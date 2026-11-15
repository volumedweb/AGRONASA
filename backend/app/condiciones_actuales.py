import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .schemas import CropRecommendation
from .scoring import score_to_label

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
VIGENCIA_CACHE_S = 30 * 60
DIAS_ATRAS = 7
DIAS_ADELANTE = 7

# Humedad volumétrica del suelo (m³/m³), orientativa: depende de la textura de cada lote.
SUELO_MUY_SECO, SUELO_SECO, SUELO_SATURADO = 0.10, 0.18, 0.40
SUELO_MUY_FRIO_C, SUELO_FRIO_C = 8.0, 12.0

logger = logging.getLogger(__name__)
_CACHE: Dict[Tuple[float, float], Tuple[float, Dict[str, Any]]] = {}
_ORDEN = {"ok": 0, "aviso": 1, "peligro": 2}


def _item(id_: str, titulo: str, valor: str, estado: str, texto: str) -> Dict[str, str]:
    return {"id": id_, "titulo": titulo, "valor": valor, "estado": estado, "texto": texto}


def _suma(valores: List[Optional[float]]) -> float:
    return sum(v for v in valores if v is not None)


def parsear_condiciones(respuesta: Dict[str, Any], ahora_utc: datetime) -> Optional[Dict[str, Any]]:
    """Resume los últimos 7 y los próximos 7 días (lluvia, helada, suelo, agua) de una respuesta de Open-Meteo."""
    local = ahora_utc + timedelta(seconds=respuesta["utc_offset_seconds"])
    diario, horario = respuesta["daily"], respuesta["hourly"]
    if local.date().isoformat() not in diario["time"]:
        return None
    hoy = diario["time"].index(local.date().isoformat())
    pasados = slice(max(0, hoy - DIAS_ATRAS), hoy)
    proximos = slice(hoy, hoy + DIAS_ADELANTE)

    lluvia_7d = _suma(diario["precipitation_sum"][pasados])
    lluvia_prox = _suma(diario["precipitation_sum"][proximos])
    et0_7d = _suma(diario["et0_fao_evapotranspiration"][pasados])
    minimas = [t for t in diario["temperature_2m_min"][proximos] if t is not None]
    tmin_prox = min(minimas) if minimas else None

    ahora = horario["time"].index(local.strftime("%Y-%m-%dT%H:00")) if local.strftime("%Y-%m-%dT%H:00") in horario["time"] else None
    if ahora is None:
        return None
    humedad_raiz = horario["soil_moisture_9_to_27cm"][ahora]
    humedad_sup = horario["soil_moisture_0_to_1cm"][ahora]
    temp_suelo = horario["soil_temperature_6cm"][ahora]
    hr_48h = [h for h in horario["relative_humidity_2m"][ahora:ahora + 48] if h is not None]
    hr_media = sum(hr_48h) / len(hr_48h) if hr_48h else None

    datos = {
        "lluvia_7d_mm": round(lluvia_7d, 1), "lluvia_prox_7d_mm": round(lluvia_prox, 1),
        "balance_7d_mm": round(lluvia_7d - et0_7d, 1), "tmin_prox_7d_c": tmin_prox,
        "humedad_suelo_raiz": humedad_raiz, "humedad_suelo_superficie": humedad_sup,
        "temp_suelo_c": temp_suelo, "humedad_aire_48h_pct": None if hr_media is None else round(hr_media),
    }
    items = _semaforo(datos)
    peor = max(items, key=lambda i: _ORDEN[i["estado"]])["estado"] if items else "ok"
    return {
        "datos": datos,
        "items": items,
        "estado": peor,
        "resumen": {"ok": "Condiciones favorables", "aviso": "Sembrar con cuidados", "peligro": "Condiciones difíciles"}[peor],
        "fuente": "Open-Meteo (modelo, no sensor en tu lote)",
    }


