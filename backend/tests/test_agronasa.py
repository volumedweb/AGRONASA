import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["AGRONASA_OFFLINE_ONLY"] = "1"

from app.alerts import classify_precip_percentile, compute_percentile
from app.climate import compute_crop_window
from app.main import app
from app.nasa_client import clean_nasa_series, get_climatology, round_to_nasa_grid
from app.rotation import build_crop_rotation
from app.schemas import SoilInput
from app.scoring import trapezoid

client = TestClient(app)


def test_trapezoid_function():
    # Fuera de límites absolutos -> 0.0
    assert trapezoid(8.0, 10.0, 20.0, 30.0, 38.0) == 0.0
    assert trapezoid(40.0, 10.0, 20.0, 30.0, 38.0) == 0.0
    # En límites exactos -> 0.0
    assert trapezoid(10.0, 10.0, 20.0, 30.0, 38.0) == 0.0
    assert trapezoid(38.0, 10.0, 20.0, 30.0, 38.0) == 0.0
    # Dentro de rango óptimo -> 1.0
    assert trapezoid(25.0, 10.0, 20.0, 30.0, 38.0) == 1.0
    assert trapezoid(20.0, 10.0, 20.0, 30.0, 38.0) == 1.0
    assert trapezoid(30.0, 10.0, 20.0, 30.0, 38.0) == 1.0
    # Tramos lineales intermedios
    assert pytest.approx(trapezoid(15.0, 10.0, 20.0, 30.0, 38.0), 0.01) == 0.5
    assert pytest.approx(trapezoid(34.0, 10.0, 20.0, 30.0, 38.0), 0.01) == 0.5


def test_nasa_grid_and_missing_values():
    g_lat, g_lon = round_to_nasa_grid(-17.39, -66.28)
    assert g_lat == -17.5
    assert g_lon == -66.25

    cleaned = clean_nasa_series({"JAN": 21.4, "FEB": -999, "MAR": -999.0})
    assert cleaned["JAN"] == 21.4
    assert cleaned["FEB"] is None
    assert cleaned["MAR"] is None


def test_crop_window_calculation():
    clim, _, _ = get_climatology(-17.39, -66.28, allow_network=False)
    win = compute_crop_window(clim, mes_siembra=10, ciclo_dias=[90, 150])
    assert win["duracion_dias"] == 120
    assert win["mes_siembra"] == 10
    assert 12.0 <= win["temp_media"] <= 22.0
    assert win["precip_acumulada_mm"] > 200.0


def test_percentiles_and_alert_classification():
    hist = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    p_low = compute_percentile(5, hist)
    assert p_low < 10.0
    assert classify_precip_percentile(p_low)[0] == "sequia_severa"

    p_def = compute_percentile(20, hist)
    assert 10.0 <= p_def < 25.0
    assert classify_precip_percentile(p_def)[0] == "deficit_lluvia"

    p_norm = compute_percentile(55, hist)
    assert 25.0 <= p_norm <= 75.0
    assert classify_precip_percentile(p_norm)[0] == "normal"

    p_exc = compute_percentile(85, hist)
    assert 75.0 < p_exc <= 90.0
    assert classify_precip_percentile(p_exc)[0] == "exceso_lluvia"

    p_ext = compute_percentile(120, hist)
    assert p_ext > 90.0
    assert classify_precip_percentile(p_ext)[0] == "exceso_extremo"


def test_rotation_rules():
    clim, _, _ = get_climatology(-17.39, -66.28, allow_network=False)
    suelo = SoilInput(
        ph=5.8,
        textura="franco",
        materia_organica_pct=1.8,
        nitrogeno="bajo",
        drenaje="bueno",
    )
    rot = build_crop_rotation(clim, mes_inicio=10, suelo=suelo, cultivo_inicial_id="maiz")
    steps = rot["ciclo_rotacion"]
    assert len(steps) == 4
    # Ciclo 1 es maíz
    assert steps[0].id_cultivo == "maiz"
    # No se repite familia botánica en ciclos consecutivos
    for i in range(len(steps) - 1):
        assert steps[i].familia != steps[i + 1].familia
    # Ciclo 2 debe ser una leguminosa (fabaceas)
    assert steps[1].familia == "fabaceas"
    # Ciclo 4 incluye abono verde
    assert steps[3].id_cultivo == "abono_verde"


