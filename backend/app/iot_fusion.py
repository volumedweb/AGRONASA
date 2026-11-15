import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .climate import format_monthly_climatology
from .nasa_client import get_climatology, round_to_nasa_grid
from .schemas import (
    IoTCameraSnapshot,
    IoTNodeStatus,
    IoTSensorMeasurements,
    IoTTelemetryInput,
    IoTTelemetryResponse,
)

# Almacén en memoria de última telemetría recibida por parcela o celda
_LATEST_IOT_TELEMETRY: Dict[str, Tuple[float, IoTTelemetryInput]] = {}
IOT_MAX_CELDAS = 200            # tope de celdas guardadas (la ingesta es pública)
IOT_VIGENCIA_S = 6 * 3600       # una lectura más vieja que esto ya no se presenta como "en vivo"

DIRECCIONES_VIENTO = ["NE", "E", "SE", "N", "NO", "SO"]


def _build_default_nodes() -> List[IoTNodeStatus]:
    return [
        IoTNodeStatus(
            id="nodo-01",
            nombre="Nodo #01 · aire + veleta",
            bateria_pct=94,
            solar=True,
            red="LoRaWAN 15 min",
            rssi_dbm=-78,
            hace_min=4,
        ),
        IoTNodeStatus(
            id="nodo-02",
            nombre="Nodo #02 · suelo norte",
            bateria_pct=88,
            solar=False,
            red="LoRaWAN 30 min",
            rssi_dbm=-89,
            hace_min=12,
        ),
        IoTNodeStatus(
            id="nodo-03",
            nombre="Nodo #03 · suelo sur",
            bateria_pct=42,
            solar=False,
            red="LoRaWAN 30 min",
            rssi_dbm=-95,
            hace_min=18,
        ),
        IoTNodeStatus(
            id="cam-01",
            nombre="Cámara fenológica",
            bateria_pct=96,
            solar=True,
            red="4G/LTE · 1 foto al día",
            rssi_dbm=-74,
            hace_min=0,
        ),
    ]


def _derive_parcel_measurements(
    lat: float, lon: float, mes_data: Dict[str, Any]
) -> IoTSensorMeasurements:
    """
    Genera lecturas de microclima de parcela coherentes con la celda NASA POWER
    cuando aún no se ha inyectado un paquete físico por POST.
    """
    nasa_t2m = float(mes_data.get("t2m", 19.0))
    nasa_tmin = float(mes_data.get("t2m_min", 8.0))
    nasa_rh = float(mes_data.get("rh2m", 55.0))
    nasa_gwet = float(mes_data.get("gwetroot", 0.45))

    # Micro-variación determinista por coordenada de parcela dentro de la celda
    seed = abs((lat * 37.0 + lon * 19.0) % 1.0)
    delta_micro = round(1.2 + (seed - 0.5) * 1.4, 1)  # típicamente +0.5 a +1.9 °C

    temp_amb = round(nasa_t2m + delta_micro, 1)
    temp_min_24h = round(nasa_tmin + delta_micro * 0.6, 1)
    hum_amb = round(max(20.0, min(95.0, nasa_rh - delta_micro * 1.8)), 0)
    temp_suelo = round(temp_amb - 2.3, 1)

    # Humedad volumétrica del suelo en % (relacionada con GWETROOT pero reflejando secado superficial)
    hum_suelo = round(max(16.0, min(88.0, nasa_gwet * 100.0 - 14.0)), 0)
    viento_vel = round(8.0 + (seed * 9.0), 0)
    viento_dir = DIRECCIONES_VIENTO[int(seed * 10) % len(DIRECCIONES_VIENTO)]

    return IoTSensorMeasurements(
        temp_ambiente_c=temp_amb,
        temp_min_24h_c=temp_min_24h,
        humedad_ambiente_pct=hum_amb,
        temp_suelo_c=temp_suelo,
        humedad_suelo_pct=hum_suelo,
        viento_velocidad_kmh=viento_vel,
        viento_direccion=viento_dir,
    )


def save_iot_telemetry(payload: IoTTelemetryInput) -> IoTTelemetryResponse:
    grid_lat, grid_lon = round_to_nasa_grid(payload.lat, payload.lon)
    key = f"{grid_lat}_{grid_lon}"
    _LATEST_IOT_TELEMETRY.pop(key, None)
    _LATEST_IOT_TELEMETRY[key] = (time.time(), payload)
    while len(_LATEST_IOT_TELEMETRY) > IOT_MAX_CELDAS:
        _LATEST_IOT_TELEMETRY.pop(next(iter(_LATEST_IOT_TELEMETRY)))
    return get_iot_telemetry_for_point(
        lat=payload.lat, lon=payload.lon, mes=payload.mes
    )


