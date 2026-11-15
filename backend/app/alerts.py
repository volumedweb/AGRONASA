from typing import Any, Dict, List, Optional, Tuple
from .nasa_client import get_recent_and_historical_window
from .schemas import AlertItem


FLAT_HISTORY_MM = 1.0
DRY_SEASON_30D_MM = 10.0  # si lo normal en 30 días es menos de esto, comparar percentiles no significa nada


def compute_percentile(value: float, historical_values: List[float]) -> float:
    """
    Calcula el percentil (0 a 100) de `value` frente a la distribución histórica.
    Usa interpolación lineal sobre la serie ordenada.
    """
    if not historical_values:
        return 50.0

    sorted_vals = sorted(historical_values)
    n = len(sorted_vals)
    if sorted_vals[-1] - sorted_vals[0] < FLAT_HISTORY_MM:
        return 50.0  # historia casi sin variación (temporada seca): no hay anomalía que medir
    if value <= sorted_vals[0]:
        if sorted_vals[0] == 0:
            return 0.0
        return round(max(1.0, (value / sorted_vals[0]) * (100.0 / (n + 1))), 1)
    if value >= sorted_vals[-1]:
        return round(min(99.0, 100.0 - (sorted_vals[-1] / max(value, 0.1)) * (100.0 / (n + 1))), 1)

    below = sum(1 for v in sorted_vals if v < value)
    equal = sum(1 for v in sorted_vals if v == value)
    percentile = ((below + 0.5 * equal) / n) * 100.0
    return round(percentile, 1)


def classify_precip_percentile(percentile: float) -> Tuple[str, str, str]:
    """
    Clasifica el percentil de lluvia acumulada según la tabla de la sección 8:
    < 10: Sequía severa
    10 - 25: Déficit de lluvia
    25 - 75: Normal
    75 - 90: Exceso de lluvia
    > 90: Exceso extremo / riesgo de inundación
    Retorna: (tipo_codigo, estado_legible, severidad_semaforo)
    """
    if percentile < 10.0:
        return "sequia_severa", "Sequía severa", "rojo"
    if percentile < 25.0:
        return "deficit_lluvia", "Déficit de lluvia", "naranja"
    if percentile <= 75.0:
        return "normal", "Normal", "verde"
    if percentile <= 90.0:
        return "exceso_lluvia", "Exceso de lluvia", "naranja"
    return "exceso_extremo", "Exceso extremo / riesgo de inundación", "rojo"


def _aclaracion_de_datos(scenario: Dict[str, Any]) -> str:
    if scenario.get("estimado"):
        return " (Estimación: no hay datos diarios recientes de NASA POWER para este punto.)"
    if scenario.get("hasta"):
        anio, mes, dia = scenario["hasta"].split("-")
        return f" (Datos reales de NASA POWER hasta el {dia}/{mes}.)"
    return ""