def test_reference_zones_integration():
    # 1. Altiplano (La Paz): Quinua, Haba o Papa deben liderar; Plátano debe ser 0
    r_alt = client.post(
        "/api/recommend",
        json={"lat": -16.50, "lon": -68.15, "mes_siembra": 10},
    )
    assert r_alt.status_code == 200
    data_alt = r_alt.json()
    top_ids_alt = [c["id"] for c in data_alt["recomendaciones"][:3]]
    assert any(cid in top_ids_alt for cid in ("quinua", "haba", "papa"))
    platano_alt = next(c for c in data_alt["recomendaciones"] if c["id"] == "platano")
    assert platano_alt["puntaje"] == 0

    # 2. Llanos Tropicales (Santa Cruz): Soya, Maíz, Yuca, Maní deben tener puntajes altos
    r_tro = client.post(
        "/api/recommend",
        json={"lat": -17.78, "lon": -63.18, "mes_siembra": 11},
    )
    assert r_tro.status_code == 200
    data_tro = r_tro.json()
    top_ids_tro = [c["id"] for c in data_tro["recomendaciones"][:5]]
    assert any(cid in top_ids_tro for cid in ("soya", "maiz", "yuca", "mani", "arroz"))

    # 3. Valles (Cochabamba): Maíz, Frijol, Tomate, Cebolla, Zanahoria viables
    r_val = client.post(
        "/api/recommend",
        json={
            "lat": -17.39,
            "lon": -66.28,
            "mes_siembra": 10,
            "suelo": {"ph": 6.4, "textura": "franco", "drenaje": "bueno"},
        },
    )
    assert r_val.status_code == 200
    data_val = r_val.json()
    assert data_val["recomendaciones"][0]["puntaje"] >= 65


def test_all_api_endpoints():
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert "AgroNASA" in r_root.text
    assert client.get("/health").status_code == 200
    assert client.get("/api/climate?lat=-17.39&lon=-66.28").status_code == 200
    assert client.get("/api/alerts?lat=-17.39&lon=-66.28").status_code == 200
    assert client.get("/api/crops?categoria=cereales").status_code == 200
    assert (
        client.post(
            "/api/explore",
            json={"lat": -17.39, "lon": -66.28, "categoria": "hortalizas", "mes_siembra": 10},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/rotation",
            json={
                "lat": -17.39,
                "lon": -66.28,
                "mes_inicio": 10,
                "cultivo_inicial_id": "maiz",
                "suelo": {"ph": 6.0, "textura": "franco", "drenaje": "bueno"},
            },
        ).status_code
        == 200
    )


def test_zero_values_are_not_treated_as_missing():
    from app.climate import format_monthly_climatology, mensual

    assert mensual({"JAN": 0.0}, "JAN", 18.0) == 0.0
    assert mensual({}, "JAN", 18.0) == 18.0

    clim = {k: {m: 0.0 for m in ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]}
            for k in ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "GWETROOT", "ALLSKY_SFC_SW_DWN", "MODIS_NDVI"]}
    enero = format_monthly_climatology(clim)["meses"][0]
    assert enero["t2m"] == 0.0 and enero["t2m_min"] == 0.0 and enero["gwetroot"] == 0.0


def test_network_failure_falls_back_and_logs(monkeypatch, caplog, tmp_path):
    import httpx
    from app import nasa_client

    monkeypatch.delenv("AGRONASA_OFFLINE_ONLY", raising=False)
    monkeypatch.setattr(nasa_client, "_MEMORY_CACHE", {})
    monkeypatch.setattr(nasa_client, "CACHE_DIR", tmp_path)

    def boom(*args, **kwargs):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(nasa_client.httpx.Client, "get", boom)
    with caplog.at_level("WARNING"):
        data, mode, _ = get_climatology(-5.0, -50.0)
    assert "T2M" in data and "NASA POWER" in mode
    assert any("no disponible" in r.message for r in caplog.records)