def get_iot_telemetry_for_point(
    lat: float, lon: float, mes: Optional[int] = None
) -> IoTTelemetryResponse:
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    key = f"{grid_lat}_{grid_lon}"

    clim_raw, mode, zone_name = get_climatology(lat, lon)
    formatted = format_monthly_climatology(clim_raw)
    meses = formatted["meses"]
    resumen = formatted["resumen_anual"]

    idx = ((mes or date.today().month) - 1) % 12
    mes_actual = meses[idx]

    guardado = _LATEST_IOT_TELEMETRY.get(key)
    stored = guardado[1] if guardado and time.time() - guardado[0] < IOT_VIGENCIA_S else None
    if stored:
        mediciones = stored.mediciones
        parcela_id = stored.parcela_id
        equipos = stored.equipos or _build_default_nodes()
        camara = stored.camara_fenologica
        origen = f"Telemetría LoRaWAN en vivo + {mode}"
    else:
        mediciones = _derive_parcel_measurements(lat, lon, mes_actual)
        parcela_id = f"parcela-{abs(int(grid_lat * 10))}-{abs(int(grid_lon * 10))}"
        equipos = _build_default_nodes()
        camara = None
        origen = f"Datos simulados (sin sensores conectados) + {mode}"

    nasa_t2m = float(mes_actual.get("t2m", resumen["temp_media_c"]))
    nasa_gwet_pct = round(float(mes_actual.get("gwetroot", resumen["humedad_suelo_media"])) * 100.0, 1)
    nasa_ndvi = float(mes_actual.get("ndvi", resumen["ndvi_medio"]))

    delta_t2m = round(mediciones.temp_ambiente_c - nasa_t2m, 1)
    delta_hum_suelo = round(mediciones.humedad_suelo_pct - nasa_gwet_pct, 1)

    if not camara:
        ndvi_prev = round(max(0.18, nasa_ndvi - 0.14), 2)
        ndvi_hoy = round(min(0.88, max(0.24, nasa_ndvi + 0.04)), 2)
        cob_prev = round(ndvi_prev * 100 * 0.72)
        cob_hoy = round(ndvi_hoy * 100 * 1.15)
        camara = {
            "anterior": IoTCameraSnapshot(
                fecha="Hace 20 días",
                cobertura_verde_pct=min(95, cob_prev),
                ndvi_estimado=ndvi_prev,
                etapa="Emergencia",
            ),
            "actual": IoTCameraSnapshot(
                fecha="Hoy 12:00",
                cobertura_verde_pct=min(98, cob_hoy),
                ndvi_estimado=ndvi_hoy,
                etapa="Crecimiento vigoroso" if ndvi_hoy >= 0.42 else "Desarrollo inicial",
            ),
        }

    alertas_iot: List[Dict[str, str]] = []
    if mediciones.humedad_suelo_pct < 30.0:
        alertas_iot.append(
            {
                "severidad": "aviso",
                "titulo": "Alerta de parcela · Sonda #02",
                "mensaje": (
                    f"La humedad del suelo bajó a {int(mediciones.humedad_suelo_pct)} % "
                    f"(umbral de riego: 30 %, GWETROOT satelital: {int(nasa_gwet_pct)} %). "
                    "Confirma en terreno el déficit y prioriza riego."
                ),
            }
        )
    elif mediciones.humedad_suelo_pct > 80.0:
        alertas_iot.append(
            {
                "severidad": "aviso",
                "titulo": "Suelo saturado · Sonda #02",
                "mensaje": (
                    f"Humedad en raíces al {int(mediciones.humedad_suelo_pct)} %. "
                    "Evita sobrerriego y vigila el drenaje de los surcos."
                ),
            }
        )
    else:
        alertas_iot.append(
            {
                "severidad": "ok",
                "titulo": "Humedad de parcela óptima · Sonda #02",
                "mensaje": (
                    f"Humedad del suelo en {int(mediciones.humedad_suelo_pct)} % "
                    f"(GWETROOT satelital: {int(nasa_gwet_pct)} %). Sin estrés hídrico en raíces."
                ),
            }
        )

    signo = "+" if delta_t2m >= 0 else ""
    riesgo_helada = (
        f"Alerta: mínima local de {mediciones.temp_min_24h_c} °C con riesgo de helada."
        if mediciones.temp_min_24h_c <= 2.5
        else f"Sin riesgo de helada nocturna (mín. {mediciones.temp_min_24h_c} °C)."
    )
    alertas_iot.append(
        {
            "severidad": "peligro" if mediciones.temp_min_24h_c <= 2.5 else "ok",
            "titulo": "Satélite NASA POWER + sensores",
            "mensaje": (
                f"En la celda NASA [{grid_lat}°, {grid_lon}°] la media satelital de {mes_actual['nombre'].lower()} "
                f"es {nasa_t2m} °C (GWETROOT {int(nasa_gwet_pct)} %, NDVI {nasa_ndvi}). "
                f"Tu microclima está {signo}{delta_t2m} °C respecto al satélite. {riesgo_helada}"
            ),
        }
    )

    return IoTTelemetryResponse(
        parcela_id=parcela_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        ubicacion={
            "lat": lat,
            "lon": lon,
            "celda_nasa": [grid_lat, grid_lon],
            "zona_referencia": zone_name,
        },
        mediciones=mediciones,
        fusion_nasa={
            "mes_evaluado": mes_actual["nombre"],
            "nasa_t2m_c": nasa_t2m,
            "nasa_gwetroot_pct": nasa_gwet_pct,
            "nasa_ndvi": nasa_ndvi,
            "delta_t2m_c": delta_t2m,
            "delta_humedad_suelo_pct": delta_hum_suelo,
        },
        alertas_iot=alertas_iot,
        camara_fenologica=camara,
        equipos=equipos,
        origen=origen,
    )
