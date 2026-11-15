import json
import math
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from .climate import MONTH_NAMES_ES, compute_crop_window
from .schemas import AlertItem, CropRecommendation, SoilInput

CROPS_PATH = Path(__file__).resolve().parent.parent / "data" / "crops.json"
_CROPS_CACHE: Optional[List[Dict[str, Any]]] = None

FACTOR_LABELS_ES = {
    "temperatura": "temperatura",
    "precipitacion": "precipitación",
    "heladas": "riesgo de heladas",
    "humedad_suelo": "humedad del suelo",
    "suelo_ph": "pH del suelo",
    "suelo_textura": "textura del suelo",
    "suelo_drenaje": "drenaje del suelo",
}


def load_crops(categoria: Optional[str] = None) -> List[Dict[str, Any]]:
    global _CROPS_CACHE
    if _CROPS_CACHE is None:
        _CROPS_CACHE = json.loads(CROPS_PATH.read_text(encoding="utf-8"))
    if categoria:
        return [c for c in _CROPS_CACHE if c["categoria"].lower() == categoria.lower()]
    return list(_CROPS_CACHE)


def trapezoid(x: float, abs_min: float, opt_min: float, opt_max: float, abs_max: float) -> float:
    """
    Función trapezoidal de aptitud agroecológica (enfoque FAO EcoCrop):
    - 0.0 fuera de [abs_min, abs_max]
    - 1.0 dentro de [opt_min, opt_max]
    - interpolación lineal en los tramos intermedios
    """
    if x <= abs_min or x >= abs_max:
        return 0.0
    if opt_min <= x <= opt_max:
        return 1.0
    if x < opt_min:
        return (x - abs_min) / (opt_min - abs_min)
    return (abs_max - x) / (abs_max - opt_max)


# Cuánto del déficit de lluvia cubre el riego (el cultivo recibe lluvia + riego).
RIEGO_APORTE = {"secano": 0.0, "limitado": 0.4, "completo": 0.8}


def score_to_label(score: int) -> Literal["Muy viable", "Viable con cuidados", "Poco viable", "No recomendado"]:
    if score >= 75:
        return "Muy viable"
    if score >= 50:
        return "Viable con cuidados"
    if score >= 25:
        return "Poco viable"
    return "No recomendado"


def _compute_frost_factor(temp_min_window: float, crop: Dict[str, Any]) -> float:
    umbral = float(crop.get("temp_min_helada", 2.0))
    sensible = bool(crop.get("sensible_helada", True))
    safe_temp = umbral + 3.0
    lethal_temp = umbral - (2.5 if sensible else 5.0)

    if temp_min_window >= safe_temp:
        return 1.0
    if temp_min_window <= lethal_temp:
        return 0.0 if sensible else 0.35
    ratio = (temp_min_window - lethal_temp) / (safe_temp - lethal_temp)
    return max(0.0, min(1.0, ratio))


def generate_general_soil_observations(suelo: Optional[SoilInput]) -> List[str]:
    if not suelo:
        return []
    obs: List[str] = []
    if suelo.ph is not None:
        if suelo.ph < 5.2:
            obs.append(
                f"pH {suelo.ph}: suelo fuertemente ácido. Se recomienda evaluar encalado agrícola "
                "para mejorar la disponibilidad de fósforo y calcio."
            )
        elif suelo.ph > 7.8:
            obs.append(
                f"pH {suelo.ph}: suelo alcalino. Incorporar materia orgánica compostada ayuda a "
                "mejorar la absorción de micronutrientes (hierro, zinc)."
            )
    if suelo.materia_organica_pct is not None and suelo.materia_organica_pct < 2.0:
        obs.append(
            f"Materia orgánica baja ({suelo.materia_organica_pct} %): se aconseja incorporar abonos "
            "verdes, estiércol compostado o rastrojos."
        )
    if suelo.nitrogeno == "bajo":
        obs.append(
            "Nivel de nitrógeno bajo: prioriza leguminosas fijadoras (frijol, haba, soya, maní) "
            "en el ciclo o planifica fertilización nitrogenada fraccionada."
        )
    if suelo.drenaje == "pobre":
        obs.append(
            "Drenaje pobre: construye camellones o zanjas de drenaje para evitar asfixia radicular "
            "en tubérculos y hortalizas."
        )
    return obs


