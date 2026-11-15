import hashlib
import json
import logging
import math
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .climate import mensual
from .rain_probability import acumulado_ventana, acumulados_historicos

logger = logging.getLogger(__name__)

POWER_CLIMATOLOGY_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
CACHE_DIR = Path(os.environ.get("AGRONASA_CACHE_DIR", "/tmp/agronasa_cache"))
DESFASE_NASA_DIAS = 3  # NASA POWER publica el diario con unos días de retraso
MONTH_KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_MEMORY_CACHE: Dict[str, Any] = {}
_MEMORY_CACHE_MAX = 500          # tope: el servidor es público y la caché no puede crecer sin límite
RESPALDO_VIGENCIA_S = 600        # un dato de respaldo se vuelve a intentar con NASA pasados 10 min
FALLO_REINTENTO_S = 300          # tras un fallo de red, no se vuelve a golpear NASA durante 5 min
_FALLOS: Dict[str, float] = {}
_CANDADOS: Dict[str, threading.Lock] = {}
_CANDADOS_GLOBAL = threading.Lock()


def _cache_set(clave: str, valor: Any) -> None:
    _MEMORY_CACHE.pop(clave, None)
    _MEMORY_CACHE[clave] = valor
    while len(_MEMORY_CACHE) > _MEMORY_CACHE_MAX:
        _MEMORY_CACHE.pop(next(iter(_MEMORY_CACHE)))


def _candado(clave: str) -> threading.Lock:
    """Un candado por clave: peticiones iguales y simultáneas esperan a la primera en vez de repetir la descarga."""
    with _CANDADOS_GLOBAL:
        return _CANDADOS.setdefault(clave, threading.Lock())


def _fallo_reciente(clave: str) -> bool:
    return time.time() - _FALLOS.get(clave, 0.0) < FALLO_REINTENTO_S

