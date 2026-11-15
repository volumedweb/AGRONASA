from typing import Any, Dict, List

MONTH_KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTH_NAMES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def mensual(serie: Dict[str, Any], clave: str, por_defecto: float) -> float:
    """Valor mensual de una serie NASA; usa el valor por defecto solo si falta, no si vale 0."""
    valor = serie.get(clave)
    return por_defecto if valor is None else float(valor)


def format_monthly_climatology(climatology: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convierte la respuesta de NASA POWER en una lista mensual lista para gráficos y análisis,
    multiplicando PRECTOTCORR (mm/día) por los días de cada mes.
    """
    meses: List[Dict[str, Any]] = []
    precip_anual = 0.0

    for idx, key in enumerate(MONTH_KEYS):
        dias = DAYS_IN_MONTH[idx]
        t2m = mensual(climatology.get("T2M", {}), key, 0.0)
        t2m_max = mensual(climatology.get("T2M_MAX", {}), key, t2m + 5.0)
        t2m_min = mensual(climatology.get("T2M_MIN", {}), key, t2m - 5.0)
        prec_dia = mensual(climatology.get("PRECTOTCORR", {}), key, 0.0)
        prec_mes = round(prec_dia * dias, 1)
        precip_anual += prec_mes

        rh2m = mensual(climatology.get("RH2M", {}), key, 60.0)
        gwetroot = mensual(climatology.get("GWETROOT", {}), key, 0.5)
        sw_dwn = mensual(climatology.get("ALLSKY_SFC_SW_DWN", {}), key, 5.5)
        ndvi = mensual(climatology.get("MODIS_NDVI", {}), key, 0.45)

        meses.append({
            "mes_num": idx + 1,
            "codigo": key,
            "nombre": MONTH_NAMES_ES[idx],
            "t2m": round(t2m, 1),
            "t2m_max": round(t2m_max, 1),
            "t2m_min": round(t2m_min, 1),
            "precip_mm_dia": round(prec_dia, 2),
            "precip_mm_mes": prec_mes,
            "rh2m": round(rh2m, 1),
            "gwetroot": round(gwetroot, 2),
            "radiacion_sw": round(sw_dwn, 1),
            "ndvi": round(ndvi, 2),
        })

    t2m_anual = round(sum(m["t2m"] for m in meses) / 12.0, 1)
    t2m_min_anual = round(min(m["t2m_min"] for m in meses), 1)
    t2m_max_anual = round(max(m["t2m_max"] for m in meses), 1)
    rh2m_anual = round(sum(m["rh2m"] for m in meses) / 12.0, 1)
    gwet_anual = round(sum(m["gwetroot"] for m in meses) / 12.0, 2)
    sw_anual = round(sum(m["radiacion_sw"] for m in meses) / 12.0, 1)
    ndvi_anual = round(sum(m["ndvi"] for m in meses) / 12.0, 2)

    return {
        "resumen_anual": {
            "temp_media_c": t2m_anual,
            "temp_max_extrema_c": t2m_max_anual,
            "temp_min_extrema_c": t2m_min_anual,
            "precip_anual_mm": round(precip_anual, 1),
            "humedad_relativa_media_pct": rh2m_anual,
            "humedad_suelo_media": gwet_anual,
            "radiacion_solar_media": sw_anual,
            "ndvi_medio": ndvi_anual,
        },
        "meses": meses,
    }


def compute_crop_window(
    climatology: Dict[str, Dict[str, Any]],
    mes_siembra: int,
    ciclo_dias: List[int],
) -> Dict[str, Any]:
    """
    Calcula las variables climáticas en la ventana de cultivo desde `mes_siembra` (1..12)
    hasta completar la duración media de `ciclo_dias`.
    """
    if not (1 <= mes_siembra <= 12):
        raise ValueError("mes_siembra debe estar entre 1 y 12")

    duracion_media = int(round((ciclo_dias[0] + ciclo_dias[1]) / 2.0))
    dias_restantes = duracion_media
    cur_idx = mes_siembra - 1

    peso_total_dias = 0
    suma_t2m = 0.0
    suma_t2m_max = 0.0
    min_t2m_min = float("inf")
    precip_acumulada = 0.0
    suma_rh2m = 0.0
    suma_gwet = 0.0
    meses_cubiertos: List[int] = []

    while dias_restantes > 0:
        key = MONTH_KEYS[cur_idx]
        dias_mes = DAYS_IN_MONTH[cur_idx]
        dias_en_este_mes = min(dias_restantes, dias_mes)

        t2m = mensual(climatology.get("T2M", {}), key, 18.0)
        t2m_max = mensual(climatology.get("T2M_MAX", {}), key, t2m + 5.0)
        t2m_min_raw = mensual(climatology.get("T2M_MIN", {}), key, t2m - 5.0)
        # En NASA POWER climatology/point, T2M_MIN es el récord absoluto de 30 años;
        # ponderamos con la mínima nocturna media (T2M - 6°C) cuando la amplitud supera 11.5°C
        t2m_min = (
            round(0.65 * (t2m - 6.0) + 0.35 * t2m_min_raw, 1)
            if (t2m - t2m_min_raw) > 11.5
            else t2m_min_raw
        )
        prec_dia = mensual(climatology.get("PRECTOTCORR", {}), key, 0.0)
        rh2m = mensual(climatology.get("RH2M", {}), key, 60.0)
        gwet = mensual(climatology.get("GWETROOT", {}), key, 0.5)

        suma_t2m += t2m * dias_en_este_mes
        suma_t2m_max += t2m_max * dias_en_este_mes
        if t2m_min < min_t2m_min:
            min_t2m_min = t2m_min
        precip_acumulada += prec_dia * dias_en_este_mes
        suma_rh2m += rh2m * dias_en_este_mes
        suma_gwet += gwet * dias_en_este_mes

        peso_total_dias += dias_en_este_mes
        meses_cubiertos.append(cur_idx + 1)

        dias_restantes -= dias_en_este_mes
        cur_idx = (cur_idx + 1) % 12

    return {
        "mes_siembra": mes_siembra,
        "duracion_dias": duracion_media,
        "meses_cubiertos": meses_cubiertos,
        "temp_media": round(suma_t2m / peso_total_dias, 1),
        "temp_max_media": round(suma_t2m_max / peso_total_dias, 1),
        "temp_min_extrema": round(min_t2m_min, 1),
        "precip_acumulada_mm": round(precip_acumulada, 1),
        "humedad_relativa_media": round(suma_rh2m / peso_total_dias, 1),
        "gwetroot_medio": round(suma_gwet / peso_total_dias, 2),
    }