def evaluate_crop_for_month(
    crop: Dict[str, Any],
    climatology: Dict[str, Dict[str, Any]],
    mes_siembra: int,
    suelo: Optional[SoilInput] = None,
    alertas: Optional[List[AlertItem]] = None,
    riego: Optional[str] = None,
) -> CropRecommendation:
    win = compute_crop_window(climatology, mes_siembra, crop["ciclo_dias"])

    t_cfg = crop["temp"]
    p_cfg = crop["precip_ciclo_mm"]

    f_temp = trapezoid(win["temp_media"], t_cfg["abs_min"], t_cfg["opt_min"], t_cfg["opt_max"], t_cfg["abs_max"])
    f_prec = trapezoid(
        win["precip_acumulada_mm"], p_cfg["abs_min"], p_cfg["opt_min"], p_cfg["opt_max"], p_cfg["abs_max"]
    )
    f_prec_sin_riego = f_prec
    if win["precip_acumulada_mm"] < p_cfg["opt_min"]:  # el riego compensa la falta de lluvia, no su exceso
        f_prec = f_prec + (1.0 - f_prec) * RIEGO_APORTE.get(riego or "secano", 0.0)
    f_frost = _compute_frost_factor(win["temp_min_extrema"], crop)
    f_gwet = trapezoid(win["gwetroot_medio"], 0.15, 0.35, 0.80, 0.96)

    factores: Dict[str, float] = {
        "temperatura": round(f_temp, 3),
        "precipitacion": round(f_prec, 3),
        "heladas": round(f_frost, 3),
        "humedad_suelo": round(f_gwet, 3),
    }
    pesos: Dict[str, float] = {
        "temperatura": 0.34,
        "precipitacion": 0.34,
        "heladas": 0.22,
        "humedad_suelo": 0.10,
    }

    obs_suelo: List[str] = []
    if suelo is not None:
        s_cfg = crop["suelo"]
        if suelo.ph is not None:
            ph_cfg = s_cfg["ph"]
            f_ph = trapezoid(suelo.ph, ph_cfg["abs_min"], ph_cfg["opt_min"], ph_cfg["opt_max"], ph_cfg["abs_max"])
            factores["suelo_ph"] = round(f_ph, 3)
            pesos["suelo_ph"] = 0.18
            if suelo.ph < ph_cfg["opt_min"]:
                obs_suelo.append(
                    f"pH {suelo.ph}: ácido para {crop['nombre']} (óptimo {ph_cfg['opt_min']}–{ph_cfg['opt_max']}); "
                    "considera encalado antes de sembrar."
                )
            elif suelo.ph > ph_cfg["opt_max"]:
                obs_suelo.append(
                    f"pH {suelo.ph}: elevado para {crop['nombre']} (óptimo {ph_cfg['opt_min']}–{ph_cfg['opt_max']}); "
                    "incorpora materia orgánica."
                )

        if suelo.textura is not None:
            f_tex = 1.0 if suelo.textura in s_cfg["texturas"] else 0.55
            factores["suelo_textura"] = round(f_tex, 3)
            pesos["suelo_textura"] = 0.10
            if f_tex < 1.0:
                obs_suelo.append(
                    f"Textura '{suelo.textura}' subóptima; prefiere {', '.join(s_cfg['texturas'])}."
                )

        if suelo.drenaje is not None:
            f_dren = 1.0 if suelo.drenaje in s_cfg["drenaje"] else 0.45
            factores["suelo_drenaje"] = round(f_dren, 3)
            pesos["suelo_drenaje"] = 0.12
            if f_dren < 1.0:
                obs_suelo.append(
                    f"El drenaje '{suelo.drenaje}' limita a {crop['nombre']} (requiere {', '.join(s_cfg['drenaje'])})."
                )

        if suelo.nitrogeno == "bajo":
            if crop.get("fija_nitrogeno"):
                obs_suelo.append(f"{crop['nombre']} fija nitrógeno y ayudará a enriquecer tu suelo.")
            elif crop.get("demanda_nutrientes", {}).get("N") == "alta":
                obs_suelo.append(
                    f"{crop['nombre']} tiene alta demanda de nitrógeno y tu suelo tiene nivel bajo; requerirá abonado."
                )

    # Media geométrica ponderada; si algún factor crítico vale 0, el puntaje es 0
    critical_keys = ["temperatura", "precipitacion", "heladas"]
    if "suelo_ph" in factores:
        critical_keys.append("suelo_ph")

    if any(factores[k] <= 0.0 for k in critical_keys):
        raw_score = 0.0
    else:
        total_w = sum(pesos[k] for k in factores)
        log_sum = sum(pesos[k] * math.log(max(factores[k], 1e-4)) for k in factores)
        raw_score = math.exp(log_sum / total_w) * 100.0

    # Ajuste por riesgo climático reciente (Sección 7.3)
    ajuste_riesgo: Optional[str] = None
    alertas = [a for a in (alertas or []) if not a.estimado]  # una estimación no ajusta puntajes
    if alertas and raw_score > 0:
        tipos_alerta = {a.tipo for a in alertas}
        hay_sequia = bool(tipos_alerta & {"sequia_severa", "deficit_lluvia"})
        hay_exceso = bool(tipos_alerta & {"exceso_lluvia", "exceso_extremo"})

        if hay_sequia:
            tol = crop.get("tolerancia_sequia", "media")
            if tol == "alta":
                raw_score = min(100.0, raw_score + 6.0)
                ajuste_riesgo = "+6 pts por alta tolerancia a sequía ante déficit hídrico reciente"
            elif tol == "baja":
                raw_score = max(0.0, raw_score - 10.0)
                ajuste_riesgo = "-10 pts por alta sensibilidad a sequía ante déficit hídrico reciente"
        elif hay_exceso:
            if "pobre" in crop["suelo"]["drenaje"]:
                raw_score = min(100.0, raw_score + 4.0)
                ajuste_riesgo = "+4 pts por buena tolerancia a humedad alta"
            elif crop["suelo"]["drenaje"] == ["bueno"]:
                raw_score = max(0.0, raw_score - 8.0)
                ajuste_riesgo = "-8 pts por sensibilidad al exceso de humedad y encharcamiento"

    puntaje = int(round(max(0.0, min(100.0, raw_score))))
    etiqueta = score_to_label(puntaje)

    # Determinar factor limitante (el de menor valor)
    limiting_key = min(factores, key=lambda k: factores[k])
    limiting_val = factores[limiting_key]

    # Construir explicación en lenguaje natural (Sección 7.2 paso 6)
    mes_nombre = MONTH_NAMES_ES[mes_siembra - 1]
    partes_exp = [f"Puntaje {puntaje}/100 sembrando en {mes_nombre} (ciclo ~{win['duracion_dias']} días)."]

    if f_temp >= 0.85:
        partes_exp.append(
            f"La temperatura media del ciclo ({win['temp_media']} °C) es ideal (óptimo {t_cfg['opt_min']}–{t_cfg['opt_max']} °C)."
        )
    elif f_temp >= 0.45:
        partes_exp.append(
            f"La temperatura media ({win['temp_media']} °C) es aceptable pero fuera del óptimo ({t_cfg['opt_min']}–{t_cfg['opt_max']} °C)."
        )
    else:
        partes_exp.append(
            f"La temperatura media ({win['temp_media']} °C) limita fuertemente al cultivo (requiere {t_cfg['opt_min']}–{t_cfg['opt_max']} °C)."
        )

    if limiting_key == "precipitacion" or f_prec < 0.8:
        if win["precip_acumulada_mm"] < p_cfg["opt_min"]:
            partes_exp.append(
                f"Factor limitante principal: lluvia. Se estiman {int(round(win['precip_acumulada_mm']))} mm en el ciclo "
                f"y el cultivo prefiere {p_cfg['opt_min']}–{p_cfg['opt_max']} mm (requiere riego complementario)."
            )
        elif win["precip_acumulada_mm"] > p_cfg["opt_max"]:
            partes_exp.append(
                f"Exceso hídrico: se esperan {int(round(win['precip_acumulada_mm']))} mm en el ciclo "
                f"frente al rango óptimo de {p_cfg['opt_min']}–{p_cfg['opt_max']} mm."
            )
    elif limiting_key == "heladas" and f_frost < 0.85:
        partes_exp.append(
            f"Atención a heladas: la mínima histórica del ciclo llega a {win['temp_min_extrema']} °C "
            f"(umbral de daño: {crop['temp_min_helada']} °C)."
        )
    elif limiting_val >= 0.8:
        partes_exp.append(
            f"Lluvia estimada en el ciclo ({int(round(win['precip_acumulada_mm']))} mm) bien alineada con el requerimiento hídrico."
        )
    else:
        partes_exp.append(
            f"El factor más ajustado es {FACTOR_LABELS_ES.get(limiting_key, limiting_key)} "
            f"(índice {int(round(limiting_val * 100))} %)."
        )

    if riego in ("limitado", "completo") and f_prec - f_prec_sin_riego >= 0.05:
        partes_exp.append(
            f"Con riego {riego} el déficit de lluvia se cubre en parte "
            f"(índice de lluvia {int(round(f_prec_sin_riego * 100))} % → {int(round(f_prec * 100))} %)."
        )

    if ajuste_riesgo:
        partes_exp.append(f"Ajuste climático reciente: {ajuste_riesgo}.")

    return CropRecommendation(
        id=crop["id"],
        cultivo=crop["nombre"],
        categoria=crop["categoria"],
        familia=crop["familia"],
        puntaje=puntaje,
        etiqueta=etiqueta,
        mes_siembra_evaluado=mes_siembra,
        duracion_ciclo_dias=win["duracion_dias"],
        factor_limitante=limiting_key,
        factores=factores,
        ajuste_riesgo=ajuste_riesgo,
        observaciones_suelo=obs_suelo,
        explicacion=" ".join(partes_exp),
    )