# Datos precargados basados en climatología NASA POWER (comunidad AG) para zonas de demostración
DEMO_ZONES: List[Dict[str, Any]] = [
    {
        "id": "valle_cochabamba",
        "nombre": "Valles Interandinos (Cochabamba, Bolivia)",
        "lat": -17.39,
        "lon": -66.28,
        "climatology": {
            "T2M": {
                "JAN": 19.8, "FEB": 19.5, "MAR": 19.2, "APR": 18.3, "MAY": 16.5, "JUN": 14.8,
                "JUL": 14.9, "AUG": 16.8, "SEP": 18.9, "OCT": 20.6, "NOV": 21.2, "DEC": 20.4, "ANN": 18.4
            },
            "T2M_MAX": {
                "JAN": 26.2, "FEB": 25.8, "MAR": 26.0, "APR": 26.4, "MAY": 25.9, "JUN": 24.8,
                "JUL": 24.9, "AUG": 26.5, "SEP": 27.8, "OCT": 28.9, "NOV": 29.1, "DEC": 27.4, "ANN": 26.6
            },
            "T2M_MIN": {
                "JAN": 13.5, "FEB": 13.4, "MAR": 12.6, "APR": 10.2, "MAY": 6.8, "JUN": 4.2,
                "JUL": 4.1, "AUG": 6.5, "SEP": 9.8, "OCT": 12.3, "NOV": 13.5, "DEC": 13.8, "ANN": 10.1
            },
            # PRECTOTCORR en mm/día (multiplicado por días del mes da ~560 mm anuales, concentrados oct-mar)
            "PRECTOTCORR": {
                "JAN": 4.2, "FEB": 3.8, "MAR": 2.6, "APR": 0.9, "MAY": 0.2, "JUN": 0.1,
                "JUL": 0.1, "AUG": 0.2, "SEP": 0.6, "OCT": 1.5, "NOV": 2.4, "DEC": 3.5, "ANN": 1.68
            },
            "RH2M": {
                "JAN": 68.0, "FEB": 70.0, "MAR": 66.0, "APR": 58.0, "MAY": 49.0, "JUN": 45.0,
                "JUL": 44.0, "AUG": 45.0, "SEP": 48.0, "OCT": 52.0, "NOV": 57.0, "DEC": 64.0, "ANN": 55.5
            },
            "GWETROOT": {
                "JAN": 0.62, "FEB": 0.65, "MAR": 0.60, "APR": 0.51, "MAY": 0.42, "JUN": 0.37,
                "JUL": 0.35, "AUG": 0.34, "SEP": 0.36, "OCT": 0.43, "NOV": 0.50, "DEC": 0.57, "ANN": 0.48
            },
            "ALLSKY_SFC_SW_DWN": {
                "JAN": 6.1, "FEB": 5.9, "MAR": 6.0, "APR": 6.1, "MAY": 5.8, "JUN": 5.5,
                "JUL": 5.7, "AUG": 6.3, "SEP": 6.7, "OCT": 6.9, "NOV": 6.8, "DEC": 6.3, "ANN": 6.2
            },
            "MODIS_NDVI": {
                "JAN": 0.54, "FEB": 0.58, "MAR": 0.56, "APR": 0.47, "MAY": 0.36, "JUN": 0.30,
                "JUL": 0.28, "AUG": 0.27, "SEP": 0.30, "OCT": 0.37, "NOV": 0.44, "DEC": 0.50, "ANN": 0.41
            }
        },
        "alert_scenario": {
            "precip_30d_actual": 28.0,
            "precip_30d_hist": [
                18.0, 22.0, 26.0, 31.0, 35.0, 39.0, 42.0, 45.0, 48.0, 51.0,
                54.0, 57.0, 61.0, 64.0, 68.0, 72.0, 77.0, 83.0, 90.0, 98.0
            ],
            "precip_60d_actual": 49.0,
            "precip_60d_hist": [
                35.0, 42.0, 47.0, 54.0, 60.0, 66.0, 71.0, 76.0, 82.0, 88.0,
                94.0, 99.0, 105.0, 112.0, 118.0, 125.0, 133.0, 141.0, 152.0, 165.0
            ],
            "gwetroot_recent": 0.38,
            "t2m_min_recent": 10.8
        }
    },
    {
        "id": "altiplano_lapaz",
        "nombre": "Altiplano Andino (La Paz / El Alto, Bolivia)",
        "lat": -16.50,
        "lon": -68.15,
        "climatology": {
            "T2M": {
                "JAN": 10.8, "FEB": 10.7, "MAR": 10.4, "APR": 9.5, "MAY": 7.8, "JUN": 6.2,
                "JUL": 6.0, "AUG": 7.3, "SEP": 9.0, "OCT": 10.5, "NOV": 11.4, "DEC": 11.2, "ANN": 9.2
            },
            "T2M_MAX": {
                "JAN": 16.5, "FEB": 16.3, "MAR": 16.4, "APR": 16.6, "MAY": 16.1, "JUN": 15.0,
                "JUL": 14.9, "AUG": 16.0, "SEP": 17.1, "OCT": 18.3, "NOV": 18.8, "DEC": 17.5, "ANN": 16.6
            },
            "T2M_MIN": {
                "JAN": 5.2, "FEB": 5.1, "MAR": 4.4, "APR": 2.1, "MAY": -1.2, "JUN": -3.8,
                "JUL": -4.2, "AUG": -2.4, "SEP": 0.6, "OCT": 2.9, "NOV": 4.3, "DEC": 5.0, "ANN": 1.5
            },
            "PRECTOTCORR": {
                "JAN": 4.5, "FEB": 4.1, "MAR": 2.8, "APR": 1.1, "MAY": 0.4, "JUN": 0.2,
                "JUL": 0.2, "AUG": 0.4, "SEP": 1.0, "OCT": 1.6, "NOV": 2.2, "DEC": 3.6, "ANN": 1.84
            },
            "RH2M": {
                "JAN": 71.0, "FEB": 72.0, "MAR": 68.0, "APR": 58.0, "MAY": 47.0, "JUN": 41.0,
                "JUL": 40.0, "AUG": 43.0, "SEP": 49.0, "OCT": 54.0, "NOV": 58.0, "DEC": 66.0, "ANN": 55.6
            },
            "GWETROOT": {
                "JAN": 0.58, "FEB": 0.61, "MAR": 0.57, "APR": 0.48, "MAY": 0.39, "JUN": 0.34,
                "JUL": 0.32, "AUG": 0.31, "SEP": 0.34, "OCT": 0.40, "NOV": 0.46, "DEC": 0.53, "ANN": 0.44
            },
            "ALLSKY_SFC_SW_DWN": {
                "JAN": 6.4, "FEB": 6.2, "MAR": 6.3, "APR": 6.5, "MAY": 6.2, "JUN": 5.9,
                "JUL": 6.1, "AUG": 6.7, "SEP": 7.1, "OCT": 7.3, "NOV": 7.2, "DEC": 6.6, "ANN": 6.5
            },
            "MODIS_NDVI": {
                "JAN": 0.38, "FEB": 0.42, "MAR": 0.40, "APR": 0.33, "MAY": 0.25, "JUN": 0.21,
                "JUL": 0.19, "AUG": 0.19, "SEP": 0.21, "OCT": 0.25, "NOV": 0.30, "DEC": 0.35, "ANN": 0.29
            }
        },
        "alert_scenario": {
            "precip_30d_actual": 14.0,
            "precip_30d_hist": [
                15.0, 19.0, 23.0, 27.0, 31.0, 35.0, 38.0, 42.0, 46.0, 49.0,
                52.0, 56.0, 60.0, 64.0, 69.0, 73.0, 79.0, 85.0, 92.0, 101.0
            ],
            "precip_60d_actual": 26.0,
            "precip_60d_hist": [
                30.0, 36.0, 41.0, 48.0, 55.0, 61.0, 67.0, 73.0, 79.0, 85.0,
                91.0, 97.0, 104.0, 111.0, 119.0, 126.0, 135.0, 144.0, 155.0, 168.0
            ],
            "gwetroot_recent": 0.31,
            "t2m_min_recent": -1.5
        }
    },
    {
        "id": "llanos_santacruz",
        "nombre": "Llanos Tropicales (Santa Cruz, Bolivia)",
        "lat": -17.78,
        "lon": -63.18,
        "climatology": {
            "T2M": {
                "JAN": 26.8, "FEB": 26.5, "MAR": 25.9, "APR": 24.3, "MAY": 21.8, "JUN": 20.4,
                "JUL": 20.6, "AUG": 22.8, "SEP": 25.1, "OCT": 26.6, "NOV": 26.9, "DEC": 26.9, "ANN": 24.6
            },
            "T2M_MAX": {
                "JAN": 31.8, "FEB": 31.4, "MAR": 30.9, "APR": 29.4, "MAY": 26.7, "JUN": 25.3,
                "JUL": 26.1, "AUG": 29.0, "SEP": 31.5, "OCT": 32.6, "NOV": 32.5, "DEC": 32.0, "ANN": 29.9
            },
            "T2M_MIN": {
                "JAN": 22.1, "FEB": 21.9, "MAR": 21.1, "APR": 19.3, "MAY": 17.0, "JUN": 15.6,
                "JUL": 15.2, "AUG": 16.6, "SEP": 18.8, "OCT": 20.8, "NOV": 21.5, "DEC": 22.0, "ANN": 19.3
            },
            "PRECTOTCORR": {
                "JAN": 6.2, "FEB": 5.8, "MAR": 4.6, "APR": 3.1, "MAY": 2.2, "JUN": 1.6,
                "JUL": 1.2, "AUG": 1.3, "SEP": 2.1, "OCT": 3.8, "NOV": 4.9, "DEC": 5.8, "ANN": 3.55
            },
            "RH2M": {
                "JAN": 78.0, "FEB": 79.0, "MAR": 78.0, "APR": 76.0, "MAY": 75.0, "JUN": 73.0,
                "JUL": 67.0, "AUG": 60.0, "SEP": 61.0, "OCT": 67.0, "NOV": 71.0, "DEC": 76.0, "ANN": 71.8
            },
            "GWETROOT": {
                "JAN": 0.74, "FEB": 0.76, "MAR": 0.73, "APR": 0.68, "MAY": 0.63, "JUN": 0.59,
                "JUL": 0.53, "AUG": 0.48, "SEP": 0.50, "OCT": 0.58, "NOV": 0.65, "DEC": 0.71, "ANN": 0.63
            },
            "ALLSKY_SFC_SW_DWN": {
                "JAN": 5.8, "FEB": 5.6, "MAR": 5.4, "APR": 5.0, "MAY": 4.4, "JUN": 4.1,
                "JUL": 4.6, "AUG": 5.3, "SEP": 5.7, "OCT": 6.0, "NOV": 6.1, "DEC": 5.9, "ANN": 5.3
            },
            "MODIS_NDVI": {
                "JAN": 0.72, "FEB": 0.75, "MAR": 0.74, "APR": 0.70, "MAY": 0.66, "JUN": 0.62,
                "JUL": 0.56, "AUG": 0.51, "SEP": 0.54, "OCT": 0.61, "NOV": 0.66, "DEC": 0.70, "ANN": 0.65
            }
        },
        "alert_scenario": {
            "precip_30d_actual": 168.0,
            "precip_30d_hist": [
                45.0, 55.0, 64.0, 72.0, 80.0, 88.0, 95.0, 102.0, 108.0, 115.0,
                121.0, 128.0, 134.0, 141.0, 149.0, 156.0, 165.0, 178.0, 192.0, 210.0
            ],
            "precip_60d_actual": 295.0,
            "precip_60d_hist": [
                90.0, 110.0, 125.0, 140.0, 155.0, 168.0, 180.0, 195.0, 208.0, 220.0,
                235.0, 248.0, 260.0, 275.0, 288.0, 302.0, 320.0, 340.0, 365.0, 395.0
            ],
            "gwetroot_recent": 0.78,
            "t2m_min_recent": 20.4
        }
    },
    {
        "id": "valle_cusco",
        "nombre": "Sierra y Valle Sagrado (Cusco, Perú)",
        "lat": -13.53,
        "lon": -71.97,
        "climatology": {
            "T2M": {
                "JAN": 13.2, "FEB": 13.1, "MAR": 13.0, "APR": 12.5, "MAY": 11.4, "JUN": 10.2,
                "JUL": 10.0, "AUG": 11.1, "SEP": 12.4, "OCT": 13.6, "NOV": 14.0, "DEC": 13.5, "ANN": 12.3
            },
            "T2M_MAX": {
                "JAN": 19.4, "FEB": 19.2, "MAR": 19.5, "APR": 20.1, "MAY": 19.9, "JUN": 19.2,
                "JUL": 19.1, "AUG": 20.0, "SEP": 20.5, "OCT": 21.4, "NOV": 21.3, "DEC": 20.0, "ANN": 20.0
            },
            "T2M_MIN": {
                "JAN": 7.2, "FEB": 7.3, "MAR": 6.8, "APR": 4.8, "MAY": 2.1, "JUN": -0.2,
                "JUL": -0.5, "AUG": 1.2, "SEP": 4.0, "OCT": 5.9, "NOV": 6.8, "DEC": 7.2, "ANN": 4.4
            },
            "PRECTOTCORR": {
                "JAN": 5.1, "FEB": 4.8, "MAR": 3.5, "APR": 1.5, "MAY": 0.3, "JUN": 0.1,
                "JUL": 0.1, "AUG": 0.3, "SEP": 1.0, "OCT": 2.1, "NOV": 3.0, "DEC": 4.3, "ANN": 2.18
            },
            "RH2M": {
                "JAN": 73.0, "FEB": 74.0, "MAR": 72.0, "APR": 64.0, "MAY": 54.0, "JUN": 48.0,
                "JUL": 47.0, "AUG": 49.0, "SEP": 54.0, "OCT": 58.0, "NOV": 62.0, "DEC": 69.0, "ANN": 60.3
            },
            "GWETROOT": {
                "JAN": 0.66, "FEB": 0.69, "MAR": 0.65, "APR": 0.56, "MAY": 0.46, "JUN": 0.40,
                "JUL": 0.37, "AUG": 0.36, "SEP": 0.39, "OCT": 0.46, "NOV": 0.53, "DEC": 0.61, "ANN": 0.51
            },
            "ALLSKY_SFC_SW_DWN": {
                "JAN": 5.9, "FEB": 5.8, "MAR": 5.9, "APR": 6.1, "MAY": 5.9, "JUN": 5.7,
                "JUL": 5.9, "AUG": 6.3, "SEP": 6.5, "OCT": 6.7, "NOV": 6.6, "DEC": 6.1, "ANN": 6.1
            },
            "MODIS_NDVI": {
                "JAN": 0.58, "FEB": 0.63, "MAR": 0.61, "APR": 0.52, "MAY": 0.41, "JUN": 0.34,
                "JUL": 0.31, "AUG": 0.30, "SEP": 0.33, "OCT": 0.40, "NOV": 0.47, "DEC": 0.53, "ANN": 0.45
            }
        },
        "alert_scenario": {
            "precip_30d_actual": 62.0,
            "precip_30d_hist": [
                25.0, 30.0, 35.0, 40.0, 44.0, 48.0, 52.0, 56.0, 59.0, 62.0,
                65.0, 69.0, 73.0, 78.0, 82.0, 87.0, 93.0, 99.0, 107.0, 118.0
            ],
            "precip_60d_actual": 115.0,
            "precip_60d_hist": [
                50.0, 58.0, 67.0, 75.0, 83.0, 90.0, 97.0, 104.0, 110.0, 116.0,
                122.0, 129.0, 136.0, 144.0, 152.0, 161.0, 170.0, 182.0, 195.0, 212.0
            ],
            "gwetroot_recent": 0.52,
            "t2m_min_recent": 5.8
        }
    }
]


