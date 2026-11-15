import hmac
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .condiciones_actuales import ajustar_recomendacion, get_condiciones
from .alerts import get_alerts_for_point
from .climate import format_monthly_climatology
from .iot_fusion import get_iot_telemetry_for_point, save_iot_telemetry
from .nasa_client import DEMO_ZONES, get_climatology, get_daily_rain_history, round_to_nasa_grid
from .open_meteo import get_rain_forecast
from .tendencias import tendencias_de_lluvia
from .rain_probability import anios_del_historial, probabilidad_estimada, probabilidad_historica
from .rotation import build_crop_rotation
from .schemas import (
    ExploreRequest,
    NextCropRequest,
    IoTTelemetryInput,
    IoTTelemetryResponse,
    PointInfo,
    RecommendRequest,
    RecommendResponse,
    RotationRequest,
    RotationResponse,
)
from .guia_rotacion import cargar_guia, productos_sin_cultivo
from .siguiente_cultivo import CultivoDesconocido, armar_siguiente_cultivo, armar_solo_guia
from .scoring import generate_general_soil_observations, load_crops, recommend_crops

def _ajustar_a_hoy(recs: List[Any], mes_siembra: Optional[int], lat: float, lon: float) -> Tuple[List[Any], Optional[Dict[str, Any]]]:
    """Si se quiere sembrar este mes, corrige los puntajes con las condiciones reales de hoy (helada, suelo, agua)."""
    if mes_siembra != date.today().month:
        return recs, None
    condiciones = get_condiciones(lat, lon)
    if not condiciones:
        return recs, None
    por_id = {c["id"]: c for c in load_crops()}
    ajustadas = [ajustar_recomendacion(r, por_id[r.id], condiciones) for r in recs]
    return sorted(ajustadas, key=lambda r: r.puntaje, reverse=True), condiciones


AVISO_ORIENTATIVO = (
    "Recomendación orientativa basada en climatología regional NASA POWER (malla ~0.5° × 0.625°); "
    "no constituye pronóstico meteorológico. Consulta siempre a un técnico agrónomo local."
)