def recommend_crops(
    climatology: Dict[str, Dict[str, Any]],
    mes_siembra: Optional[int] = None,
    categorias: Optional[List[str]] = None,
    cultivos_ids: Optional[List[str]] = None,
    suelo: Optional[SoilInput] = None,
    alertas: Optional[List[AlertItem]] = None,
    riego: Optional[str] = None,
) -> List[CropRecommendation]:
    crops = load_crops()
    if categorias:
        cat_set = {c.lower() for c in categorias}
        crops = [c for c in crops if c["categoria"].lower() in cat_set]
    if cultivos_ids:
        id_set = {cid.lower() for cid in cultivos_ids}
        crops = [c for c in crops if c["id"].lower() in id_set]

    recommendations: List[CropRecommendation] = []
    for crop in crops:
        if mes_siembra is not None:
            rec = evaluate_crop_for_month(crop, climatology, mes_siembra, suelo=suelo, alertas=alertas, riego=riego)
        else:
            # Si no se especifica mes de siembra, evalúa los 12 meses y sugiere el mejor
            candidates = [
                evaluate_crop_for_month(crop, climatology, m, suelo=suelo, alertas=alertas, riego=riego)
                for m in range(1, 13)
            ]
            rec = max(candidates, key=lambda r: r.puntaje)
        recommendations.append(rec)

    recommendations.sort(key=lambda r: r.puntaje, reverse=True)
    return recommendations