def test_rain_probability_from_history_and_estimate():
    from datetime import date
    from app.rain_probability import probabilidad_estimada, probabilidad_historica

    # 2 años: el 10 de enero llovió 5 mm en ambos; el resto del tiempo, 0 mm
    historial = {}
    for anio in (2022, 2023):
        for d in range(1, 21):
            historial[date(anio, 1, d)] = 5.0 if d == 10 else 0.0
    dia = probabilidad_historica(historial, date(2025, 1, 10), 1, [2022, 2023])[0]
    # ventana ±3 días = 7 muestras por año, 1 lluviosa → 2 de 14
    assert dia["probabilidad_pct"] == 14 and dia["mm_tipico"] == 5.0

    sin_datos = probabilidad_historica({}, date(2025, 1, 10), 1, [])[0]
    assert sin_datos["probabilidad_pct"] is None

    clim = {"PRECTOTCORR": {k: 0.0 for k in ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]}}
    assert probabilidad_estimada(clim, date(2025, 7, 1), 2)[0]["probabilidad_pct"] == 0


def test_rain_probability_endpoint_offline():
    res = client.get("/api/rain-probability", params={"lat": -17.39, "lon": -66.28, "dias": 5})
    assert res.status_code == 200
    body = res.json()
    assert len(body["dias"]) == 5 and all(0 <= d["probabilidad_pct"] <= 100 for d in body["dias"])
    assert client.get("/api/rain-probability", params={"lat": 0, "lon": 0, "dias": 30}).status_code == 422


def test_open_meteo_parsing_and_offline_mode():
    from app.open_meteo import get_rain_forecast, parsear_pronostico

    respuesta = {"daily": {
        "time": ["2026-11-14", "2026-11-15"],
        "precipitation_probability_max": [23, None],
        "precipitation_sum": [0.8, None],
    }}
    dias = parsear_pronostico(respuesta)
    assert dias[0] == {"fecha": "2026-11-14", "probabilidad_pct": 23, "mm_tipico": 0.8}
    assert dias[1]["probabilidad_pct"] is None and dias[1]["mm_tipico"] == 0.0
    assert get_rain_forecast(-17.39, -66.28, 7) is None  # los tests corren en modo sin red


def test_rain_endpoint_prefers_open_meteo_forecast(monkeypatch):
    from app import main

    falso = {"dias": [{"fecha": "2026-11-14", "probabilidad_pct": 80, "mm_tipico": 5.0}], "horas": []}
    monkeypatch.setattr(main, "get_rain_forecast", lambda lat, lon, dias: falso)
    body = client.get("/api/rain-probability", params={"lat": -17.39, "lon": -66.28, "dias": 1}).json()
    assert body["es_pronostico"] is True and body["dias"] == falso["dias"]


def test_next_six_hours_roll_with_local_time_and_cross_midnight():
    from datetime import datetime, timezone
    from app.open_meteo import proximas_horas

    tiempos = [f"2026-11-{14 + d}T{h:02d}:00" for d in (0, 1) for h in range(24)]
    resp = {
        "utc_offset_seconds": -4 * 3600,
        "hourly": {
            "time": tiempos,
            "precipitation_probability": list(range(48)),
            "temperature_2m": [20.4] * 48,
            "is_day": [1] * 48,
        },
    }
    ahora = datetime(2026, 11, 15, 3, 30, tzinfo=timezone.utc)  # 23:30 del 14 en UTC-4
    horas = proximas_horas(resp, ahora)
    assert [h["hora"] for h in horas] == ["23:00", "00:00", "01:00", "02:00", "03:00", "04:00"]
    assert horas[0]["probabilidad_pct"] == 23 and horas[0]["temperatura_c"] == 20

    seis = proximas_horas(resp, datetime(2026, 11, 14, 10, 5, tzinfo=timezone.utc))  # 06:05 local
    assert [h["hora"] for h in seis] == ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00"]
    assert proximas_horas(resp, datetime(2030, 1, 1, tzinfo=timezone.utc)) == []


