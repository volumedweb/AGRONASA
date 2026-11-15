from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .climate import MONTH_KEYS, mensual

DIA_LLUVIOSO_MM = 1.0
VENTANA_DIAS = 3


def probabilidad_historica(
    historial_mm: Dict[date, float], desde: date, dias: int, anios: List[int]
) -> List[Dict[str, Any]]:
    """
    Para cada día futuro, mira los mismos días del calendario (±VENTANA_DIAS) en los años
    del historial y cuenta cuántos fueron lluviosos (>= DIA_LLUVIOSO_MM). No es un pronóstico.
    """
    resultado = []
    for i in range(dias):
        objetivo = desde + timedelta(days=i)
        muestras: List[float] = []
        for anio in anios:
            for desfase in range(-VENTANA_DIAS, VENTANA_DIAS + 1):
                try:
                    fecha = objetivo.replace(year=anio) + timedelta(days=desfase)
                except ValueError:  # 29 de febrero en un año no bisiesto
                    continue
                if fecha in historial_mm:
                    muestras.append(historial_mm[fecha])
        lluviosos = [mm for mm in muestras if mm >= DIA_LLUVIOSO_MM]
        resultado.append({
            "fecha": objetivo.isoformat(),
            "probabilidad_pct": round(100 * len(lluviosos) / len(muestras)) if muestras else None,
            "mm_tipico": round(sum(lluviosos) / len(lluviosos), 1) if lluviosos else 0.0,
        })
    return resultado


def probabilidad_estimada(climatologia: Dict[str, Any], desde: date, dias: int) -> List[Dict[str, Any]]:
    """Respaldo sin datos diarios: aproxima la fracción de días lluviosos con la lluvia media diaria del mes."""
    resultado = []
    for i in range(dias):
        objetivo = desde + timedelta(days=i)
        mm_dia = mensual(climatologia.get("PRECTOTCORR", {}), MONTH_KEYS[objetivo.month - 1], 1.5)
        fraccion_lluviosa = min(0.9, mm_dia / (mm_dia + 3.0))
        resultado.append({
            "fecha": objetivo.isoformat(),
            "probabilidad_pct": round(100 * fraccion_lluviosa),
            "mm_tipico": round(mm_dia / max(fraccion_lluviosa, 0.05), 1),
        })
    return resultado


def anios_del_historial(historial_mm: Optional[Dict[date, float]]) -> List[int]:
    return sorted({f.year for f in historial_mm}) if historial_mm else []


def acumulado_ventana(serie: Dict[date, float], fin: date, dias: int, cobertura_minima: float = 0.9) -> Optional[float]:
    """Suma de los `dias` días que terminan en `fin`; None si faltan demasiados datos."""
    valores = [serie[fin - timedelta(days=i)] for i in range(dias) if (fin - timedelta(days=i)) in serie]
    if len(valores) < cobertura_minima * dias:
        return None
    return round(sum(valores) * dias / len(valores), 1)


def acumulados_historicos(historial: Dict[date, float], fin: date, dias: int) -> List[float]:
    """Lluvia acumulada en la misma ventana del calendario (terminando el mismo día y mes) de cada año del historial."""
    resultado = []
    for anio in sorted({f.year for f in historial}):
        try:
            fin_anio = fin.replace(year=anio)
        except ValueError:  # 29 de febrero
            continue
        total = acumulado_ventana(historial, fin_anio, dias)
        if total is not None:
            resultado.append(total)
    return resultado
