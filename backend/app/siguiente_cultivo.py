from typing import Any, Dict, List, Optional, Set, Tuple

from .climate import MONTH_KEYS, MONTH_NAMES_ES, mensual
from .guia_rotacion import NOMBRES_ZONA, cargar_guia, fila_por_slug, filas_de_cultivo
from .rotation import _advance_month, _tags_for_crop
from .schemas import RotationStep, SoilInput
from .scoring import evaluate_crop_for_month, load_crops

PERMANENTES = {"platano", "citricos"}
CICLO_LARGO_DIAS = 240  # más de ~8 meses: no sirve a quien siembra por temporada

ZONAS = NOMBRES_ZONA
PUNTAJE_MINIMO = 35
CICLOS_DEL_PLAN = 2


def _guia_por_zona() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Qué recomienda la guía después de cada cultivo de crops.json, por zona (viene de data/guia_rotacion.json)."""
    resultado: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for fila in cargar_guia()["filas"]:
        for id_ in fila["cultivos"]:
            resultado.setdefault(fila["zona"], {})[id_] = {
                "ids": fila["despues_cultivos"],
                "beneficios": [(b["color"], b["icono"], b["texto"]) for b in fila["beneficios"]],
            }
    return resultado


GUIA_POR_ZONA = _guia_por_zona()


class CultivoDesconocido(ValueError):
    pass


def _zona(climatologia: Dict[str, Dict[str, Any]]) -> str:
    """Zona agroecológica según la temperatura media anual (llanos cálidos, valles templados, altiplano frío)."""
    media = sum(mensual(climatologia.get("T2M", {}), k, 18.0) for k in MONTH_KEYS) / 12
    return "llanos" if media >= 20 else "valles" if media >= 11 else "altiplano"


def _perfil(crop: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que el cultivo le hace al suelo, deducido de sus características."""
    textos = [t.texto for t in _tags_for_crop(crop["id"], crop)]
    demanda_n = crop.get("demanda_nutrientes", {}).get("N", "media")
    return {
        "demanda_n": demanda_n,
        "raiz": crop.get("profundidad_raiz", "media"),
        "fija_n": bool(crop.get("fija_nitrogeno")),
        "permanente": crop["id"] in PERMANENTES,
        "extractivo": demanda_n == "alta" or any(t.startswith(("Extract", "Consumo")) for t in textos),
        "suelo_removido": any(("Removido" in t or "Erosi" in t) for t in textos),
        "sanitario": any("Sanitario" in t for t in textos),
        "etiquetas": textos,
    }


def _resumen(crop: Dict[str, Any], perfil: Dict[str, Any]) -> str:
    partes = [f"demanda {perfil['demanda_n']} de nitrógeno", f"raíz {perfil['raiz']}"]
    partes.append("fija nitrógeno" if perfil["fija_n"] else "no fija nitrógeno")
    texto = f"{crop['nombre']} ({crop['familia']}): " + ", ".join(partes) + "."
    if perfil["permanente"]:
        return texto + " Es un cultivo permanente: no se rota, se protege el suelo entre surcos."
    if perfil["extractivo"] and not perfil["fija_n"]:
        return texto + " Agota el suelo: conviene seguir con una leguminosa que reponga nitrógeno."
    if perfil["fija_n"]:
        return texto + " Mejora el suelo: conviene seguir con un cultivo que aproveche ese nitrógeno."
    return texto + " Cambia de familia en la siguiente campaña para cortar plagas."


def _etiqueta(color: str, icono: str, texto: str) -> Dict[str, str]:
    return {"color": color, "icono": icono, "texto": texto}


def _sin_repetidos(etiquetas: List[Dict[str, str]]) -> List[Dict[str, str]]:
    vistas, unicas = set(), []
    for e in etiquetas:
        if e["texto"] not in vistas:
            vistas.add(e["texto"])
            unicas.append(e)
    return unicas