def test_iot_telemetry_get_and_post_fusion():
    # 1. GET telemetría derivada de la celda NASA POWER
    r_get = client.get("/api/iot/telemetry", params={"lat": -17.39, "lon": -66.28, "mes": 10})
    assert r_get.status_code == 200
    assert r_get.headers.get("X-Content-Type-Options") == "nosniff"
    data_get = r_get.json()
    assert "mediciones" in data_get
    assert "fusion_nasa" in data_get
    assert data_get["ubicacion"]["celda_nasa"] == [-17.5, -66.25]

    # 2. POST telemetría en vivo desde nodo LoRaWAN / simulador externo
    payload = {
        "parcela_id": "parcela-cochabamba-01",
        "lat": -17.39,
        "lon": -66.28,
        "mes": 10,
        "mediciones": {
            "temp_ambiente_c": 22.4,
            "temp_min_24h_c": 8.4,
            "humedad_ambiente_pct": 54.0,
            "temp_suelo_c": 18.9,
            "humedad_suelo_pct": 26.0,
            "viento_velocidad_kmh": 11.0,
            "viento_direccion": "NE",
        },
    }
    r_post = client.post("/api/iot/telemetry", json=payload)
    assert r_post.status_code == 200
    data_post = r_post.json()
    assert data_post["parcela_id"] == "parcela-cochabamba-01"
    assert data_post["mediciones"]["humedad_suelo_pct"] == 26.0
    assert any(a["severidad"] == "aviso" for a in data_post["alertas_iot"])



def test_next_crop_uses_previous_crop_traits_without_soil_data():
    from app.siguiente_cultivo import armar_siguiente_cultivo

    clim, _, _ = get_climatology(-17.39, -66.28)
    tras_maiz = armar_siguiente_cultivo(clim, "maiz", 10)
    assert tras_maiz["anterior"]["demanda_nitrogeno"] == "alta" and "pH" in tras_maiz["nota"]
    primeras = tras_maiz["sugerencias"][:3]
    assert primeras and all(s["familia"] != "gramineas" for s in tras_maiz["sugerencias"])
    assert any(s["familia"] == "fabaceas" for s in primeras)  # cultivo exigente → leguminosa

    tras_haba = armar_siguiente_cultivo(clim, "haba", 10)
    assert all(s["familia"] != "fabaceas" for s in tras_haba["sugerencias"])
    assert any("nitrógeno que dejó" in " ".join(s["motivos"]) for s in tras_haba["sugerencias"])

    plan = tras_maiz["ciclo_rotacion"]
    assert [p["ciclo"] for p in plan] == [1, 2, 3] and plan[-1]["id_cultivo"] == "abono_verde"
    familias = [p["familia"] for p in plan[:-1]]
    assert len(set(familias)) == len(familias) and "gramineas" not in familias

    permanente = armar_siguiente_cultivo(clim, "platano", 10)
    assert permanente["ciclo_rotacion"] == [] and all(s["id"] in {"soya", "frijol", "haba", "mani"} for s in permanente["sugerencias"])


def test_next_crop_endpoint_and_unknown_crop():
    ok = client.post("/api/next-crop", json={"lat": -17.39, "lon": -66.28, "cultivo_anterior_id": "papa", "mes_siembra": None})
    assert ok.status_code == 200 and ok.json()["sugerencias"]
    assert client.post("/api/next-crop", json={"lat": -17.39, "lon": -66.28, "cultivo_anterior_id": "marte"}).status_code == 404
    assert client.post("/api/next-crop", json={"lat": -17.39, "lon": -66.28, "cultivo_anterior_id": "maiz", "mes_siembra": 13}).status_code == 422


def test_next_crop_suggestions_carry_guide_labels():
    from app.siguiente_cultivo import armar_siguiente_cultivo

    clim, _, _ = get_climatology(-17.39, -66.28)
    r = armar_siguiente_cultivo(clim, "papa", None)
    assert all({"color", "icono", "texto"} <= set(t) for t in r["anterior"]["etiquetas"])
    por_id = {s["id"]: s for s in r["sugerencias"]}
    assert all(s["etiquetas"] for s in r["sugerencias"])  # impacto en el suelo del cultivo sugerido
    legumbres = [s for s in r["sugerencias"] if s["familia"] == "fabaceas"]
    assert legumbres and all(any(b["texto"] == "Fijador de Nitrógeno" for b in s["beneficios"]) for s in legumbres)
    assert all(any(b["texto"] == "Corte de Plagas" for b in s["beneficios"]) for s in r["sugerencias"])  # papa: riesgo sanitario

    platano = armar_siguiente_cultivo(clim, "platano", 11)
    assert platano["sugerencias"] and {b["texto"] for b in platano["sugerencias"][0]["beneficios"]} >= {"Fijador de Nitrógeno", "Control de Erosión"}


