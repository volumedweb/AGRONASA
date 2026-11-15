from typing import Any, Dict, List, Optional
from .climate import MONTH_NAMES_ES
from .schemas import RotationStep, RotationTag, SoilInput
from .scoring import evaluate_crop_for_month, generate_general_soil_observations, load_crops


_CROP_TAGS: Dict[str, List[Dict[str, str]]] = {
    "maiz": [
        {"color": "rojo", "icono": "🔴", "texto": "Consumo Excesivo"},
        {"color": "verde", "icono": "🟢", "texto": "Generador de Biomasa"},
    ],
    "papa": [
        {"color": "rojo", "icono": "🔴", "texto": "Consumo Excesivo"},
        {"color": "naranja", "icono": "🟠", "texto": "Riesgo Sanitario / Erosivo"},
    ],
    "quinua": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo"},
        {"color": "naranja", "icono": "🟠", "texto": "Erosión Eólica"},
    ],
    "soya": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo P/S"},
        {"color": "azul", "icono": "🔵", "texto": "Fijador de Nitrógeno"},
    ],
    "frijol": [
        {"color": "azul", "icono": "🔵", "texto": "Fijador de Nitrógeno"},
        {"color": "verde", "icono": "🟢", "texto": "Cobertura Rápida"},
    ],
    "haba": [
        {"color": "azul", "icono": "🔵", "texto": "Fijador de Nitrógeno"},
        {"color": "morado", "icono": "🟣", "texto": "Mejorador de Suelo"},
    ],
    "yuca": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo K"},
        {"color": "naranja", "icono": "🟠", "texto": "Suelo Removido"},
    ],
    "arroz": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo N"},
        {"color": "rojo", "icono": "🔴", "texto": "Compactación"},
    ],
    "tomate": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo Intenso"},
        {"color": "naranja", "icono": "🟠", "texto": "Riesgo Sanitario"},
    ],
    "cebolla": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo Superficial"},
        {"color": "naranja", "icono": "🟠", "texto": "Riesgo Sanitario"},
    ],
    "zanahoria": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo Superficial"},
        {"color": "naranja", "icono": "🟠", "texto": "Suelo Removido"},
    ],
    "platano": [
        {"color": "amarillo", "icono": "🟡", "texto": "Cultivo Permanente"},
        {"color": "rojo", "icono": "🔴", "texto": "Alto Consumo K"},
    ],
    "citricos": [
        {"color": "amarillo", "icono": "🟡", "texto": "Cultivo Permanente"},
        {"color": "naranja", "icono": "🟠", "texto": "Riesgo de Erosión"},
    ],
    "mani": [
        {"color": "rojo", "icono": "🔴", "texto": "Extractivo"},
        {"color": "naranja", "icono": "🟠", "texto": "Suelo Removido"},
    ],
    "girasol": [
        {"color": "verde", "icono": "🟢", "texto": "Generador de Biomasa"},
        {"color": "morado", "icono": "🟣", "texto": "Descompactador"},
    ],
    "abono_verde": [
        {"color": "verde", "icono": "🟢", "texto": "Generador de Biomasa"},
        {"color": "azul", "icono": "🔵", "texto": "Fijador de Nitrógeno"},
        {"color": "morado", "icono": "🟣", "texto": "Recuperador"},
    ],
}


def _tags_for_crop(crop_id: str, crop: Optional[Dict[str, Any]] = None) -> List[RotationTag]:
    if crop_id in _CROP_TAGS:
        return [RotationTag(**t) for t in _CROP_TAGS[crop_id]]
    tags: List[RotationTag] = []
    if crop and crop.get("fija_nitrogeno"):
        tags.append(RotationTag(color="azul", icono="🔵", texto="Fijador de Nitrógeno"))
    elif crop and crop.get("categoria") in {"cereales", "oleaginosas"}:
        tags.append(RotationTag(color="verde", icono="🟢", texto="Generador de Biomasa"))
    else:
        tags.append(RotationTag(color="rojo", icono="🔴", texto="Extractivo"))
    return tags


def _advance_month(mes_inicio: int, duracion_dias: int) -> int:
    meses_avance = max(3, int(round(duracion_dias / 30.0)))
    return ((mes_inicio - 1 + meses_avance) % 12) + 1