def _bonos_y_motivos(prev: Dict[str, Any], prev_p: Dict[str, Any], cand: Dict[str, Any]) -> Tuple[int, List[str], List[Dict[str, str]]]:
    """Puntos extra y razones, según las reglas prácticas de rotación (familia, nitrógeno, raíz, cobertura)."""
    cand_p = _perfil(cand)
    bono = 0
    beneficios: List[Dict[str, str]] = []
    motivos = [f"Cambia de familia ({prev['familia']} → {cand['familia']}) y corta los ciclos de plagas."]
    if prev_p["sanitario"]:
        beneficios.append(_etiqueta("naranja", "🟠", "Corte de Plagas"))
    if prev_p["permanente"]:
        if cand_p["fija_n"]:
            bono += 25
            motivos = [f"Leguminosa baja entre surcos de {prev['nombre']}: fija nitrógeno y cubre el suelo sin arrancar la plantación."]
            beneficios = [_etiqueta("azul", "🔵", "Fijador de Nitrógeno"), _etiqueta("verde", "🟢", "Control de Erosión")]
        return bono, motivos, beneficios
    if prev_p["extractivo"] and cand_p["fija_n"]:
        bono += 20
        motivos.append(f"Fija nitrógeno y repone lo que consumió {prev['nombre']}.")
        beneficios.append(_etiqueta("azul", "🔵", "Fijador de Nitrógeno"))
    elif prev_p["fija_n"] and cand_p["demanda_n"] in {"media", "alta"}:
        bono += 15
        motivos.append(f"Aprovecha el nitrógeno que dejó {prev['nombre']}.")
        beneficios.append(_etiqueta("verde", "🟢", "Aprovechamiento Residual"))
    if cand_p["raiz"] != prev_p["raiz"]:
        bono += 6
        motivos.append(f"Su raíz {cand_p['raiz']} explora otra capa que la raíz {prev_p['raiz']} de {prev['nombre']}.")
        if cand_p["raiz"] == "profunda":
            beneficios.append(_etiqueta("morado", "🟣", "Recuperador Profundo"))
    if prev_p["suelo_removido"] and cand["categoria"] in {"cereales", "oleaginosas"}:
        bono += 8
        motivos.append("Deja rastrojo que protege el suelo que quedó removido.")
        beneficios.append(_etiqueta("verde", "🟢", "Generador de Biomasa"))
    return bono, motivos, beneficios


def sugerir_siguientes(
    climatologia: Dict[str, Dict[str, Any]],
    anterior_id: str,
    mes_siembra: Optional[int],
    suelo: Optional[SoilInput] = None,
    riego: Optional[str] = None,
    excluir_ids: Optional[Set[str]] = None,
    excluir_familias: Optional[Set[str]] = None,
    limite: int = 5,
) -> List[Dict[str, Any]]:
    """Cultivos que conviene sembrar después de `anterior_id`; con mes_siembra=None busca el mejor mes de cada uno."""
    crops = load_crops()
    por_id = {c["id"]: c for c in crops}
    if anterior_id not in por_id:
        raise CultivoDesconocido(anterior_id)
    prev = por_id[anterior_id]
    prev_p = _perfil(prev)
    prohibidos_ids = (excluir_ids or set()) | {anterior_id}
    prohibidas_familias = (excluir_familias or set()) | {prev["familia"]}

    zona = _zona(climatologia)
    guia = GUIA_POR_ZONA.get(zona, {}).get(anterior_id)

    sugerencias: List[Dict[str, Any]] = []
    for cand in crops:
        if cand["id"] in prohibidos_ids or cand["familia"] in prohibidas_familias:
            continue
        if prev_p["permanente"] and not cand.get("fija_nitrogeno"):
            continue
        if not prev_p["permanente"] and cand["id"] in PERMANENTES:
            continue  # quien siembra por temporada no puede esperar años a que produzca
        meses = [mes_siembra] if mes_siembra else range(1, 13)
        evaluaciones = [evaluate_crop_for_month(cand, climatologia, m, suelo=suelo, riego=riego) for m in meses]
        mejor = max(evaluaciones, key=lambda e: e.puntaje)
        bono, motivos, beneficios = _bonos_y_motivos(prev, prev_p, cand)
        if mes_siembra and mejor.puntaje < PUNTAJE_MINIMO:
            mejor_del_anio = max(
                (evaluate_crop_for_month(cand, climatologia, m, suelo=suelo, riego=riego) for m in range(1, 13)),
                key=lambda e: e.puntaje,
            )
            if mejor_del_anio.puntaje >= PUNTAJE_MINIMO:
                motivos.append(
                    f"En {MONTH_NAMES_ES[mes_siembra - 1].lower()} el clima no acompaña; "
                    f"el mejor mes para sembrarlo es {MONTH_NAMES_ES[mejor_del_anio.mes_siembra_evaluado - 1].lower()}."
                )
                mejor = mejor_del_anio
        if guia and cand["id"] in guia["ids"]:
            bono += 30
            motivos.insert(0, f"La guía de rotación para {ZONAS[zona].lower()} recomienda {cand['nombre']} después de {prev['nombre']}.")
            beneficios = _sin_repetidos(beneficios + [_etiqueta(*t) for t in guia["beneficios"]])
        if max(cand["ciclo_dias"]) > CICLO_LARGO_DIAS:
            bono -= 15
            motivos.append(f"Ciclo largo: unos {round(max(cand['ciclo_dias']) / 30)} meses hasta cosechar.")
        motivos.append(f"Clima: {mejor.puntaje}/100 sembrando en {MONTH_NAMES_ES[mejor.mes_siembra_evaluado - 1].lower()}.")
        sugerencias.append({
            "id": cand["id"],
            "cultivo": cand["nombre"],
            "familia": cand["familia"],
            "categoria": cand["categoria"],
            "puntaje_climatico": mejor.puntaje,
            "etiqueta": mejor.etiqueta,
            "mes_siembra": mejor.mes_siembra_evaluado,
            "duracion_ciclo_dias": mejor.duracion_ciclo_dias,
            "afinidad": mejor.puntaje + bono,
            "motivos": motivos,
            "etiquetas": [t.model_dump() for t in _tags_for_crop(cand["id"], cand)],
            "beneficios": beneficios,
        })

    viables = [s for s in sugerencias if s["puntaje_climatico"] >= PUNTAJE_MINIMO]
    return sorted(viables, key=lambda s: s["afinidad"], reverse=True)[:limite]