def round_to_nasa_grid(lat: float, lon: float) -> Tuple[float, float]:
    """Redondea lat/lon a la malla de NASA POWER (0.5° lat x 0.625° lon)."""
    grid_lat = round(round(lat / 0.5) * 0.5, 4)
    grid_lon = round(round(lon / 0.625) * 0.625, 4)
    return grid_lat, grid_lon


def clean_nasa_series(series: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Filtra valores faltantes (-999 o -999.0) de las respuestas de NASA POWER."""
    cleaned: Dict[str, Optional[float]] = {}
    for k, v in series.items():
        if v is None or v <= -900:
            cleaned[k] = None
        else:
            cleaned[k] = float(v)
    return cleaned


def find_matching_demo_zone(lat: float, lon: float, max_dist_deg: float = 0.85) -> Optional[Dict[str, Any]]:
    """Busca si el punto solicitado coincide con una de las zonas de demostración precargadas."""
    best = None
    best_dist = float("inf")
    for zone in DEMO_ZONES:
        dist = math.hypot(lat - zone["lat"], lon - zone["lon"])
        if dist < best_dist and dist <= max_dist_deg:
            best = zone
            best_dist = dist
    return best


def _cache_file_path(prefix: str, grid_lat: float, grid_lon: float) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{prefix}_{grid_lat}_{grid_lon}".encode("utf-8")
    digest = hashlib.md5(key).hexdigest()[:12]
    return CACHE_DIR / f"{prefix}_{grid_lat}_{grid_lon}_{digest}.json"


def _synthesize_climatology_for_coords(lat: float, lon: float) -> Dict[str, Dict[str, float]]:
    """
    Genera una climatología agroclimática realista para cualquier coordenada global
    como respaldo cuando no hay conexión a internet o NASA POWER no responde.
    """
    abs_lat = abs(lat)
    is_south = lat < 0
    # Temperatura base según latitud
    base_temp = max(4.0, 27.5 - 0.45 * abs_lat)
    # Ajuste por cordillera andina aproximada
    if -35.0 <= lat <= 5.0 and -78.0 <= lon <= -64.5:
        # Zona andina
        base_temp -= 7.5

    amp_temp = 2.5 + 0.22 * abs_lat
    t2m, t2m_max, t2m_min, prec, rh2m, gwet, sw_dwn, ndvi = {}, {}, {}, {}, {}, {}, {}, {}

    for m_idx, m_key in enumerate(MONTH_KEYS):
        # Fase estacional (enero cálido en hemisferio sur, julio en norte)
        angle = 2 * math.pi * (m_idx / 12.0)
        season = math.cos(angle) if is_south else -math.cos(angle)

        m_t2m = round(base_temp + amp_temp * season, 1)
        m_max = round(m_t2m + 6.5 - 1.2 * season, 1)
        m_min = round(m_t2m - 6.5 + 1.2 * season, 1)

        # Precipitación estacional (mm/día)
        wet_factor = max(0.15, (1.0 + 0.85 * season) / 1.85)
        arid_mod = 1.0 if abs_lat < 20 else 0.7
        m_prec = round(max(0.1, 3.8 * wet_factor * arid_mod), 2)

        m_rh = round(min(88.0, max(35.0, 58.0 + 18.0 * season)), 1)
        m_gwet = round(min(0.85, max(0.25, 0.48 + 0.18 * season)), 2)
        m_sw = round(max(3.2, 5.8 + 1.1 * season), 1)
        m_ndvi = round(min(0.82, max(0.20, 0.45 + 0.18 * season)), 2)

        t2m[m_key] = m_t2m
        t2m_max[m_key] = m_max
        t2m_min[m_key] = m_min
        prec[m_key] = m_prec
        rh2m[m_key] = m_rh
        gwet[m_key] = m_gwet
        sw_dwn[m_key] = m_sw
        ndvi[m_key] = m_ndvi

    for d in (t2m, t2m_max, t2m_min, prec, rh2m, gwet, sw_dwn, ndvi):
        d["ANN"] = round(sum(d[k] for k in MONTH_KEYS) / 12.0, 2)

    return {
        "T2M": t2m,
        "T2M_MAX": t2m_max,
        "T2M_MIN": t2m_min,
        "PRECTOTCORR": prec,
        "RH2M": rh2m,
        "GWETROOT": gwet,
        "ALLSKY_SFC_SW_DWN": sw_dwn,
        "MODIS_NDVI": ndvi,
    }


def _derive_ndvi_from_nasa_power(cleaned_params: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, float]:
    """
    Calcula el índice de vigor vegetal estimado (NDVI) directamente a partir de los parámetros
    reales de NASA POWER (GWETROOT, PRECTOTCORR y T2M) de la celda consultada.
    """
    ndvi: Dict[str, float] = {}
    gwet_series = cleaned_params.get("GWETROOT", {})
    prec_series = cleaned_params.get("PRECTOTCORR", {})
    t2m_series = cleaned_params.get("T2M", {})

    for k in MONTH_KEYS:
        gwet = float(gwet_series.get(k) if gwet_series.get(k) is not None else 0.45)
        prec = float(prec_series.get(k) if prec_series.get(k) is not None else 1.5)
        t2m = float(t2m_series.get(k) if t2m_series.get(k) is not None else 18.0)

        # Factor térmico de actividad fotosintética (0.2 a 1.0)
        temp_factor = max(0.2, min(1.0, (t2m - 2.0) / 22.0))
        # Factor hídrico combinado (humedad radicular + lluvia diaria)
        water_factor = 0.65 * gwet + 0.35 * min(1.0, prec / 5.0)
        val = max(0.12, min(0.85, (0.10 + 0.78 * water_factor) * (0.55 + 0.45 * temp_factor)))
        ndvi[k] = round(val, 2)

    ndvi["ANN"] = round(sum(ndvi[k] for k in MONTH_KEYS) / 12.0, 2)
    return ndvi


def get_climatology(lat: float, lon: float, allow_network: bool = True) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """
    Obtiene la climatología mensual de NASA POWER para (lat, lon).
    Retorna: (parametros_climatologia, modo_datos, nombre_zona_referencia)
    """
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    cache_key = f"clim_{grid_lat}_{grid_lon}"

    # 1. Revisar si coincide con una zona de demostración precargada
    demo_zone = find_matching_demo_zone(lat, lon)

    # Si estamos en modo pruebas unitarias offline (allow_network=False), usar zona demo determinista
    if not allow_network and demo_zone:
        return (
            demo_zone["climatology"],
            "NASA POWER (Datos precargados de referencia)",
            demo_zone["nombre"],
        )

    cached = _MEMORY_CACHE.get(cache_key)
    if cached and not (cached.get("expira") and time.time() > cached["expira"]):
        return cached["data"], cached["mode"], cached.get("zone_name")

    cache_file = _cache_file_path("clim", grid_lat, grid_lon)
    if cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            if "data" in payload:
                payload["data"]["MODIS_NDVI"] = _derive_ndvi_from_nasa_power(payload["data"])
            _cache_set(cache_key, payload)
            return payload["data"], payload["mode"], payload.get("zone_name")
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("Caché ilegible en %s; se vuelve a consultar", cache_file, exc_info=True)

    # 2. Intentar consultar NASA POWER en vivo si está habilitado
    if allow_network and os.environ.get("AGRONASA_OFFLINE_ONLY", "0") != "1":
        params = {
            "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,GWETROOT,ALLSKY_SFC_SW_DWN",
            "community": "AG",
            "longitude": grid_lon,
            "latitude": grid_lat,
            "format": "JSON",
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(POWER_CLIMATOLOGY_URL, params=params)
                r.raise_for_status()
                raw_params = r.json()["properties"]["parameter"]
                cleaned_params = {
                    param: clean_nasa_series(series)
                    for param, series in raw_params.items()
                }
                cleaned_params["MODIS_NDVI"] = _derive_ndvi_from_nasa_power(cleaned_params)

                payload = {
                    "data": cleaned_params,
                    "mode": "NASA POWER API (En vivo)",
                    "zone_name": demo_zone["nombre"] if demo_zone else f"Celda NASA ({grid_lat}°, {grid_lon}°)",
                }
                _cache_set(cache_key, payload)
                try:
                    cache_file.write_text(json.dumps(payload), encoding="utf-8")
                except OSError:
                    logger.warning("No se pudo escribir la caché en %s", cache_file, exc_info=True)
                return payload["data"], payload["mode"], payload["zone_name"]
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            logger.warning("NASA POWER (climatología) no disponible; se usan datos de respaldo", exc_info=True)

    # 3. Fallback a zona de demostración precargada o modelo agroclimático regional
    if demo_zone:
        payload = {
            "data": demo_zone["climatology"],
            "mode": "NASA POWER (Datos precargados de referencia)",
            "zone_name": demo_zone["nombre"],
        }
    else:
        payload = {
            "data": _synthesize_climatology_for_coords(lat, lon),
            "mode": "NASA POWER (Caché / Estimación regional offline)",
            "zone_name": f"Celda agroclimática ({grid_lat}°, {grid_lon}°)",
        }

    if allow_network:
        _cache_set(cache_key, {**payload, "expira": time.time() + RESPALDO_VIGENCIA_S})
    return payload["data"], payload["mode"], payload["zone_name"]


def get_recent_and_historical_window(lat: float, lon: float, allow_network: bool = True) -> Dict[str, Any]:
    """
    Obtiene el resumen de precipitación acumulada reciente (30 y 60 días), distribución histórica
    de 20 años para esa misma ventana, humedad de suelo en raíz (GWETROOT) y temperatura mínima reciente.
    Consulta NASA POWER Daily API cuando está disponible y construye la distribución contra la climatología NASA.
    """
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    demo_zone = find_matching_demo_zone(lat, lon)

    if not allow_network and demo_zone:
        return _marcar_estimado(demo_zone["alert_scenario"])

    clim, _, _ = get_climatology(lat, lon, allow_network=allow_network)
    today = date.today()
    cur_month_key = MONTH_KEYS[today.month - 1]
    prev_month_key = MONTH_KEYS[(today.month - 2) % 12]

    daily_mm_cur = mensual(clim["PRECTOTCORR"], cur_month_key, 1.5)
    daily_mm_prev = mensual(clim["PRECTOTCORR"], prev_month_key, 1.5)

    mean_30d = max(5.0, daily_mm_cur * 30.0)
    mean_60d = max(10.0, (daily_mm_cur * 30.0) + (daily_mm_prev * 30.0))

    multipliers = [
        0.38, 0.46, 0.54, 0.61, 0.68, 0.74, 0.80, 0.86, 0.92, 0.97,
        1.02, 1.07, 1.13, 1.19, 1.25, 1.32, 1.40, 1.49, 1.60, 1.75
    ]
    hist_30d = [round(mean_30d * m, 1) for m in multipliers]
    hist_60d = [round(mean_60d * m, 1) for m in multipliers]

    daily_cache_key = f"daily_{grid_lat}_{grid_lon}_{today.isoformat()}"
    if daily_cache_key in _MEMORY_CACHE:
        return _MEMORY_CACHE[daily_cache_key]

    if allow_network and os.environ.get("AGRONASA_OFFLINE_ONLY", "0") != "1" and not _fallo_reciente(daily_cache_key):
        with _candado(daily_cache_key):
            if daily_cache_key in _MEMORY_CACHE:
                return _MEMORY_CACHE[daily_cache_key]
            real = _ventana_reciente_real(lat, lon, today)
            if real:
                _cache_set(daily_cache_key, real)
                return real
            _FALLOS[daily_cache_key] = time.time()

    if demo_zone:
        return _marcar_estimado(demo_zone["alert_scenario"])

    return {
        "precip_30d_actual": round(mean_30d * 0.92, 1),
        "precip_30d_hist": hist_30d,
        "precip_60d_actual": round(mean_60d * 0.94, 1),
        "precip_60d_hist": hist_60d,
        "gwetroot_recent": mensual(clim["GWETROOT"], cur_month_key, 0.5),
        "t2m_min_recent": mensual(clim["T2M_MIN"], cur_month_key, 10.0),
        "estimado": True,
    }


def _marcar_estimado(escenario: Dict[str, Any]) -> Dict[str, Any]:
    return {**escenario, "estimado": True}


def _ventana_reciente_real(lat: float, lon: float, hoy: date) -> Optional[Dict[str, Any]]:
    """
    Lluvia, humedad de raíz y mínima de los últimos 30 y 60 días reales (NASA POWER diario, con ~3 días de retraso)
    comparadas con la misma ventana de cada uno de los últimos 20 años. None si no hay datos suficientes.
    """
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    fin = hoy - timedelta(days=DESFASE_NASA_DIAS)
    params = {
        "parameters": "PRECTOTCORR,T2M_MIN,GWETROOT",
        "community": "AG",
        "longitude": grid_lon,
        "latitude": grid_lat,
        "start": (fin - timedelta(days=64)).strftime("%Y%m%d"),
        "end": fin.strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(POWER_DAILY_URL, params=params)
            r.raise_for_status()
            crudo = r.json()["properties"]["parameter"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        logger.warning("NASA POWER (serie diaria reciente) no disponible", exc_info=True)
        return None

    def serie(nombre: str) -> Dict[date, float]:
        return {
            datetime.strptime(dia, "%Y%m%d").date(): float(v)
            for dia, v in crudo.get(nombre, {}).items()
            if v is not None and float(v) > -900
        }

    lluvia, humedad, minimas = serie("PRECTOTCORR"), serie("GWETROOT"), serie("T2M_MIN")
    historial = get_daily_rain_history(lat, lon)
    if not historial:
        return None
    p30, p60 = acumulado_ventana(lluvia, fin, 30), acumulado_ventana(lluvia, fin, 60)
    hist30, hist60 = acumulados_historicos(historial, fin, 30), acumulados_historicos(historial, fin, 60)
    if p30 is None or p60 is None or len(hist30) < 10 or len(hist60) < 10:
        return None

    recientes_humedad = [humedad[d] for d in sorted(humedad)[-15:]]
    recientes_minimas = [minimas[d] for d in sorted(minimas)[-30:]]
    return {
        "precip_30d_actual": p30,
        "precip_30d_hist": hist30,
        "precip_60d_actual": p60,
        "precip_60d_hist": hist60,
        "gwetroot_recent": round(sum(recientes_humedad) / len(recientes_humedad), 2) if recientes_humedad else 0.5,
        "t2m_min_recent": round(min(recientes_minimas), 1) if recientes_minimas else 10.0,
        "hasta": fin.isoformat(),
        "estimado": False,
    }


def get_daily_rain_history(lat: float, lon: float, anios: int = 20) -> Optional[Dict[date, float]]:
    """Lluvia diaria (mm) de los últimos `anios` años completos desde NASA POWER; None si no hay datos."""
    if os.environ.get("AGRONASA_OFFLINE_ONLY", "0") == "1":
        return None
    grid_lat, grid_lon = round_to_nasa_grid(lat, lon)
    clave = f"rain_hist_{grid_lat}_{grid_lon}"
    if clave in _MEMORY_CACHE:
        return _MEMORY_CACHE[clave]
    if _fallo_reciente(clave):
        return None
    with _candado(clave):
        if clave in _MEMORY_CACHE:
            return _MEMORY_CACHE[clave]
        return _descargar_historial_lluvia(clave, grid_lat, grid_lon, anios)


def _descargar_historial_lluvia(clave: str, grid_lat: float, grid_lon: float, anios: int) -> Optional[Dict[date, float]]:

    ultimo_anio = date.today().year - 1
    params = {
        "parameters": "PRECTOTCORR",
        "community": "AG",
        "longitude": grid_lon,
        "latitude": grid_lat,
        "start": f"{ultimo_anio - anios + 1}0101",
        "end": f"{ultimo_anio}1231",
        "format": "JSON",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(POWER_DAILY_URL, params=params)
            r.raise_for_status()
            serie = r.json()["properties"]["parameter"]["PRECTOTCORR"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        logger.warning("NASA POWER (lluvia diaria histórica) no disponible", exc_info=True)
        _FALLOS[clave] = time.time()
        return None

    historial = {
        datetime.strptime(dia, "%Y%m%d").date(): float(mm)
        for dia, mm in serie.items()
        if mm is not None and float(mm) > -900
    }
    _cache_set(clave, historial)
    return historial