def _semaforo(d: Dict[str, Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []

    pasada, proxima = d["lluvia_7d_mm"], d["lluvia_prox_7d_mm"]
    if pasada < 5 and proxima < 5:
        estado, texto = "aviso", "Casi no llovió ni se espera lluvia: la siembra necesitaría riego."
    elif pasada > 100 or proxima > 100:
        estado, texto = "aviso", "Mucha lluvia: riesgo de encharcamiento y de perder semilla."
    else:
        estado, texto = "ok", "Lluvia razonable para sembrar."
    items.append(_item("lluvia", "Lluvia", f"{pasada:.0f} mm atrás · {proxima:.0f} mm adelante", estado, texto))

    raiz = d["humedad_suelo_raiz"]
    if raiz is not None:
        if raiz < SUELO_MUY_SECO:
            estado, texto = "peligro", "El suelo está muy seco a la profundidad de las raíces."
        elif raiz < SUELO_SECO:
            estado, texto = "aviso", "Suelo algo seco a la profundidad de las raíces: conviene regar."
        elif raiz > SUELO_SATURADO:
            estado, texto = "aviso", "Suelo casi saturado de agua: cuida el drenaje."
        else:
            estado, texto = "ok", "Humedad adecuada a la profundidad de las raíces."
        sup = d["humedad_suelo_superficie"]
        extra = f" · superficie {sup:.2f}" if sup is not None else ""
        items.append(_item("suelo", "Humedad del suelo", f"{raiz:.2f} m³/m³{extra}", estado, texto))

    ts = d["temp_suelo_c"]
    if ts is not None:
        if ts < SUELO_MUY_FRIO_C:
            estado, texto = "peligro", "Suelo muy frío: la mayoría de las semillas no germina bien."
        elif ts < SUELO_FRIO_C:
            estado, texto = "aviso", "Suelo fresco: germinará lento en cultivos de clima cálido."
        else:
            estado, texto = "ok", "Temperatura del suelo buena para germinar."
        items.append(_item("temp_suelo", "Temperatura del suelo", f"{ts:.0f} °C", estado, texto))

    tmin = d["tmin_prox_7d_c"]
    if tmin is not None:
        if tmin <= 0:
            estado, texto = "peligro", "Se prevé helada en los próximos 7 días."
        elif tmin <= 3:
            estado, texto = "aviso", "Noches muy frías en los próximos 7 días: riesgo de helada ligera."
        else:
            estado, texto = "ok", "Sin riesgo de helada en los próximos 7 días."
        items.append(_item("helada", "Mínima próxima semana", f"{tmin:.0f} °C", estado, texto))

    balance = d["balance_7d_mm"]
    if balance < -20:
        estado, texto = "aviso", "En la última semana el suelo perdió más agua de la que recibió: riega."
    else:
        estado, texto = "ok", "El agua recibida cubre lo que perdió el suelo."
    items.append(_item("balance", "Balance de agua (7 días)", f"{balance:+.0f} mm", estado, texto))

    hr = d["humedad_aire_48h_pct"]
    if hr is not None:
        if hr >= 85:
            estado, texto = "aviso", "Aire muy húmedo: vigila hongos."
        else:
            estado, texto = "ok", "Humedad del aire sin riesgo especial de hongos."
        items.append(_item("hongos", "Humedad del aire (48 h)", f"{hr} %", estado, texto))
    return items


def get_condiciones(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Condiciones reales de los últimos y próximos 7 días en las coordenadas; None si Open-Meteo no responde."""
    if os.environ.get("AGRONASA_OFFLINE_ONLY", "0") == "1":
        return None
    clave = (round(lat, 2), round(lon, 2))
    guardado = _CACHE.get(clave)
    ahora_utc = datetime.now(timezone.utc)
    if guardado and time.time() - guardado[0] < VIGENCIA_CACHE_S:
        return parsear_condiciones(guardado[1], ahora_utc)

    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "past_days": DIAS_ATRAS, "forecast_days": DIAS_ADELANTE + 1,
        "daily": "temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
        "hourly": "soil_moisture_0_to_1cm,soil_moisture_9_to_27cm,soil_temperature_6cm,relative_humidity_2m",
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            respuesta = r.json()
            resultado = parsear_condiciones(respuesta, ahora_utc)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        logger.warning("Open-Meteo (condiciones de siembra) no disponible", exc_info=True)
        return None
    _CACHE[clave] = (time.time(), respuesta)
    return resultado


def ajustar_recomendacion(rec: CropRecommendation, crop: Dict[str, Any], condiciones: Dict[str, Any]) -> CropRecommendation:
    """Baja el puntaje de quien sembraría hoy en condiciones que el cultivo no tolera (helada, suelo frío, seco o saturado)."""
    d = condiciones["datos"]
    cambios: List[Tuple[int, str]] = []
    tmin, ts, raiz = d["tmin_prox_7d_c"], d["temp_suelo_c"], d["humedad_suelo_raiz"]

    if tmin is not None and crop.get("sensible_helada") and tmin <= crop["temp_min_helada"]:
        cambios.append((-25, f"se prevé una mínima de {tmin:.0f} °C y {crop['nombre']} se daña por debajo de {crop['temp_min_helada']} °C"))
    if ts is not None and ts < crop["temp"]["abs_min"]:
        cambios.append((-20, f"el suelo está a {ts:.0f} °C, más frío de lo que tolera para crecer ({crop['temp']['abs_min']} °C)"))
    if raiz is not None and raiz < SUELO_SECO and d["lluvia_prox_7d_mm"] < 10 and crop.get("tolerancia_sequia") != "alta":
        cambios.append((-10, "el suelo está seco y casi no se espera lluvia: necesitará riego"))
    if raiz is not None and raiz > SUELO_SATURADO and crop["suelo"]["drenaje"] == ["bueno"]:
        cambios.append((-8, "el suelo está saturado y este cultivo necesita buen drenaje"))

    if not cambios or rec.puntaje <= 0:
        return rec
    puntaje = max(0, rec.puntaje + sum(p for p, _ in cambios))
    motivos = "; ".join(m for _, m in cambios)
    previo = f"{rec.ajuste_riesgo} · " if rec.ajuste_riesgo else ""
    return rec.model_copy(update={
        "puntaje": puntaje,
        "etiqueta": score_to_label(puntaje),
        "ajuste_riesgo": f"{previo}{sum(p for p, _ in cambios)} pts por las condiciones de hoy: {motivos}",
        "explicacion": f"{rec.explicacion} Hoy: {motivos}.",
    })