def test_after_seasonal_crop_no_permanent_and_guide_by_zone():
    from app.siguiente_cultivo import armar_siguiente_cultivo

    llanos, _, _ = get_climatology(-17.78, -63.18)
    tras_soya = armar_siguiente_cultivo(llanos, "soya", None)
    ids = [s["id"] for s in tras_soya["sugerencias"]]
    assert "citricos" not in ids and "platano" not in ids
    assert ids[:2] == ["maiz", "girasol"] or set(ids[:2]) == {"maiz", "girasol"}  # lo que dice la guía para los Llanos
    guiados = [s for s in tras_soya["sugerencias"] if s["id"] in {"maiz", "girasol"}]
    assert all("guía de rotación" in s["motivos"][0] for s in guiados)
    assert all(any(b["texto"] == "Generador de Biomasa" for b in s["beneficios"]) for s in guiados)
    assert tras_soya["zona"] == "Llanos y trópico"
    assert all(s["id"] not in {"citricos", "platano"} for p in tras_soya["ciclo_rotacion"] for s in [{"id": p["id_cultivo"]}])

    altiplano, _, _ = get_climatology(-16.5, -68.15)
    assert armar_siguiente_cultivo(altiplano, "papa", None)["sugerencias"][0]["id"] == "quinua"


def test_real_window_sums_and_yearly_history():
    from datetime import date, timedelta
    from app.rain_probability import acumulado_ventana, acumulados_historicos

    historial = {}
    for anio in (2023, 2024, 2025):
        for i in range(0, 90):
            historial[date(anio, 9, 1) + timedelta(days=i)] = float(anio - 2022)  # 1, 2, 3 mm/día
    fin = date(2025, 10, 15)
    assert acumulado_ventana(historial, fin, 30) == 90.0
    assert acumulado_ventana(historial, date(2025, 12, 25), 30) is None  # sin cobertura suficiente
    assert acumulados_historicos(historial, date(2026, 10, 15), 30) == [30.0, 60.0, 90.0]


def test_alert_message_says_when_data_is_estimated_or_real():
    from app.alerts import evaluate_alerts_from_data

    base = {"precip_30d_actual": 50.0, "precip_30d_hist": [40.0 + i for i in range(20)],
            "precip_60d_actual": 90.0, "precip_60d_hist": [80.0 + i for i in range(20)],
            "gwetroot_recent": 0.5, "t2m_min_recent": 9.0}
    estimado = evaluate_alerts_from_data({**base, "estimado": True})[0].mensaje
    real = evaluate_alerts_from_data({**base, "estimado": False, "hasta": "2026-11-12"})[0].mensaje
    assert "Estimación" in estimado and "hasta el 12/11" in real


def _respuesta_open_meteo(tmin=12.0, humedad_raiz=0.27, temp_suelo=19.0, lluvia=3.0):
    dias = [f"2026-11-{d:02d}" for d in range(8, 23)]
    horas = [f"{d}T{h:02d}:00" for d in dias for h in range(24)]
    return {
        "utc_offset_seconds": -4 * 3600,
        "daily": {
            "time": dias,
            "temperature_2m_min": [tmin] * len(dias),
            "precipitation_sum": [lluvia] * len(dias),
            "et0_fao_evapotranspiration": [4.0] * len(dias),
        },
        "hourly": {
            "time": horas,
            "soil_moisture_0_to_1cm": [0.06] * len(horas),
            "soil_moisture_9_to_27cm": [humedad_raiz] * len(horas),
            "soil_temperature_6cm": [temp_suelo] * len(horas),
            "relative_humidity_2m": [70] * len(horas),
        },
    }