def _bloque_guia(filas: List[Dict[str, Any]], zona: str) -> Dict[str, Any]:
    """Lo que dice la guía sobre este cultivo: primero la fila de tu zona, luego las de otras zonas."""
    guia = cargar_guia()
    ordenadas = sorted(filas, key=lambda f: f["zona"] != zona)
    return {
        "zona_detectada": NOMBRES_ZONA[zona],
        "filas": [{**f, "zona_nombre": NOMBRES_ZONA[f["zona"]], "en_tu_zona": f["zona"] == zona} for f in ordenadas],
        "reglas": guia["reglas"],
    }


def armar_solo_guia(climatologia: Dict[str, Dict[str, Any]], slug: str) -> Dict[str, Any]:
    """Producto que está en la guía pero no en crops.json (caña, sésamo, ají…): se muestra lo que dice la guía, sin puntajes."""
    filas = fila_por_slug(cargar_guia(), slug)
    if not filas:
        raise CultivoDesconocido(slug)
    zona = _zona(climatologia)
    primera = filas[0]
    return {
        "anterior": {
            "id": f"guia:{slug}", "cultivo": primera["producto"], "familia": "", "categoria": "guia",
            "demanda_nitrogeno": None, "raiz": None, "fija_nitrogeno": None, "permanente": False,
            "etiquetas": primera["impacto"], "resumen": f"{primera['producto']}: {primera['temporada']}.",
        },
        "zona": NOMBRES_ZONA[zona],
        "confianza": None,
        "sugerencias": [],
        "ciclo_rotacion": [],
        "guia": _bloque_guia(filas, zona),
        "solo_guia": True,
        "nota": "Este producto no está en la base de cultivos con datos de clima: se muestra lo que recomienda la guía de rotación de Bolivia.",
    }


def _confianza(suelo: Optional[SoilInput], riego: Optional[str], hay_guia: bool, mejor_puntaje: Optional[int]) -> Dict[str, Any]:
    """Qué tan firme es la sugerencia: 10–95 según los datos que aportó el usuario y el respaldo de la guía."""
    campos = ("ph", "materia_organica_pct", "textura", "nitrogeno", "fosforo", "potasio", "pendiente_pct")
    datos = sum(1 for c in campos if suelo is not None and getattr(suelo, c) is not None)
    puntos = 30 + round(30 * datos / len(campos))
    por_que = [f"Datos de suelo ingresados: {datos} de {len(campos)}."]
    if hay_guia:
        puntos += 10
        por_que.append("La guía de rotación de la zona cubre este cultivo anterior.")
    else:
        por_que.append("La guía de rotación de la zona no menciona este cultivo anterior.")
    if riego:
        puntos += 10
        por_que.append(f"Indicaste tu riego ({riego}).")
    else:
        por_que.append("No indicaste si tienes riego: se asume solo la lluvia.")
    if mejor_puntaje is not None and mejor_puntaje < 75:
        puntos -= 10
        por_que.append("La mejor opción no llega a 'Muy viable' con el clima de la zona.")
    puntos = max(10, min(95, puntos))
    return {"puntos": puntos, "etiqueta": "Alta" if puntos >= 70 else "Media" if puntos >= 45 else "Baja", "por_que": por_que}