def evaluate_alerts_from_data(scenario: Dict[str, Any]) -> List[AlertItem]:
    """Evalúa las alertas agroclimáticas de 30 días, 60 días y helada a partir de datos históricos."""
    alerts: List[AlertItem] = []
    aclaracion = _aclaracion_de_datos(scenario)

    p30_val = float(scenario["precip_30d_actual"])
    p30_hist = [float(x) for x in scenario["precip_30d_hist"]]
    p30_mean = round(sum(p30_hist) / len(p30_hist), 1) if p30_hist else p30_val
    perc_30 = 50.0 if p30_mean < DRY_SEASON_30D_MM else compute_percentile(p30_val, p30_hist)
    tipo_30, estado_30, sev_30 = classify_precip_percentile(perc_30)

    gwet = float(scenario.get("gwetroot_recent", 0.5))
    t_min = float(scenario.get("t2m_min_recent", 10.0))

    # Redacción honesta basada en anomalía histórica (nunca pronóstico futuro)
    if tipo_30 in ("sequia_severa", "deficit_lluvia"):
        top_pct = max(1, int(round(perc_30)))
        refuerzo_suelo = (
            f" La humedad en zona de raíces es baja ({int(gwet * 100)} %)."
            if gwet < 0.40
            else ""
        )
        msg_30 = (
            f"Las últimas 4 semanas están entre el {top_pct} % más secas de los últimos 20 años "
            f"en tu zona ({p30_val} mm acumulados frente a {p30_mean} mm de media histórica)."
            f"{refuerzo_suelo}"
        )
    elif tipo_30 in ("exceso_lluvia", "exceso_extremo"):
        top_pct = max(1, int(round(100.0 - perc_30)))
        refuerzo_suelo = (
            f" El suelo presenta alta saturación en zona de raíces ({int(gwet * 100)} %)."
            if gwet > 0.72
            else ""
        )
        msg_30 = (
            f"Las últimas 4 semanas están entre el {top_pct} % más lluviosas de los últimos 20 años "
            f"en tu zona ({p30_val} mm acumulados frente a {p30_mean} mm de media histórica)."
            f"{refuerzo_suelo}"
        )
    else:
        msg_30 = (
            f"La lluvia de las últimas 4 semanas ({p30_val} mm) se mantiene dentro del rango normal "
            f"histórico de los últimos 20 años (media de {p30_mean} mm, percentil {int(round(perc_30))})."
        )

    alerts.append(
        AlertItem(
            tipo=tipo_30,
            estado=f"{estado_30} (30 días)",
            severidad=sev_30,
            ventana_dias=30,
            percentil=perc_30,
            lluvia_reciente_mm=p30_val,
            lluvia_media_historica_mm=p30_mean,
            humedad_suelo_raiz=gwet,
            temp_min_reciente_c=t_min,
            mensaje=msg_30 + aclaracion,
        )
    )

    # Ventana de 60 días
    p60_val = float(scenario["precip_60d_actual"])
    p60_hist = [float(x) for x in scenario["precip_60d_hist"]]
    p60_mean = round(sum(p60_hist) / len(p60_hist), 1) if p60_hist else p60_val
    perc_60 = 50.0 if p60_mean < 2 * DRY_SEASON_30D_MM else compute_percentile(p60_val, p60_hist)
    tipo_60, estado_60, sev_60 = classify_precip_percentile(perc_60)

    if tipo_60 != "normal":
        extremo_txt = (
            f"{max(1, int(round(perc_60)))} % más secas"
            if perc_60 < 25
            else f"{max(1, int(round(100 - perc_60)))} % más húmedas"
        )
        alerts.append(
            AlertItem(
                tipo=f"{tipo_60}_60d",
                estado=f"{estado_60} (60 días)",
                severidad=sev_60,
                ventana_dias=60,
                percentil=perc_60,
                lluvia_reciente_mm=p60_val,
                lluvia_media_historica_mm=p60_mean,
                humedad_suelo_raiz=gwet,
                mensaje=(
                    f"En el acumulado de 60 días ({p60_val} mm vs {p60_mean} mm históricos), "
                    f"el bimestre se ubica entre el {extremo_txt} de las últimas dos décadas."
                    f"{aclaracion}"
                ),
            )
        )

    # Alerta de helada reciente
    if t_min <= 2.5:
        sev_helada = "rojo" if t_min <= 0.0 else "amarillo"
        estado_helada = "Riesgo alto de helada" if t_min <= 0.0 else "Temperaturas nocturnas frías"
        alerts.append(
            AlertItem(
                tipo="riesgo_helada",
                estado=estado_helada,
                severidad=sev_helada,
                temp_min_reciente_c=t_min,
                mensaje=(
                    f"Las temperaturas mínimas recientes han descendido hasta {t_min} °C. "
                    "Los cultivos sensibles a heladas pueden sufrir daños foliares o pérdida de floración."
                    f"{aclaracion}"
                ),
            )
        )

    for alerta in alerts:
        alerta.estimado = bool(scenario.get("estimado"))
    return alerts


def get_alerts_for_point(lat: float, lon: float, allow_network: bool = True) -> List[AlertItem]:
    scenario = get_recent_and_historical_window(lat, lon, allow_network=allow_network)
    return evaluate_alerts_from_data(scenario)