def build_crop_rotation(
    climatology: Dict[str, Dict[str, Any]],
    mes_inicio: int,
    suelo: SoilInput,
    cultivo_inicial_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construye un plan de rotación de cultivos en 4 etapas siguiendo las reglas de la sección 9.3:
    1. No repetir familia botánica en ciclos consecutivos.
    2. Alternar cultivos exigentes en nutrientes con leguminosas fijadoras de nitrógeno.
    3. Alternar profundidad de raíz (profunda / media / superficial).
    4. Incluir abono verde / descanso regenerativo, especialmente si la materia orgánica es baja.
    """
    crops = load_crops()
    crops_by_id = {c["id"]: c for c in crops}

    steps: List[RotationStep] = []
    used_ids = set()

    # --- CICLO 1: Cultivo principal ---
    c1_crop = None
    if cultivo_inicial_id and cultivo_inicial_id in crops_by_id:
        c1_crop = crops_by_id[cultivo_inicial_id]
        c1_eval = evaluate_crop_for_month(c1_crop, climatology, mes_inicio, suelo=suelo)
    else:
        # Priorizar un cultivo energético/comercial (cereal, tubérculo u oleaginosa) con buen puntaje
        non_legumes = [c for c in crops if not c.get("fija_nitrogeno")]
        evaluated = [
            (c, evaluate_crop_for_month(c, climatology, mes_inicio, suelo=suelo))
            for c in non_legumes
        ]
        evaluated.sort(key=lambda pair: pair[1].puntaje, reverse=True)
        c1_crop, c1_eval = evaluated[0]

    used_ids.add(c1_crop["id"])
    c1_fin = _advance_month(mes_inicio, c1_eval.duracion_ciclo_dias)
    demanda_n_c1 = c1_crop.get("demanda_nutrientes", {}).get("N", "media")
    raiz_c1 = c1_crop.get("profundidad_raiz", "profunda")

    steps.append(
        RotationStep(
            ciclo=1,
            id_cultivo=c1_crop["id"],
            nombre=c1_crop["nombre"],
            familia=c1_crop["familia"],
            categoria=c1_crop["categoria"],
            mes_inicio=mes_inicio,
            mes_fin=c1_fin,
            puntaje_climatico=c1_eval.puntaje,
            rol_agronomico=f"Cultivo principal (demanda de N {demanda_n_c1}, raíz {raiz_c1})",
            razon=(
                f"Inicia el ciclo en {MONTH_NAMES_ES[mes_inicio - 1]} aprovechando una aptitud "
                f"agroclimática de {c1_eval.puntaje}/100."
            ),
            etiquetas=_tags_for_crop(c1_crop["id"], c1_crop),
        )
    )

    # --- CICLO 2: Leguminosa fijadora de nitrógeno (distinta familia) ---
    mes_c2 = (c1_fin % 12) + 1
    legumes = [
        c for c in crops
        if c.get("fija_nitrogeno") and c["familia"] != c1_crop["familia"] and c["id"] not in used_ids
    ]
    if not legumes:  # p. ej. el primer cultivo ya es leguminosa: se alterna con otra leguminosa de distinta especie
        legumes = [c for c in crops if c.get("fija_nitrogeno") and c["id"] not in used_ids]
    if not legumes:
        legumes = [c for c in crops if c["id"] not in used_ids and c["familia"] != c1_crop["familia"]]
    # Evaluar en el mes inmediato o el mes siguiente si mejora notablemente la ventana
    best_legume_pair = None
    for candidate_month in [mes_c2, (mes_c2 % 12) + 1, ((mes_c2 + 1) % 12) + 1]:
        for leg in legumes:
            ev = evaluate_crop_for_month(leg, climatology, candidate_month, suelo=suelo)
            if best_legume_pair is None or ev.puntaje > best_legume_pair[1].puntaje:
                best_legume_pair = (leg, ev, candidate_month)

    c2_crop, c2_eval, mes_c2_real = best_legume_pair
    used_ids.add(c2_crop["id"])
    c2_fin = _advance_month(mes_c2_real, c2_eval.duracion_ciclo_dias)
    raiz_c2 = c2_crop.get("profundidad_raiz", "media")

    steps.append(
        RotationStep(
            ciclo=2,
            id_cultivo=c2_crop["id"],
            nombre=c2_crop["nombre"],
            familia=c2_crop["familia"],
            categoria=c2_crop["categoria"],
            mes_inicio=mes_c2_real,
            mes_fin=c2_fin,
            puntaje_climatico=c2_eval.puntaje,
            rol_agronomico="Fijación biológica de nitrógeno (leguminosa)",
            razon=(
                f"Repone el nitrógeno consumido por {c1_crop['nombre']} y cambia de familia botánica "
                f"({c1_crop['familia']} → {c2_crop['familia']}) para cortar ciclos de plagas."
            ),
            etiquetas=_tags_for_crop(c2_crop["id"], c2_crop),
        )
    )

    # --- CICLO 3: Raíz distinta y familia distinta (tubérculo, hortaliza o grano andino) ---
    mes_c3 = (c2_fin % 12) + 1
    c3_candidates = [
        c for c in crops
        if c["familia"] not in {c1_crop["familia"], c2_crop["familia"]}
        and c["id"] not in used_ids
    ]
    best_c3_tuple = None
    for candidate_month in [mes_c3, (mes_c3 % 12) + 1, ((mes_c3 + 1) % 12) + 1]:
        for cand in c3_candidates:
            ev = evaluate_crop_for_month(cand, climatology, candidate_month, suelo=suelo)
            # Bonificar si tiene profundidad de raíz diferente al ciclo 2
            bonus = 8 if cand.get("profundidad_raiz") != raiz_c2 else 0
            eff_score = ev.puntaje + bonus
            if best_c3_tuple is None or eff_score > best_c3_tuple[3]:
                best_c3_tuple = (cand, ev, candidate_month, eff_score)

    c3_crop, c3_eval, mes_c3_real, _ = best_c3_tuple
    c3_fin = _advance_month(mes_c3_real, c3_eval.duracion_ciclo_dias)
    raiz_c3 = c3_crop.get("profundidad_raiz", "media")

    steps.append(
        RotationStep(
            ciclo=3,
            id_cultivo=c3_crop["id"],
            nombre=c3_crop["nombre"],
            familia=c3_crop["familia"],
            categoria=c3_crop["categoria"],
            mes_inicio=mes_c3_real,
            mes_fin=c3_fin,
            puntaje_climatico=c3_eval.puntaje,
            rol_agronomico=f"Ruptura sanitaria y exploración radicular ({raiz_c3})",
            razon=(
                f"Aprovecha el nitrógeno fijado por {c2_crop['nombre']}, explora otro estrato del suelo "
                f"(raíz {raiz_c3}) y pertenece a la familia {c3_crop['familia']}."
            ),
            etiquetas=_tags_for_crop(c3_crop["id"], c3_crop),
        )
    )

    # --- CICLO 4: Abono verde o descanso regenerativo ---
    mes_c4 = (c3_fin % 12) + 1
    c4_fin = _advance_month(mes_c4, 75)
    mo_baja = (suelo.materia_organica_pct is not None and suelo.materia_organica_pct < 2.5) or (
        suelo.nitrogeno == "bajo"
    )
    nombre_c4 = (
        "Abono verde (Vicia / Avena forrajera incorporada)"
        if mo_baja
        else "Cobertura vegetal / Descanso mejorado"
    )
    razon_c4 = (
        "Tu suelo presenta baja materia orgánica o nitrógeno: incorporar abono verde antes de la floración "
        "restaura la estructura física, aumenta la retención de humedad y protege contra la erosión."
        if mo_baja
        else "Cierra la rotación protegiendo el suelo con cobertura vegetal y aportando biomasa antes de volver a sembrar."
    )

    steps.append(
        RotationStep(
            ciclo=4,
            id_cultivo="abono_verde",
            nombre=nombre_c4,
            familia="cobertura_mixta",
            categoria="regeneracion",
            mes_inicio=mes_c4,
            mes_fin=c4_fin,
            puntaje_climatico=90,
            rol_agronomico="Regeneración de materia orgánica y estructura del suelo",
            razon=razon_c4,
            etiquetas=_tags_for_crop("abono_verde"),
        )
    )

    observaciones = generate_general_soil_observations(suelo)
    if not observaciones:
        observaciones.append(
            "Los parámetros de suelo ingresados se encuentran en rangos manejables para la rotación propuesta."
        )

    beneficios = [
        f"Diversidad botánica completa: {c1_crop['familia']} → {c2_crop['familia']} → {c3_crop['familia']} → cobertura regenerativa.",
        f"Reposición biológica de nitrógeno en el ciclo 2 mediante {c2_crop['nombre']}.",
        f"Alternancia de arquitectura radicular ({raiz_c1} → {raiz_c2} → {raiz_c3}) que evita la compactación y el agotamiento de una sola capa del suelo.",
        "Reducción de la presión de plagas, nematodos y hongos específicos del suelo.",
    ]

    return {
        "observaciones_suelo": observaciones,
        "ciclo_rotacion": steps,
        "beneficios_esperados": beneficios,
    }
