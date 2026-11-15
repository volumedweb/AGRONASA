from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from .climate import MONTH_NAMES_ES

LLUVIA_INTENSA_MM = 50.0
DIA_SECO_MM = 1.0
MES_SECO_FRACCION = 0.6
COBERTURA_MINIMA = 0.9


def regresion_lineal(xs: List[float], ys: List[float]) -> Optional[Dict[str, float]]:
    """Mínimos cuadrados simples: pendiente m, ordenada b y r² (None con menos de 3 puntos)."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    m = sxy / sxx
    r2 = 0.0 if syy == 0 else (sxy * sxy) / (sxx * syy)
    return {"m": m, "b": my - m * mx, "r2": r2, "n": n}


def fuerza_de_tendencia(r2: float) -> str:
    """≥0.3 clara, ≥0.1 moderada, menos: débil (domina la variación natural)."""
    return "clara" if r2 >= 0.3 else "moderada" if r2 >= 0.1 else "débil"


def _dias_del_anio(anio: int) -> int:
    return 366 if (anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)) else 365


def tendencias_de_lluvia(historial: Dict[date, float], mes: int) -> Optional[Dict[str, Any]]:
    """Tendencia de la lluvia anual y riesgos del mes elegido (mes seco, lluvia intensa) según años reales."""
    por_anio: Dict[int, List[float]] = defaultdict(list)
    por_anio_mes: Dict[int, List[float]] = defaultdict(list)
    for fecha, mm in historial.items():
        por_anio[fecha.year].append(mm)
        if fecha.month == mes:
            por_anio_mes[fecha.year].append(mm)

    anuales = {a: sum(v) for a, v in por_anio.items() if len(v) >= COBERTURA_MINIMA * _dias_del_anio(a)}
    mensuales = {a: v for a, v in por_anio_mes.items() if len(v) >= 27 * COBERTURA_MINIMA}
    ajuste = regresion_lineal(sorted(anuales), [anuales[a] for a in sorted(anuales)])
    if ajuste is None or len(mensuales) < 5:
        return None

    totales_mes = {a: sum(v) for a, v in mensuales.items()}
    media_mes = sum(totales_mes.values()) / len(totales_mes)
    anios = len(mensuales)
    secos = sum(1 for t in totales_mes.values() if t < MES_SECO_FRACCION * media_mes)
    intensos = sum(1 for v in mensuales.values() if max(v) >= LLUVIA_INTENSA_MM)
    dias_secos = sum(sum(1 for mm in v if mm < DIA_SECO_MM) / len(v) * 30 for v in mensuales.values()) / anios

    return {
        "anios": f"{min(anuales)}–{max(anuales)}",
        "n_anios": len(anuales),
        "anual": {
            "media_mm": round(sum(anuales.values()) / len(anuales)),
            "tendencia_mm_decada": round(ajuste["m"] * 10),
            "r2": round(ajuste["r2"], 2),
            "fuerza": fuerza_de_tendencia(ajuste["r2"]),
        },
        "mes": {
            "nombre": MESES_ES_MIN(mes),
            "media_mm": round(media_mes),
            "prob_mes_seco_pct": round(100 * secos / anios),
            "prob_lluvia_intensa_pct": round(100 * intensos / anios),
            "dias_secos_por_mes": round(dias_secos),
        },
        "definiciones": {
            "mes_seco": f"menos del {int(MES_SECO_FRACCION * 100)} % de la lluvia media de ese mes",
            "lluvia_intensa": f"al menos un día con {int(LLUVIA_INTENSA_MM)} mm o más",
            "dia_seco": f"menos de {DIA_SECO_MM:g} mm",
        },
    }


def MESES_ES_MIN(mes: int) -> str:
    return MONTH_NAMES_ES[mes - 1].lower()