def _paso(ciclo: int, s: Dict[str, Any], mes_fin: int, rol: str) -> Dict[str, Any]:
    return RotationStep(
        ciclo=ciclo, id_cultivo=s["id"], nombre=s["cultivo"], familia=s["familia"], categoria=s["categoria"],
        mes_inicio=s["mes_siembra"], mes_fin=mes_fin, puntaje_climatico=s["puntaje_climatico"],
        rol_agronomico=rol, razon=" ".join(s["motivos"][:2]), etiquetas=s["etiquetas"],
    ).model_dump()


def armar_siguiente_cultivo(
    climatologia: Dict[str, Dict[str, Any]],
    anterior_id: str,
    mes_siembra: Optional[int],
    suelo: Optional[SoilInput] = None,
    riego: Optional[str] = None,
) -> Dict[str, Any]:
    """Qué sembrar después del cultivo anterior, más una rotación de 2 campañas y un cierre con abono verde."""
    por_id = {c["id"]: c for c in load_crops()}
    if anterior_id not in por_id:
        raise CultivoDesconocido(anterior_id)
    prev = por_id[anterior_id]
    prev_p = _perfil(prev)

    sugerencias = sugerir_siguientes(climatologia, anterior_id, mes_siembra, suelo, riego)

    plan: List[Dict[str, Any]] = []
    if sugerencias and not prev_p["permanente"]:
        ids_usados, familias_usadas = {anterior_id}, {prev["familia"]}
        actual_id, mes = anterior_id, mes_siembra
        for ciclo in range(1, CICLOS_DEL_PLAN + 1):
            opciones = sugerir_siguientes(climatologia, actual_id, mes, suelo, riego, ids_usados, familias_usadas, limite=1)
            if not opciones:
                break
            elegido = opciones[0]
            fin = _advance_month(elegido["mes_siembra"], elegido["duracion_ciclo_dias"])
            rol = "Leguminosa que repone nitrógeno" if por_id[elegido["id"]].get("fija_nitrogeno") else "Cultivo de otra familia"
            plan.append(_paso(ciclo, elegido, fin, rol))
            ids_usados.add(elegido["id"])
            familias_usadas.add(elegido["familia"])
            actual_id, mes = elegido["id"], (fin % 12) + 1
        if plan:
            inicio = (plan[-1]["mes_fin"] % 12) + 1
            plan.append(RotationStep(
                ciclo=len(plan) + 1, id_cultivo="abono_verde", nombre="Abono verde (vicia / avena) o descanso",
                familia="cobertura_mixta", categoria="regeneracion", mes_inicio=inicio,
                mes_fin=_advance_month(inicio, 75), puntaje_climatico=90,
                rol_agronomico="Regeneración de materia orgánica y estructura del suelo",
                razon="Cierra la rotación protegiendo el suelo y aportando biomasa antes de volver a sembrar.",
                etiquetas=_tags_for_crop("abono_verde"),
            ).model_dump())

    zona = _zona(climatologia)
    sin_datos_suelo = suelo is None or (suelo.ph is None and suelo.materia_organica_pct is None)
    return {
        "anterior": {
            "id": prev["id"], "cultivo": prev["nombre"], "familia": prev["familia"], "categoria": prev["categoria"],
            "demanda_nitrogeno": prev_p["demanda_n"], "raiz": prev_p["raiz"], "fija_nitrogeno": prev_p["fija_n"],
            "permanente": prev_p["permanente"], "etiquetas": [t.model_dump() for t in _tags_for_crop(prev["id"], prev)], "resumen": _resumen(prev, prev_p),
        },
        "zona": ZONAS[zona],
        "guia": _bloque_guia(filas_de_cultivo(cargar_guia(), anterior_id), zona),
        "confianza": _confianza(
            suelo, riego, anterior_id in GUIA_POR_ZONA.get(zona, {}),
            sugerencias[0]["puntaje_climatico"] if sugerencias else None,
        ),
        "sugerencias": sugerencias,
        "ciclo_rotacion": plan,
        "nota": (
            "No hay pH ni materia orgánica: la sugerencia se basa en lo que suele dejar este cultivo "
            f"(familia, nitrógeno y raíz), en el clima y en la guía de rotación para {ZONAS[zona].lower()}."
            if sin_datos_suelo else
            "Sugerencia basada en el cultivo anterior, el clima y los datos de suelo que ingresaste."
        ),
    }