app = FastAPI(
    title="AgroNASA — Asistente Agroclimático de Siembra",
    description=(
        "API que traduce datos de observación de la Tierra de la NASA (NASA POWER + MODIS NDVI) "
        "en recomendaciones explicables de cultivos, alertas de anomalías hídricas/heladas y planes de rotación."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/health", summary="Verificar estado del servicio")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "estado": "activo", "servicio": "agronasa-backend", "version": "1.0.0"}


@app.get("/api/demo-zones")
def list_demo_zones() -> Dict[str, Any]:
    return {
        "zonas": [
            {
                "id": z["id"],
                "nombre": z["nombre"],
                "lat": z["lat"],
                "lon": z["lon"],
            }
            for z in DEMO_ZONES
        ]
    }


@app.get("/api/climate")
def api_get_climate(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
) -> Dict[str, Any]:
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    clim_raw, mode, zone_name = get_climatology(lat, lon)
    formatted = format_monthly_climatology(clim_raw)

    return {
        "punto": {
            "lat": lat,
            "lon": lon,
            "celda_nasa": [grid_lat, grid_lon],
            "zona_referencia": zone_name,
        },
        "climatologia": formatted,
        "fuente": "NASA POWER (comunidad AG) + MODIS NDVI",
        "modo_datos": mode,
        "aviso": AVISO_ORIENTATIVO,
    }


@app.get("/api/rain-probability")
def api_rain_probability(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
    dias: int = Query(7, ge=1, le=14, description="Cantidad de días a mostrar desde hoy"),
) -> Dict[str, Any]:
    pronostico = get_rain_forecast(lat, lon, dias)
    if pronostico:
        return {
            "dias": pronostico["dias"],
            "horas": pronostico["horas"],
            "base": "Pronóstico de Open-Meteo.com para estas coordenadas",
            "es_pronostico": True,
            "aviso": "Pronóstico meteorológico de Open-Meteo (CC BY 4.0); puede cambiar de un día a otro.",
        }

    hoy = date.today()
    historial = get_daily_rain_history(lat, lon)
    if historial:
        anios = anios_del_historial(historial)
        lista = probabilidad_historica(historial, hoy, dias, anios)
        base = f"Frecuencia histórica de días con lluvia en {len(anios)} años (NASA POWER diario)"
    else:
        clim_raw, _, _ = get_climatology(lat, lon)
        lista = probabilidad_estimada(clim_raw, hoy, dias)
        base = "Estimación a partir de la lluvia media mensual (sin serie diaria disponible)"
    return {
        "dias": lista,
        "horas": [],
        "base": base,
        "es_pronostico": False,
        "aviso": "Es la probabilidad habitual para esa fecha, no un pronóstico del tiempo.",
    }


@app.get("/api/field-conditions")
def api_field_conditions(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
) -> Dict[str, Any]:
    condiciones = get_condiciones(lat, lon)
    if not condiciones:
        return {"disponible": False, "aviso": "Open-Meteo no respondió; se usan solo los promedios de NASA POWER."}
    return {"disponible": True, **condiciones}


@app.get("/api/climate-trends")
def api_climate_trends(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
    mes: int = Query(default_factory=lambda: date.today().month, ge=1, le=12, description="Mes a analizar"),
) -> Dict[str, Any]:
    historial = get_daily_rain_history(lat, lon)
    resultado = tendencias_de_lluvia(historial, mes) if historial else None
    if not resultado:
        return {"disponible": False, "aviso": "No hay serie diaria de NASA POWER para este punto."}
    return {
        "disponible": True,
        **resultado,
        "fuente": "NASA POWER diario (lluvia corregida, PRECTOTCORR)",
        "aviso": "Es historia observada, no un pronóstico. Con 20 años, una tendencia débil se debe a la variación natural.",
    }


@app.get("/api/alerts")
def api_get_alerts(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
) -> Dict[str, Any]:
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    _, mode, zone_name = get_climatology(lat, lon)
    alerts = get_alerts_for_point(lat, lon)

    return {
        "punto": {
            "lat": lat,
            "lon": lon,
            "celda_nasa": [grid_lat, grid_lon],
            "zona_referencia": zone_name,
        },
        "alertas": [a.model_dump() for a in alerts],
        "fuente": "NASA POWER Diario y Climatología (comunidad AG)",
        "modo_datos": mode,
        "aviso": "Las alertas reflejan anomalías recientes frente al histórico de 20 años, no pronósticos futuros.",
    }


@app.post("/api/recommend", response_model=RecommendResponse)
def api_recommend(req: RecommendRequest) -> RecommendResponse:
    grid_lat, grid_lon = round_to_nasa_grid(req.lat, req.lon)
    clim_raw, mode, zone_name = get_climatology(req.lat, req.lon)
    alerts = get_alerts_for_point(req.lat, req.lon)

    recs = recommend_crops(
        climatology=clim_raw,
        mes_siembra=req.mes_siembra,
        categorias=req.categorias,
        suelo=req.suelo,
        alertas=alerts,
        riego=req.riego,
    )
    recs, condiciones = _ajustar_a_hoy(recs, req.mes_siembra, req.lat, req.lon)
    obs_suelo_gen = generate_general_soil_observations(req.suelo)

    return RecommendResponse(
        punto=PointInfo(
            lat=req.lat,
            lon=req.lon,
            celda_nasa=[grid_lat, grid_lon],
            zona_referencia=zone_name,
        ),
        alertas=alerts,
        observaciones_suelo_generales=obs_suelo_gen,
        recomendaciones=recs,
        condiciones=condiciones,
        fuente="NASA POWER (comunidad AG) + FAO EcoCrop",
        modo_datos=mode,
        aviso=AVISO_ORIENTATIVO,
    )


@app.get("/api/crops")
def api_get_crops(categoria: Optional[str] = Query(None, description="Filtrar por categoría")) -> Dict[str, Any]:
    crops = load_crops(categoria=categoria)
    categorias_disponibles = sorted({c["categoria"] for c in load_crops()})
    return {
        "total": len(crops),
        "categorias_disponibles": categorias_disponibles,
        "cultivos": crops,
    }


@app.post("/api/explore")
def api_explore(req: ExploreRequest) -> Dict[str, Any]:
    grid_lat, grid_lon = round_to_nasa_grid(req.lat, req.lon)
    clim_raw, mode, zone_name = get_climatology(req.lat, req.lon)
    alerts = get_alerts_for_point(req.lat, req.lon)

    categorias = [req.categoria] if req.categoria else None
    recs = recommend_crops(
        climatology=clim_raw,
        mes_siembra=req.mes_siembra,
        categorias=categorias,
        cultivos_ids=req.cultivos_ids,
        suelo=req.suelo,
        alertas=alerts,
        riego=req.riego,
    )
    recs, _ = _ajustar_a_hoy(recs, req.mes_siembra, req.lat, req.lon)

    return {
        "punto": {
            "lat": req.lat,
            "lon": req.lon,
            "celda_nasa": [grid_lat, grid_lon],
            "zona_referencia": zone_name,
        },
        "categoria_filtrada": req.categoria or "todas",
        "mes_siembra": req.mes_siembra,
        "resultados": [r.model_dump() for r in recs],
        "fuente": "NASA POWER (comunidad AG) + FAO EcoCrop",
        "modo_datos": mode,
        "aviso": AVISO_ORIENTATIVO,
    }


@app.post("/api/rotation", response_model=RotationResponse)
def api_rotation(req: RotationRequest) -> RotationResponse:
    grid_lat, grid_lon = round_to_nasa_grid(req.lat, req.lon)
    clim_raw, _, zone_name = get_climatology(req.lat, req.lon)

    rot_data = build_crop_rotation(
        climatology=clim_raw,
        mes_inicio=req.mes_inicio,
        suelo=req.suelo,
        cultivo_inicial_id=req.cultivo_inicial_id,
    )

    return RotationResponse(
        punto=PointInfo(
            lat=req.lat,
            lon=req.lon,
            celda_nasa=[grid_lat, grid_lon],
            zona_referencia=zone_name,
        ),
        observaciones_suelo=rot_data["observaciones_suelo"],
        ciclo_rotacion=rot_data["ciclo_rotacion"],
        beneficios_esperados=rot_data["beneficios_esperados"],
        aviso="Guía general de rotación agroecológica; no sustituye a un plan de manejo agronómico certificado.",
    )


@app.get(
    "/api/iot/telemetry",
    response_model=IoTTelemetryResponse,
    summary="Obtener telemetría IoT LoRaWAN fusionada con NASA POWER",
)
def api_get_iot_telemetry(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)"),
    mes: Optional[int] = Query(None, ge=1, le=12, description="Mes evaluado (1..12)"),
) -> IoTTelemetryResponse:
    return get_iot_telemetry_for_point(lat=lat, lon=lon, mes=mes)


@app.post(
    "/api/iot/telemetry",
    response_model=IoTTelemetryResponse,
    summary="Ingestar telemetría desde nodos IoT LoRaWAN o simulador externo",
)
def api_post_iot_telemetry(
    payload: IoTTelemetryInput, x_token: Optional[str] = Header(None)
) -> IoTTelemetryResponse:
    # Con AGRONASA_IOT_TOKEN definido, solo quien conoce la clave puede enviar lecturas.
    esperado = os.environ.get("AGRONASA_IOT_TOKEN")
    if esperado and not hmac.compare_digest(x_token or "", esperado):
        raise HTTPException(status_code=401, detail="Falta la clave de ingesta (cabecera X-Token).")
    return save_iot_telemetry(payload)



@app.get("/api/rotation-guide")
def api_rotation_guide() -> Dict[str, Any]:
    """Guía de rotación agrícola de Bolivia (22 productos en 3 zonas) y los productos que se pueden elegir sin estar en crops.json."""
    guia = cargar_guia()
    return {**guia, "productos_sin_cultivo": productos_sin_cultivo(guia)}


@app.post("/api/next-crop")
def api_next_crop(req: NextCropRequest) -> Dict[str, Any]:
    grid_lat, grid_lon = round_to_nasa_grid(req.lat, req.lon)
    clim_raw, mode, zone_name = get_climatology(req.lat, req.lon)
    try:
        if req.cultivo_anterior_id.startswith("guia:"):
            resultado = armar_solo_guia(clim_raw, req.cultivo_anterior_id[5:])
        else:
            resultado = armar_siguiente_cultivo(clim_raw, req.cultivo_anterior_id, req.mes_siembra, req.suelo, req.riego)
    except CultivoDesconocido:
        raise HTTPException(status_code=404, detail=f"Cultivo desconocido: {req.cultivo_anterior_id}")
    return {
        "punto": {"lat": req.lat, "lon": req.lon, "celda_nasa": [grid_lat, grid_lon], "zona_referencia": zone_name},
        **resultado,
        "modo_datos": mode,
        "aviso": AVISO_ORIENTATIVO,
    }


FRONTEND_INDEX = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist" / "index.html"


@app.get("/", include_in_schema=False)
def serve_frontend():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return JSONResponse(
        {
            "mensaje": "AgroNASA API en ejecución",
            "docs": "/docs",
            "health": "/health",
        }
    )
