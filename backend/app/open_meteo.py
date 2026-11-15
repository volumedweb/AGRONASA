import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
VIGENCIA_CACHE_S = 30 * 60
HORAS_VISIBLES = 6

logger = logging.getLogger(__name__)
_CACHE: Dict[Tuple[float, float, int], Tuple[float, Dict[str, Any]]] = {}


def parsear_pronostico(respuesta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convierte la respuesta diaria de Open-Meteo en [{fecha, probabilidad_pct, mm_tipico}]."""
    diario = respuesta["daily"]
    return [
        {
            "fecha": fecha,
            "probabilidad_pct": None if prob is None else round(prob),
            "mm_tipico": 0.0 if mm is None else round(mm, 1),
        }
        for fecha, prob, mm in zip(
            diario["time"], diario["precipitation_probability_max"], diario["precipitation_sum"]
        )
    ]


def proximas_horas(
    respuesta: Dict[str, Any], ahora_utc: datetime, cantidad: int = HORAS_VISIBLES
) -> List[Dict[str, Any]]:
    """
    Las `cantidad` horas que empiezan en la hora actual del punto consultado (si son las 6,
    de 6 a 11; si son las 23, de 23 a 4 del día siguiente).
    """
    local = ahora_utc + timedelta(seconds=respuesta["utc_offset_seconds"])
    hora_actual = local.strftime("%Y-%m-%dT%H:00")
    horario = respuesta["hourly"]
    tiempos = horario["time"]
    if hora_actual not in tiempos:
        return []
    inicio = tiempos.index(hora_actual)
    horas = []
    for i in range(inicio, min(inicio + cantidad, len(tiempos))):
        prob = horario["precipitation_probability"][i]
        temp = horario["temperature_2m"][i]
        horas.append({
            "hora": tiempos[i][11:16],
            "probabilidad_pct": None if prob is None else round(prob),
            "temperatura_c": None if temp is None else round(temp),
            "es_de_dia": bool(horario["is_day"][i]),
        })
    return horas


def _pedir_pronostico(lat: float, lon: float, dias: int) -> Optional[Dict[str, Any]]:
    """Respuesta cruda de Open-Meteo (diaria + horaria), con caché de 30 min por coordenada."""
    if os.environ.get("AGRONASA_OFFLINE_ONLY", "0") == "1":
        return None

    clave = (round(lat, 2), round(lon, 2), dias)
    guardado = _CACHE.get(clave)
    if guardado and time.time() - guardado[0] < VIGENCIA_CACHE_S:
        return guardado[1]

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_probability_max,precipitation_sum",
        "hourly": "precipitation_probability,temperature_2m,is_day",
        "timezone": "auto",
        "forecast_days": max(dias, 2),
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            respuesta = r.json()
            parsear_pronostico(respuesta)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        logger.warning("Open-Meteo no disponible; se usan datos históricos de NASA", exc_info=True)
        return None

    _CACHE[clave] = (time.time(), respuesta)
    return respuesta


def get_rain_forecast(lat: float, lon: float, dias: int) -> Optional[Dict[str, Any]]:
    """Pronóstico de lluvia de Open-Meteo: {'dias': [...], 'horas': [...]}; None si no está disponible."""
    respuesta = _pedir_pronostico(lat, lon, dias)
    if respuesta is None:
        return None
    return {
        "dias": parsear_pronostico(respuesta)[:dias],
        "horas": proximas_horas(respuesta, datetime.now(timezone.utc)),
    }
