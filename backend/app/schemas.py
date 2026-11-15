from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SoilInput(BaseModel):
    ph: Optional[float] = Field(None, ge=3.0, le=10.0, description="pH del suelo (3.0 a 10.0)")
    textura: Optional[
        Literal["arenoso", "franco-arenoso", "franco", "franco-arcilloso", "arcilloso"]
    ] = Field(None, description="Textura del suelo")
    materia_organica_pct: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Materia orgánica (%)"
    )
    nitrogeno: Optional[Literal["bajo", "medio", "alto"]] = None
    pendiente_pct: Optional[float] = Field(None, ge=0.0, le=60.0, description="Pendiente del terreno (%)")
    fosforo: Optional[Literal["bajo", "medio", "alto"]] = None
    potasio: Optional[Literal["bajo", "medio", "alto"]] = None
    drenaje: Optional[Literal["bueno", "moderado", "pobre"]] = None


Riego = Literal["secano", "limitado", "completo"]


class RecommendRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitud (-90 a 90)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitud (-180 a 180)")
    mes_siembra: Optional[int] = Field(
        None, ge=1, le=12, description="Mes de siembra (1=Enero .. 12=Diciembre). Si se omite, evalúa el mejor mes."
    )
    categorias: Optional[List[str]] = Field(
        None, max_length=10, description="Filtrar por categorías (ej. ['cereales', 'hortalizas'])"
    )
    suelo: Optional[SoilInput] = Field(None, description="Datos opcionales de suelo")
    riego: Optional[Riego] = Field(None, description="Riego disponible: secano, limitado o completo")


class ExploreRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    mes_siembra: Optional[int] = Field(None, ge=1, le=12)
    categoria: Optional[str] = Field(None, max_length=40, description="Categoría de cultivo a explorar")
    cultivos_ids: Optional[List[str]] = Field(
        None, max_length=25, description="Lista opcional de IDs de cultivos específicos"
    )
    suelo: Optional[SoilInput] = None
    riego: Optional[Riego] = None


class RotationRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    mes_inicio: int = Field(10, ge=1, le=12, description="Mes de inicio del primer ciclo")
    cultivo_inicial_id: Optional[str] = Field(
        None, max_length=40, description="Cultivo inicial deseado (opcional)"
    )
    suelo: SoilInput = Field(..., description="Datos de suelo para optimizar rotación")


class NextCropRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    cultivo_anterior_id: str = Field(..., max_length=40, description="Cultivo que se sembró antes")
    mes_siembra: Optional[int] = Field(None, ge=1, le=12, description="Mes en que se quiere sembrar (vacío = mejor mes)")
    suelo: Optional[SoilInput] = None
    riego: Optional[Riego] = None


class PointInfo(BaseModel):
    lat: float
    lon: float
    celda_nasa: List[float]
    zona_referencia: Optional[str] = None


class AlertItem(BaseModel):
    tipo: str
    estado: str
    severidad: Literal["verde", "amarillo", "naranja", "rojo"]
    estimado: bool = False
    ventana_dias: Optional[int] = None
    percentil: Optional[float] = None
    lluvia_reciente_mm: Optional[float] = None
    lluvia_media_historica_mm: Optional[float] = None
    humedad_suelo_raiz: Optional[float] = None
    temp_min_reciente_c: Optional[float] = None
    mensaje: str


class CropRecommendation(BaseModel):
    id: str
    cultivo: str
    categoria: str
    familia: str
    puntaje: int
    etiqueta: Literal["Muy viable", "Viable con cuidados", "Poco viable", "No recomendado"]
    mes_siembra_evaluado: int
    duracion_ciclo_dias: int
    factor_limitante: str
    factores: Dict[str, float]
    ajuste_riesgo: Optional[str] = None
    observaciones_suelo: List[str] = []
    explicacion: str


class RecommendResponse(BaseModel):
    punto: PointInfo
    alertas: List[AlertItem]
    observaciones_suelo_generales: List[str] = []
    recomendaciones: List[CropRecommendation]
    condiciones: Optional[Dict[str, Any]] = None
    fuente: str
    modo_datos: str
    aviso: str


class RotationTag(BaseModel):
    color: Literal["rojo", "naranja", "amarillo", "verde", "azul", "morado"]
    icono: str
    texto: str


class RotationStep(BaseModel):
    ciclo: int
    id_cultivo: str
    nombre: str
    familia: str
    categoria: str
    mes_inicio: int
    mes_fin: int
    puntaje_climatico: int
    rol_agronomico: str
    razon: str
    etiquetas: List[RotationTag] = []


class RotationResponse(BaseModel):
    punto: PointInfo
    observaciones_suelo: List[str]
    ciclo_rotacion: List[RotationStep]
    beneficios_esperados: List[str]
    aviso: str


class IoTSensorMeasurements(BaseModel):
    temp_ambiente_c: float = Field(..., ge=-50.0, le=65.0)
    temp_min_24h_c: float = Field(..., ge=-50.0, le=65.0)
    humedad_ambiente_pct: float = Field(..., ge=0.0, le=100.0)
    temp_suelo_c: float = Field(..., ge=-30.0, le=60.0)
    humedad_suelo_pct: float = Field(..., ge=0.0, le=100.0)
    viento_velocidad_kmh: float = Field(..., ge=0.0, le=250.0)
    viento_direccion: str = Field("NE", max_length=8)


class IoTCameraSnapshot(BaseModel):
    fecha: str = Field(..., max_length=32)
    cobertura_verde_pct: float = Field(..., ge=0.0, le=100.0)
    ndvi_estimado: float = Field(..., ge=0.0, le=1.0)
    etapa: str = Field(..., max_length=60)


class IoTNodeStatus(BaseModel):
    id: str = Field(..., max_length=40)
    nombre: str = Field(..., max_length=80)
    bateria_pct: int = Field(..., ge=0, le=100)
    solar: bool = False
    red: str = Field("LoRaWAN", max_length=40)
    rssi_dbm: int = Field(-80, ge=-140, le=0)
    hace_min: int = Field(4, ge=0, le=10080)


class IoTTelemetryInput(BaseModel):
    parcela_id: str = Field("parcela-demo-01", max_length=60)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    mes: Optional[int] = Field(None, ge=1, le=12)
    mediciones: IoTSensorMeasurements
    camara_fenologica: Optional[Dict[str, IoTCameraSnapshot]] = None
    equipos: Optional[List[IoTNodeStatus]] = Field(None, max_length=20)


class IoTTelemetryResponse(BaseModel):
    parcela_id: str
    timestamp: str
    ubicacion: Dict[str, Any]
    mediciones: IoTSensorMeasurements
    fusion_nasa: Dict[str, Any]
    alertas_iot: List[Dict[str, str]]
    camara_fenologica: Dict[str, IoTCameraSnapshot]
    equipos: List[IoTNodeStatus]
    origen: str