def test_field_conditions_semaphore_and_crop_adjustment():
    from datetime import datetime, timezone
    from app.condiciones_actuales import ajustar_recomendacion, parsear_condiciones
    from app.scoring import evaluate_crop_for_month, load_crops

    ahora = datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)  # 12:00 hora local
    buenas = parsear_condiciones(_respuesta_open_meteo(), ahora)
    assert buenas["estado"] == "ok" and buenas["datos"]["lluvia_7d_mm"] == 21.0  # 7 días × 3 mm
    assert {i["id"] for i in buenas["items"]} >= {"lluvia", "suelo", "temp_suelo", "helada", "balance"}

    malas = parsear_condiciones(_respuesta_open_meteo(tmin=-2.0, humedad_raiz=0.05, temp_suelo=6.0, lluvia=0.0), ahora)
    estados = {i["id"]: i["estado"] for i in malas["items"]}
    assert malas["estado"] == "peligro" and estados["helada"] == "peligro" and estados["suelo"] == "peligro"
    assert parsear_condiciones(_respuesta_open_meteo(), datetime(2030, 1, 1, tzinfo=timezone.utc)) is None

    clim, _, _ = get_climatology(-17.39, -66.28)
    maiz = next(c for c in load_crops() if c["id"] == "tomate")  # sensible a heladas y con puntaje > 0 en este valle
    mejor_mes = max(range(1, 13), key=lambda m: evaluate_crop_for_month(maiz, clim, m).puntaje)
    base = evaluate_crop_for_month(maiz, clim, mejor_mes)
    assert base.puntaje > 0
    sin_cambio = ajustar_recomendacion(base, maiz, buenas)
    con_helada = ajustar_recomendacion(base, maiz, malas)
    assert sin_cambio.puntaje == base.puntaje
    assert con_helada.puntaje < base.puntaje and "condiciones de hoy" in con_helada.ajuste_riesgo


def test_field_conditions_endpoint_offline():
    body = client.get("/api/field-conditions", params={"lat": -17.39, "lon": -66.28}).json()
    assert body["disponible"] is False


def test_irrigation_raises_score_where_rain_is_short():
    from app.scoring import evaluate_crop_for_month, load_crops

    clim, _, _ = get_climatology(-17.39, -66.28)  # valle seco: casi todo sale en 0 sin riego
    tomate = next(c for c in load_crops() if c["id"] == "tomate")
    mejor_mes = max(range(1, 13), key=lambda m: evaluate_crop_for_month(tomate, clim, m).puntaje)
    secano = evaluate_crop_for_month(tomate, clim, mejor_mes, riego="secano")
    limitado = evaluate_crop_for_month(tomate, clim, mejor_mes, riego="limitado")
    completo = evaluate_crop_for_month(tomate, clim, mejor_mes, riego="completo")
    assert secano.puntaje == evaluate_crop_for_month(tomate, clim, mejor_mes).puntaje  # sin riego = secano
    assert secano.puntaje <= limitado.puntaje <= completo.puntaje and completo.puntaje > secano.puntaje
    assert "Con riego completo" in completo.explicacion

    maiz = next(c for c in load_crops() if c["id"] == "maiz")
    assert max(evaluate_crop_for_month(maiz, clim, m).puntaje for m in range(1, 13)) == 0
    assert max(evaluate_crop_for_month(maiz, clim, m, riego="completo").puntaje for m in range(1, 13)) > 0

    r = client.post("/api/recommend", json={"lat": -17.39, "lon": -66.28, "mes_siembra": 10, "riego": "completo"})
    assert r.status_code == 200
    assert client.post("/api/recommend", json={"lat": -17.39, "lon": -66.28, "riego": "mucho"}).status_code == 422


def test_linear_trend_and_rain_risks_from_daily_history():
    from datetime import date, timedelta
    from app.tendencias import fuerza_de_tendencia, regresion_lineal, tendencias_de_lluvia

    ajuste = regresion_lineal([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert round(ajuste["m"], 6) == 2.0 and round(ajuste["r2"], 6) == 1.0
    assert regresion_lineal([1, 2], [1, 2]) is None
    assert [fuerza_de_tendencia(x) for x in (0.5, 0.2, 0.05)] == ["clara", "moderada", "débil"]

    historial = {}
    for anio in range(2006, 2026):
        dia = date(anio, 1, 1)
        while dia.year == anio:
            historial[dia] = 2.0  # 2 mm todos los días → 730 mm al año
            dia += timedelta(days=1)
        # octubre muy seco en 5 de los 20 años y con un día de 60 mm en 4 años
        if anio < 2011:
            for d in range(1, 32):
                historial[date(anio, 10, d)] = 0.0
        if anio >= 2022:
            historial[date(anio, 10, 15)] = 60.0
    r = tendencias_de_lluvia(historial, 10)
    assert r["n_anios"] == 20 and r["anual"]["tendencia_mm_decada"] > 0  # los años secos son los primeros
    assert r["mes"]["prob_mes_seco_pct"] == 25 and r["mes"]["prob_lluvia_intensa_pct"] == 20
    assert tendencias_de_lluvia({date(2020, 1, 1): 1.0}, 10) is None

    body = client.get("/api/climate-trends", params={"lat": -17.39, "lon": -66.28, "mes": 10}).json()
    assert body["disponible"] is False  # modo sin red
    assert client.get("/api/climate-trends", params={"lat": -17.39, "lon": -66.28, "mes": 13}).status_code == 422


def test_next_crop_confidence_grows_with_data():
    from app.schemas import SoilInput
    from app.siguiente_cultivo import armar_siguiente_cultivo

    llanos, _, _ = get_climatology(-17.78, -63.18)
    pobre = armar_siguiente_cultivo(llanos, "soya", None)["confianza"]
    rico = armar_siguiente_cultivo(
        llanos, "soya", None,
        SoilInput(ph=6.5, materia_organica_pct=3.0, textura="franco", nitrogeno="medio", fosforo="medio", potasio="alto", pendiente_pct=2.0),
        "limitado",
    )["confianza"]
    assert 10 <= pobre["puntos"] < rico["puntos"] <= 95
    assert rico["etiqueta"] == "Alta" and pobre["etiqueta"] != "Alta" and len(rico["por_que"]) >= 3


def test_review_fixes_irrigation_percentiles_and_legume_rotation():
    from app.alerts import compute_percentile, evaluate_alerts_from_data
    from app.scoring import evaluate_crop_for_month, load_crops
    from app.schemas import SoilInput

    # el riego no compensa el exceso de lluvia (solo la falta)
    from app.climate import compute_crop_window

    llanos, _, _ = get_climatology(-17.78, -63.18)
    casos = [(c, m) for c in load_crops() for m in range(1, 13)
             if compute_crop_window(llanos, m, c["ciclo_dias"])["precip_acumulada_mm"] > c["precip_ciclo_mm"]["opt_max"]]
    assert casos, "los Llanos deberían tener algún cultivo con exceso de lluvia"
    for crop, mes in casos:
        base = evaluate_crop_for_month(crop, llanos, mes).factores["precipitacion"]
        assert evaluate_crop_for_month(crop, llanos, mes, riego="completo").factores["precipitacion"] == base

    # historia plana (temporada seca): ni sequía ni inundación
    assert compute_percentile(0.0, [0.0] * 20) == 50.0
    seca = {"precip_30d_actual": 0.0, "precip_30d_hist": [0.0] * 20, "precip_60d_actual": 0.0, "precip_60d_hist": [0.0] * 20,
            "gwetroot_recent": 0.3, "t2m_min_recent": 5.0}
    assert all(a.tipo in ("normal",) for a in evaluate_alerts_from_data(seca))
    # una estimación se marca y no ajusta puntajes
    est = evaluate_alerts_from_data({**seca, "estimado": True, "t2m_min_recent": -1.0})
    assert all(a.estimado for a in est) and any("Estimación" in a.mensaje for a in est if a.tipo == "riesgo_helada")

    # rotación que empieza con una leguminosa ya no falla
    for inicial in ("soya", "frijol", "haba", "mani"):
        r = client.post("/api/rotation", json={"lat": -17.39, "lon": -66.28, "mes_inicio": 10, "cultivo_inicial_id": inicial, "suelo": {}})
        assert r.status_code == 200, inicial
        assert len(r.json()["ciclo_rotacion"]) == 4


def test_iot_ingest_token_staleness_and_cache_bounds(monkeypatch):
    from app import iot_fusion, nasa_client

    cuerpo = {"parcela_id": "p1", "lat": -17.39, "lon": -66.28, "mes": 10,
              "mediciones": {"temp_ambiente_c": 20, "temp_min_24h_c": 8, "humedad_ambiente_pct": 50, "temp_suelo_c": 18,
                             "humedad_suelo_pct": 12, "viento_velocidad_kmh": 5, "viento_direccion": "NE"}}
    monkeypatch.setenv("AGRONASA_IOT_TOKEN", "clave")
    assert client.post("/api/iot/telemetry", json=cuerpo).status_code == 401
    assert client.post("/api/iot/telemetry", json=cuerpo, headers={"X-Token": "mala"}).status_code == 401
    assert client.post("/api/iot/telemetry", json=cuerpo, headers={"X-Token": "clave"}).status_code == 200
    monkeypatch.delenv("AGRONASA_IOT_TOKEN")

    # una lectura vieja deja de presentarse como "en vivo"
    clave = next(iter(iot_fusion._LATEST_IOT_TELEMETRY))
    if clave:
        t, dato = iot_fusion._LATEST_IOT_TELEMETRY[clave]
        iot_fusion._LATEST_IOT_TELEMETRY[clave] = (t - iot_fusion.IOT_VIGENCIA_S - 1, dato)
        r = client.get("/api/iot/telemetry", params={"lat": -17.39, "lon": -66.28, "mes": 10}).json()
        assert "simulados" in r["origen"]

    # la caché en memoria tiene tope
    monkeypatch.setattr(nasa_client, "_MEMORY_CACHE_MAX", 3)
    for i in range(10):
        nasa_client._cache_set(f"k{i}", i)
    assert len(nasa_client._MEMORY_CACHE) <= 3 and "k9" in nasa_client._MEMORY_CACHE


def test_rotation_guide_is_complete_shown_and_in_sync_with_markdown():
    from pathlib import Path
    from app.guia_rotacion import RUTA_MD, cargar_guia, parsear_guia
    from app.siguiente_cultivo import GUIA_POR_ZONA

    guia = cargar_guia()
    assert len(guia["filas"]) == 22 and len(guia["reglas"]) == 4
    assert {f["zona"] for f in guia["filas"]} == {"llanos", "valles", "altiplano"}
    if Path(RUTA_MD).exists():  # el JSON que usa la app es la guía actual
        assert parsear_guia(Path(RUTA_MD).read_text(encoding="utf-8")) == {**guia}

    # el motor usa la misma fuente: después de soya en los Llanos → maíz y girasol
    assert GUIA_POR_ZONA["llanos"]["soya"]["ids"] == ["maiz", "girasol"]

    # soya elegida desde el valle: la guía la tiene solo en los Llanos y se muestra igual, con su aviso de zona
    r = client.post("/api/next-crop", json={"lat": -17.39, "lon": -66.28, "cultivo_anterior_id": "soya"}).json()
    fila = r["guia"]["filas"][0]
    assert fila["producto"] == "Soya" and fila["zona"] == "llanos" and fila["en_tu_zona"] is False
    assert "Sorgo" in fila["despues"] and fila["temporada"].startswith("Verano")
    assert [b["texto"] for b in fila["impacto"]] and [b["texto"] for b in fila["beneficios"]]

    # en los Llanos, la fila aparece como "en tu zona"
    ll = client.post("/api/next-crop", json={"lat": -17.78, "lon": -63.18, "cultivo_anterior_id": "soya"}).json()
    assert ll["guia"]["filas"][0]["en_tu_zona"] is True and "Llanos" in ll["guia"]["zona_detectada"]

    # productos que solo están en la guía (caña, sésamo, ají…) se pueden elegir y muestran la guía sin puntajes
    g = client.get("/api/rotation-guide").json()
    nombres = {p["nombre"] for p in g["productos_sin_cultivo"]}
    assert {"Sésamo y Chía", "Caña de Azúcar"} <= nombres
    caña = next(p for p in g["productos_sin_cultivo"] if p["nombre"] == "Caña de Azúcar")
    r2 = client.post("/api/next-crop", json={"lat": -17.78, "lon": -63.18, "cultivo_anterior_id": caña["id"]}).json()
    assert r2["solo_guia"] is True and r2["sugerencias"] == [] and "Crotalaria" in r2["guia"]["filas"][0]["despues"]
    assert client.post("/api/next-crop", json={"lat": -17.78, "lon": -63.18, "cultivo_anterior_id": "guia:no-existe"}).status_code == 404
