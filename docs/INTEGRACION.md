# AgroNasa — Guía técnica para fusionarlo con otro proyecto

Este documento describe **qué hace AgroNasa, cómo lo hace y qué contratos de datos usa**, para que otro equipo pueda reproducir las mismas funcionalidades con otro diseño o fusionarlas en su proyecto. Separa lo que es **lógica de dominio (debe conservarse)** de lo que es **capa visual (se puede cambiar)**.

> Estado: prototipo del reto *Field Shift: Adapting Farms with NASA Data* (NASA Space Apps 2026). Todo está en un solo archivo, `index.html` (HTML + CSS + JS, sin build), más un servidor opcional (`sensores-puente.js`) y pruebas (`tests/`).

---

## 1. Qué es, en un párrafo

Herramienta de **apoyo a decisiones** para agricultores. El usuario dibuja su terreno en un mapa y (opcionalmente) llena su estudio de suelo. La app consulta 30 años de clima de NASA POWER para ese punto, calcula tendencias, extremos y estrés hídrico, evalúa la salud del suelo, compara rotaciones de cultivos (la actual, un plan propio y 3 alternativas generadas) con un puntaje explicable (0–100), propone un calendario de siembra y cosecha, y genera un reporte PDF. Una pestaña aparte muestra sensores en campo (IoT LoRaWAN) frente a los datos satelitales. **Apoya, no reemplaza, al agricultor ni a un técnico.**

## 2. Qué se puede cambiar y qué no

| Se puede rediseñar libremente | Debe conservarse (decisiones de producto) |
|---|---|
| Colores, tipografías, layout, íconos, animaciones | Aviso permanente: *"Esta herramienta apoya la decisión; valídela con un agrónomo o experto local."* |
| Panel flotante vs. páginas, pestañas vs. acordeones | Rotular siempre lo que **no es de la NASA** (pronóstico, proyecciones 2050, elevación, datos de ejemplo) |
| Tipo de gráfico (siempre que muestre lo mismo) | Datos sintéticos siempre marcados como "ejemplo, NO NASA" |
| Textos de ayuda, microcopy (manteniendo lenguaje simple) | Nada de dosis de cal ni fertilizantes; nada de pronósticos afirmativos del clima futuro |
| Nombre y logo | Las "ventanas que se abren" no se presentan como ventaja del cambio climático |
| | Explicabilidad: cada puntaje se puede desarmar criterio por criterio |
| | Privacidad: el estudio de suelo no sale del navegador |
| | Mostrar incertidumbre (fuerza de tendencia, rango de puntaje, confianza, empate técnico) |

## 3. Arquitectura

```text
┌──────────── Entradas ────────────┐   ┌────────── Datos externos (sin clave) ──────────┐
│ Polígono (Leaflet.draw)          │   │ NASA POWER mensual + diario (30 años)          │
│ Suelo (form / CSV)               │──▶│ Open-Meteo: pronóstico, elevación, proyecciones│
│ Prioridades, rotación actual,    │   │ NASA GIBS (capas visuales), OSM, Esri          │
│ condiciones, plan, escenario     │   └───────────────┬────────────────────────────────┘
└──────────────┬───────────────────┘                   │
               ▼                                       ▼
        state + leerSuelo()  ──▶  analizar(clima)  ──▶  ctx = {c, S, w, rec}
                                                           │
        ┌──────────────────────────┬───────────────────────┼──────────────────────────┐
        ▼                          ▼                       ▼                          ▼
  saludSuelo/tarjetasSuelo   generar() → estrategias   cicloPlan()              fusionIot()
  (suelo cansado, acciones)  (puntaje, calendario,     (plan: siembra→cosecha→  (sensores vs NASA)
                              confianza, rango)         estudio→decisión)
        └──────────────────────────┴───────────────────────┴──────────────────────────┘
                                   ▼
                       render (UI) + reporte PDF (jsPDF)
```

**Estado global** (`state`): `poly, lat, lon, area, clima, meta, tab, charts, prio:Set, mercado:Set, riego, equipo, esc:{r,t}, pendAuto, relieve, lista, ctx, tiempo, proy, iot…`.

**Flujo reactivo:** cualquier cambio de entrada llama a `programar()` (espera 400 ms) → `mostrar()` + `guardarEstado()`. Al cambiar el terreno se consulta el clima (`cargarClima`), el relieve (`cargarRelieve`) y el pronóstico (`cargarTiempo`). El clima está protegido contra respuestas viejas con un token (`state.tok`).

### Secciones del código (en orden)
Datos guardados de ejemplo · Constantes · Base de cultivos · Utilidades · Estado · Tema/accesibilidad · Mapa · Relieve · Formulario · Semáforo de suelo · NASA POWER + caché · Tendencias · Probabilidades · Proyecciones 2050 · Visualizaciones · Gráficos del clima · El tiempo · Carga de clima · Salud del suelo · Plan · Cuidado del suelo · Rotaciones · Persistencia/enlace · Caso de ejemplo · PDF · Sensores · Panel flotante · Inicio.

## 4. Funcionalidades que debe tener la versión fusionada

1. **Mapa y terreno:** dibujar polígono/rectángulo, área en hectáreas (fórmula esférica), centroide, buscador de lugares, "mi ubicación", mapas base (claro/oscuro/satélite), capas NASA GIBS (NDVI, lluvia IMERG, temperatura de superficie, humedad SMAP) con leyenda y opacidad, y capa de **zonas de pendiente** recortadas a la forma del terreno.
2. **Suelo:** formulario (pH, materia orgánica %, textura, N, P, K como bajo/medio/alto, pendiente %) y **CSV** (arrastrar). Todo opcional; lo que falta se marca "dato faltante". Semáforo por variable con escala e intervalo ideal. Pendiente estimada automáticamente si está vacía.
3. **Evaluación del suelo ("suelo cansado")** con índice 0–100, qué lo limita y si la rotación actual **saca más de lo que devuelve**.
4. **Recomendaciones de cuidado del suelo** (qué hacer, por qué, prioridad alta/media/baja, base agronómica; sin dosis).
5. **Prioridades** (7 chips), **rotación actual** (hasta 3 cultivos), **condiciones** (riego, maquinaria, qué se vende cerca).
6. **Clima:** "el tiempo" ahora + 8 días; historia de 30 años con pestañas Temperatura, Lluvia, Humedad del suelo, Balance de agua, Extremos, Riesgos (probabilidades) y 2050; mapa de calor mes × año; resumen en filas; explicación de satélite vs. campo.
7. **Rotaciones:** recomendación principal con pasos concretos, comparación de 4–5 opciones, calendario Gantt con riesgos del año, evidencia, beneficios, riesgos, vacíos, "cómo se calculó", confianza, rango, sensibilidad automática, escenario ±lluvia/temperatura, radar y aporte por criterio.
8. **Plan:** hasta 3 siembras futuras con fechas, avisos, estudio de suelo tras cada cosecha y estimación de salud del suelo.
9. **Sensores en campo (IoT):** lecturas, alertas, tendencias día/semana/mes, cámara diaria, estado de equipos, comparación con NASA. Fuente: simulador, servidor puente o JSON pegado.
10. **Compartir y persistir:** guardar en el navegador, enlace compartible, WhatsApp, borrar datos.
11. **Reporte PDF** (corto: gráficos, recomendaciones y proceso).
12. **Caso de ejemplo** de 1 clic que funciona **sin internet** (copia real de NASA POWER incluida).
13. **Modo oscuro/claro**, letra grande, responsive (celular: hoja inferior).

## 5. Integraciones externas

Ninguna requiere clave ni cuenta; todas permiten CORS desde el navegador.

| Servicio | Endpoint | Uso | Notas |
|---|---|---|---|
| NASA POWER mensual | `https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M,T2M_MIN,T2M_MAX,PRECTOTCORR,GWETROOT,ALLSKY_SFC_SW_DWN,EVPTRNS&community=AG&longitude=…&latitude=…&start=1996&end=2025&format=JSON` | Clima base | `properties.parameter[VAR]["YYYYMM"]`; el mes `13` es el promedio anual (se ignora); valores ≤ −900 = faltante. `PRECTOTCORR` en mm/día; `EVPTRNS` en MJ/m²/día (÷2.45 → mm/día). Versión de la API en `header.api.version`. |
| NASA POWER diario | mismo, `/temporal/daily/point`, `parameters=T2M_MAX,T2M_MIN,PRECTOTCORR`, `start=19960101&end=20251231` | Calor extremo, heladas, lluvia intensa, racha seca | ~540 KB; se procesa a conteos por año y mes. |
| Open-Meteo pronóstico | `https://api.open-meteo.com/v1/forecast?...&current=…&hourly=…&daily=…&timezone=auto&forecast_days=8` | "El tiempo" | **No es NASA** |
| Open-Meteo elevación | `https://api.open-meteo.com/v1/elevation?latitude=a,b,…&longitude=…` (81 puntos, malla 9×9) | Pendiente y zonas de erosión | **No es NASA** (Copernicus DEM ~90 m). Si se consigue SRTM abierto con CORS, sustituir. |
| Open-Meteo clima futuro | `https://climate-api.open-meteo.com/v1/climate?...&start_date=1996-01-01&end_date=2050-12-31&models=EC_Earth3P_HR,MPI_ESM1_2_XR,MRI_AGCM3_2_S&daily=temperature_2m_mean,precipitation_sum` | Pestaña 2050 | **No es NASA**; tarda ~20 s; se agrega a medias y totales anuales. |
| NASA GIBS (WMTS) | `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{capa}/default/{fecha\|default}/GoogleMapsCompatible_Level{N}/{z}/{y}/{x}.png` | Capas visuales | Capas: `MODIS_Terra_L3_NDVI_Monthly` (N=7), `IMERG_Precipitation_Rate` (6), `MODIS_Terra_L3_Land_Surface_Temp_Monthly_Day` (6), `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture` (6). Solo visuales. |
| Mapa base | OpenStreetMap (`tile.openstreetmap.org`), Esri World Imagery | Fondo | El "oscuro" es OSM con un filtro CSS (CARTO ahora exige clave). |
| Buscador | `https://nominatim.openstreetmap.org/search` | Buscar lugar | Solo se envía el texto escrito. |

**Resiliencia (conservar):** reintento 1 vez con espera; *timeouts* (30 s mensual, 45 s diario); si falla la red se usa la **última copia guardada** de esa celda de 0.1° (y se avisa con su fecha); si no hay, se ofrece reintentar o ver datos de ejemplo claramente rotulados. Si falla solo el diario, se sigue con el mensual y las heladas se estiman con la Tmín mensual.

**Privacidad:** solo salen las coordenadas del centro (NASA POWER, Open-Meteo) y el texto del buscador (OSM). El estudio de suelo no sale del navegador.

## 6. Modelos de datos

### 6.1 Suelo (`S`)
```js
{ ph: 3–10|null, mo: 0–20|null, pend: 0–60|null,
  textura: 'arcilloso'|'franco'|'arenoso'|null, nit|fos|pot: 'bajo'|'medio'|'alto'|null }
```
**CSV:** encabezados `ph, mo, textura, n, p, k, pendiente` (acepta `;`, comas decimales y acentos; varias filas se promedian; N/P/K solo `bajo/medio/alto`).

### 6.2 Clima (`c = analizar(...)`)
```js
{ fuente, yrs:[1996..2025], nYears:29,
  d:{ yrs, m:{ tmean,tmin,tmax,rain,gw,sol,et: { [año]: [12 valores|null] } } },   // rain y et en mm/mes
  A:{ tmean,tmin,tmax,rain,gw,et: [valor anual por año] },
  T:{ tmean,rain,gw,et: {m,b,r2,n} },        // regresión lineal (m = pendiente por año)
  rainMes:[12 × {m,b,r2,n}],                  // tendencia de lluvia de cada mes
  early:{...}, recent:{...},                  // climatología mensual (12 valores) de 1996–2005 y 2016–2025
  // cada una: tmean,tmin,tmax, precip(mm/mes), gw(0–1), et(mm/mes) y, si hay diario: heat,frost,heavy (días/mes)
  Ea:[1996,2005], Rc:[2016,2025],
  daily:{ S:{heat,frost,heavy,dry}[por año], T:{…ols}, avgE:{…}, avgR:{…} } | null }
```

### 6.3 Estrategia (`evaluar` → `generar`)
```js
{ cs:[cultivos], nombre, total:0–100,
  dims:{ agua, ingreso, nitrogeno, erosion, mo, forraje, mercado, clima, suelo, resil },
  prio, pen,
  plan:{ multi:bool, items:[{ crop, s, mes:0–11, fit:0–1, anio, meses:[…] }] },   // con el clima reciente
  plan0:{…},                                                                      // con el clima antiguo
  // añadidos por generar():
  et, medalla, desc, actual?, esPlan?, rango:[min,max], conf:{ p:10–95, label:'Alta'|'Media'|'Baja', why:[…] } }
```

### 6.4 Estado compartible y almacenamiento
- **Enlace:** `…/index.html#s=` + Base64URL(JSON `{ p:[[lat,lng]…], f:{campo:valor}, pr:[ids], m:[ids], pa:bool }`). Campos `f`: `ph,mo,textura,nit,fos,pot,pend,rot1,rot2,rot3,plan1,plan2,plan3,riego,equipo`.
- **Todo estado importado se valida** (`estadoSeguro`): números en rango, opciones existentes, ids conocidos, polígono con ≥3 puntos numéricos válidos. Mantener esta validación en cualquier implementación.
- **localStorage:** `agronasa.v2` (estado), `agronasa.tema`, `agronasa.letra`, `agronasa.cache.<lat.1f>,<lon.1f>` (clima: `{fecha, version, p:{VAR:[360 valores, −999 = faltante]}, dd}`), `agronasa.proy.<lat.1f>,<lon.1f>` (proyecciones), `agronasa.iot` (origen) y `agronasa.iot.hist` (historial).

### 6.5 Sensores (contrato JSON) — ver también `SENSORES.md`
```json
{ "parcela_id": "…", "ultima_actualizacion": "ISO-8601",
  "lecturas_actuales": { "temp_ambiente_c":0, "temp_ambiente_min_noche_c":0, "humedad_ambiente_pct":0,
                         "temp_suelo_c":0, "humedad_suelo_pct":0, "viento_direccion":"NE", "viento_grados":45, "viento_velocidad_kmh":0 },
  "camara_diaria": { "fecha_anterior":"", "cobertura_verde_anterior_pct":0, "ndvi_anterior":0,
                     "fecha_actual":"", "cobertura_verde_actual_pct":0, "ndvi_actual":0, "url_foto_actual":"", "url_foto_anterior":"" },
  "equipos": [{ "nombre":"", "canal":"", "bateria_pct":0, "solar":true, "rssi_dbm":0, "snr_db":0, "hace_minutos":0 }],
  "historial": [{ "t":"ISO-8601", "temp_ambiente_c":0, "temp_suelo_c":0, "humedad_suelo_pct":0 }] }
```
Solo `lecturas_actuales` es obligatorio. **Se valida y sanea siempre** (`normalizarIot`): números, textos recortados, URLs de foto seguras (sin `javascript:` ni comillas). Servidor puente: `POST /api/iot/update`, `GET /api/iot/latest`; clave opcional `PUENTE_TOKEN` (`?token=` o `X-Token`).

## 7. Algoritmos y fórmulas (la parte que hay que reproducir fielmente)

### 7.1 Clima
- **Tendencias:** regresión lineal simple (OLS) sobre valores anuales; se reporta pendiente por década y **fuerza** según r²: ≥0.3 *clara*, ≥0.1 *moderada*, <0.1 *débil (la variación natural domina)*.
- **Periodos:** *antes* = primeros 10 años (1996–2005); *reciente* = últimos 10 (2016–2025).
- **Extremos (diarios):** calor = Tmáx ≥ 35 °C; helada = Tmín ≤ 2 °C; lluvia intensa = ≥ 50 mm/día; día seco = < 1 mm. Un mes tiene **riesgo de helada** si promedia ≥ 0.5 días de helada (sin datos diarios: Tmín media mensual ≤ 5 °C).
- **Estrés hídrico del mes:** `sP = 1 − min(1, P/ET)` (sin ET: `P/100`); `sG = 1 − min(1, GWETROOT/0.5)`; `estrés = 0.6·sP + 0.4·sG`. Los 3 meses más altos (> 0.05) se señalan.
- **Meses sin cultivo posible:** meses donde el mejor ajuste de cualquier cultivo de la base es < 0.55.
- **Probabilidades (pestaña Riesgos):** se parte la serie por la mitad; para cada mes, % de años con: mes seco (lluvia < 60 % de su promedio), calor (≥3 días), helada (≥1 día), lluvia intensa (≥1 día).
- **Proyecciones 2050:** por modelo, temperatura media anual y lluvia total anual; cambio = media 2031–2050 − media 1996–2015 de **ese mismo modelo**. Se muestra el rango entre modelos y cuántos coinciden. Es escenario, no pronóstico.
- **Pendiente:** malla de 9×9 puntos sobre la caja del terreno (lado mínimo 600 m); pendiente % por diferencias centrales; cada celda se recorta al polígono (Sutherland–Hodgman); clases: >8 % alta, 4–8 % media.

### 7.2 Ajuste climático de un cultivo en un mes (`ajusteMes`, 0–1)
```
fT = max(0, 1 − distancia_a_su_rango_óptimo / 6)
si helada del mes: fT *= 0.4 + 0.12·toleranciaHelada
si hay días de calor: fT *= 1 − min(0.3, díasCalor/20) · (Tmáx_óptima < 32 ? 1 : 0.4)
necesidad = {baja:60, media:100, alta:150} · (1 − 0.06·toleranciaSequía)        // mm/mes
w = min(1, lluvia/necesidad);  con humedad de suelo: w = 0.7·w + 0.3·min(1, gw/0.5)
riego: w = w + (1 − w)·{secano:0, limitado:0.4, completo:0.8}
ajuste = fT · w
```
`ajusteCiclo` = promedio de los meses que dura el ciclo (`ceil(díasCiclo/30)`, máx. 12). Una siembra es **"adecuada"** si ≥ 0.75. Cada cultivo/ventana se compara con el clima antiguo y el reciente: *"más favorable hoy"*, *"estable"*, *"se cerró"*, *"débil"*.

### 7.3 Calendario (`planificar`)
- Si la suma de ciclos ≤ 12 meses: búsqueda exhaustiva del mes de inicio (0–11) y de cada cultivo siguiente (sin solaparse y terminando antes de la siembra del año siguiente) que **maximiza la suma de ajustes**.
- Si no cabe: rotación de varios años; cada cultivo en su mejor mes.
- Perennes (alfalfa, caña) ocupan los 12 meses y se evalúan solos.
- Meses libres → se sugiere cobertura. El resultado se guarda en memoria por (clima, cultivos, riego).

### 7.4 Puntaje de una rotación (`evaluar`)
```
Puntaje = máx(0, 0.50·Prioridades + 0.35·Clima + 0.15·Suelo − Penalización)
```
- **Dimensiones por cultivo (promedio de los cultivos de la rotación):** `agua = min(100, {baja:100,media:60,alta:20}·0.7 + sequía·6)`; `ingreso = 20·ingreso`; `nitrógeno = fijaN ? 100 : 0`; `erosión = 20·eros`; `mo = 20·mo`; `forraje = 20·forraje`; `mercado = (hay lista) ? (está ? 100 : 40) : 50`; `suelo = 100·compatibilidad(pH, textura)`; `resiliencia = 10·(sequía + helada)`.
- **Clima** = 100 · promedio de los ajustes de cada siembra en su mes elegido.
- **Compatibilidad con suelo:** pH dentro del rango del cultivo = 1, fuera decae linealmente a 0 a 1.5 unidades; textura que prefiere = 1, otra = 0.6; sin dato = neutro (1).
- **Prioridades** = promedio ponderado de las 7 dimensiones con pesos: chip elegido = 3, no elegido = 1 (ninguno elegido → todos 1). **Ajustes automáticos:** nitrógeno bajo → +1.5 a "nitrógeno"; materia orgánica < 2 → +1.5 a "mo"; pendiente > 8 % o suelo arenoso → +1.5 a "erosión"; lluvia en descenso (r² ≥ 0.1) → +1 a "agua"; lluvias intensas en aumento (r² ≥ 0.1) → +1 a "erosión". La pantalla muestra cada peso "tú → aplicado".
- **Penalización:** 6 puntos por cada cultivo mecanizado si el usuario tiene equipo básico.
- **Traza:** `traza()` devuelve criterio, valor, peso y aporte; **la suma de aportes = puntaje** (hay una prueba automática).

### 7.5 Generación de alternativas (`generar`)
Candidatos: todas las parejas ordenadas de cultivos anuales distintos + cada perenne sola. Se muestran: **tu rotación actual** (si existe), **tu plan** (si existe) y tres alternativas que no repiten el conjunto de cultivos: **A · Mejor ajuste** (máx. puntaje), **B · Más resistente** (`0.5·clima + 0.3·agua + 0.2·resiliencia`), **C · Cuida el suelo** (`0.35·mo + 0.25·nitrógeno + 0.25·erosión + 0.15·clima`).

### 7.6 Incertidumbre
- **Rango:** puntaje mínimo y máximo con (a) clima reciente, (b) clima antiguo, (c) lluvia −15 %, (d) +1 °C.
- **Empate técnico:** diferencia < 5 puntos con la mejor opción.
- **Confianza (10–95):** `30 + 30·(datos de suelo/7) + 10 (humedad y ET disponibles) + 10 (datos diarios) − 10 por siembra con ajuste < 0.75 − 5 (pidió "mercado" sin indicar qué se vende)`. Clima de ejemplo: máximo 20. Etiqueta: ≥70 Alta, ≥45 Media, resto Baja. `conf.why` lista cada razón.
- **Sensibilidad automática:** ¿cambia la mejor opción con −15 % de lluvia, +1.5 °C, el clima antiguo o sin riego?
- **Escenario manual:** lluvia −30…+30 %, temperatura +0…+3 °C (afecta mensual; no los extremos diarios).

### 7.7 Salud del suelo (índice orientativo, requiere ≥ 2 datos)
Componentes (peso): materia orgánica 30 (`mo/3.5·100`), pH 20 (ideal 6–7, penaliza hasta 1.5 unidades), nitrógeno 15, fósforo 10, potasio 10 (bajo 25 / medio 70 / alto 100) y protección frente a erosión 15 (pendiente ≤2 %:100, ≤4:85, ≤8:55, ≤15:30, más:10; −10 si arenoso). Clases: ≥75 *en buen estado*, ≥55 *con señales de cansancio*, <55 *cansado*. Se indican los 2 componentes más bajos (< 60).

**Balance del cultivo:** `min(100, (mo + eros)·10 + (fijaN ? 20 : 0)) − 20·extracción`. El de la rotación es el promedio; > 15 *devuelve más de lo que saca*, < −15 *saca más de lo que devuelve*.

### 7.8 Plan (`cicloPlan`)
Parte del mes siguiente; cada siembra va en el mejor mes de los 12 siguientes (se prefiere la fecha más cercana salvo que otra sea > 0.03 mejor); cosecha = fin del ciclo; **estudio de suelo = mes siguiente a la cosecha**; luego la decisión (seguir con el siguiente cultivo si no bajaron MO/N y el pH sigue en 5.5–7.3; si no, intercalar cobertura o leguminosa). Avisos: misma familia que el cultivo anterior, cultivo exigente (extracción ≥ 4) con suelo cansado o N bajo, ajuste < 0.75, pH fuera de rango. **Salud estimada:** cada cultivo suma `balance·0.1` puntos (máx. ±10 por campaña), solo orientativo.

### 7.9 Reglas de cuidado del suelo (`tarjetasSuelo`)
pH < 5 *alta* / < 5.5 *media* (revisar encalado, **sin dosis**) / > 7.8 *alta* / > 7.3 *media*; MO < 2 *alta* / < 3 *media*; N bajo (*alta* si además MO < 2, si no *media*); P o K bajo *media*; pendiente > 8 *alta* / > 4 *media*; arenoso *media*; arcilloso *baja*; lluvia en descenso *media*; lluvias intensas en aumento *media*; suelo "cansado" *alta*; rotación que saca más de lo que devuelve *media*; datos faltantes *baja*. Cada tarjeta cita su **base agronómica** general.

### 7.10 Sensores (reglas automáticas)
Suelo seco < 30 % → *regar hoy*; 30–70 % óptimo; > 70 % saturado. Aire ≤ 2.5 °C helada; > 32 °C golpe de calor. Humedad del aire ≥ 75 % hongos. Viento ≥ 15 km/h no fumigar. Temperatura del suelo ≥ 15 °C favorece germinar (orientativo). Batería < 45 %; sin reporte > 60 min (salvo equipos con canal diario). **Comparación con NASA:** celda de la rejilla `[round(lat/0.5)·0.5, round(lon/0.625)·0.625]`; se contrasta la temperatura y la humedad medidas con la media mensual de NASA y con el pronóstico, y se aclara que son magnitudes distintas.

## 8. Base de cultivos (valores generales, **no validados localmente**)

Escala 0–5 salvo donde se indica; `ext` = extracción de nutrientes. `perenne` ocupa todo el año.

| id | Cultivo | Familia | Ciclo (d) | T óptima °C | Agua | Helada | Sequía | Fija N | Raíz cm | MO | Erosión | Ingreso | Forraje | Ext. | pH | Notas |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maiz | Maíz | gramínea | 130 | 20–30 | media | 1 | 2 | no | 100 | 4 | 3 | 3 | 3 | 5 | 5.8–7.5 | mecanizado |
| soya | Soya | leguminosa | 120 | 20–30 | media | 1 | 2 | sí | 80 | 2 | 2 | 4 | 2 | 3 | 5.8–7.0 | mecanizado |
| trigo | Trigo | gramínea | 120 | 12–24 | baja | 4 | 2 | no | 100 | 3 | 3 | 3 | 1 | 3 | 5.5–7.5 | mecanizado |
| sorgo | Sorgo | gramínea | 110 | 22–34 | baja | 1 | 4 | no | 150 | 4 | 3 | 3 | 4 | 4 | 5.5–8.0 | mecanizado |
| girasol | Girasol | asterácea | 120 | 18–30 | baja | 2 | 3 | no | 150 | 2 | 2 | 4 | 1 | 4 | 6.0–7.5 | mecanizado |
| frijol | Frijol | leguminosa | 90 | 16–27 | media | 0 | 1 | sí | 50 | 2 | 2 | 3 | 1 | 2 | 6.0–7.0 | |
| mani | Maní | leguminosa | 120 | 22–32 | baja | 0 | 3 | sí | 60 | 2 | 2 | 4 | 2 | 3 | 5.8–7.0 | |
| avena | Avena | gramínea | 110 | 10–22 | media | 4 | 2 | no | 80 | 3 | 4 | 2 | 4 | 2 | 5.0–7.0 | |
| alfalfa | Alfalfa | leguminosa | 360 | 15–28 | media | 3 | 4 | sí | 200 | 4 | 4 | 3 | 5 | 3 | 6.5–7.8 | perenne |
| cobertura | Cobertura de leguminosas | leguminosa | 120 | 18–32 | baja | 1 | 3 | sí | 80 | 5 | 5 | 0 | 2 | 0 | 5.0–7.5 | cobertura (no se vende) |
| cana | Caña de azúcar | gramínea | 360 | 22–32 | alta | 1 | 2 | no | 120 | 4 | 4 | 4 | 2 | 5 | 5.5–7.5 | perenne, mecanizado |
| yuca | Yuca | euforbiácea | 270 | 20–30 | media | 0 | 4 | no | 80 | 2 | 2 | 3 | 1 | 4 | 4.5–7.0 | |

Cada cultivo también lleva las **texturas preferidas** (`tex`). Está en el arreglo `CULTIVOS` del código. Si el equipo tiene una base mejor o validada, reemplazarla respetando estos campos.

## 9. Reporte PDF (contenido mínimo)
Encabezado con logo, fecha, área y fuente del clima · **Lo más importante** (frases) · croquis del terreno + estado del suelo (semáforo) · gráficos del clima con una línea de lectura · tabla comparativa de rotaciones + radar + aporte por criterio · calendario por rotación con hasta 3 riesgos · acciones de cuidado del suelo · proceso del plan · aviso final. **Reporte corto:** el detalle completo queda en pantalla. Se activó la compresión de imágenes (de 13 MB a ~0.5 MB): no desactivarla.

## 10. Mapa de la interfaz a la lógica (para quien rehaga la UI)

| Componente de UI | Entrada / evento | Función que debe invocar | Salida a mostrar |
|---|---|---|---|
| Mapa (dibujar/editar/borrar) | `draw:created/edited/deleted` | `terrenoCambio()` → `cargarClima()`, `cargarRelieve()`, `cargarTiempo()` | área, centro, relieve, clima |
| Formulario de suelo / CSV | `input` / archivo | `leerSuelo()`, `leerCSV()`, `estadoSuelo()`, `programar()` | semáforo, salud, tarjetas |
| Chips y selects | `input` | `programar()` → `mostrar()` | resultados recalculados |
| Resultados | — | `mostrar()` (usa `pesos`, `generar`, `sensibilidad`, `resumenTexto`, `pintarReco`) | recomendación, opciones, gráficos |
| Pestañas del clima | clic | `dibujarTab()`, `cfgsTab()`, `textoTab()` | gráficos + lectura |
| Plan | selects | `pintarPlan()`, `cicloPlan()` | pasos, avisos, gráfico de salud |
| Sensores | origen/escenario | `iotTick()`, `normalizarIot()`, `pintarIot()` | lecturas, alertas, tendencias |
| Compartir | clic | `enlace()`, `textoCompartir()` | enlace / WhatsApp |
| Generar reporte | clic | `reporte()` | PDF |
| Caso de ejemplo | clic | `casoEjemplo()` (usa `cargarClima('guardado')`) | todo, sin internet |

`cargarClima(modo)`: `undefined` = consultar NASA (con caché de respaldo), `'guardado'` = copia incluida de Montero, `'sintetico'` = datos de ejemplo **rotulados "NO NASA"**.

## 11. Cómo fusionarlo con otro proyecto (recomendación)

1. **Congelar la lógica de dominio.** Las secciones *Tendencias, Probabilidades, Proyecciones, Salud del suelo, Plan, Cuidado del suelo, Rotaciones (hasta `traza`/`sensibilidad`/`confianza`), Sensores (`normalizarIot`, `estadosIot`, `alertasIot`, `fusionIot`)* son funciones casi puras. Extraerlas a un módulo (`dominio.js`) sin tocar su comportamiento.
2. **Resolver el acoplamiento con el DOM/estado global.** Hoy estas funciones leen datos de la interfaz o de `state`, y hay que pasarlos como parámetros:
   - `leerSuelo()`, `leerRotacion()`, `leerPlan()` leen el DOM.
   - `ajusteMes`, `planificar` (clave de caché) y `traza`/`riesgos` leen `state.riego` y `state.equipo`.
   - `evaluar` lee `state.mercado`; `pesos` lee `state.prio`; `confianza` lee `state.prio/mercado/pendAuto`.
   - `escenario` recibe lluvia/temperatura, pero `mostrar()` lee `state.esc`.
   Propuesta: una función `calcular({ suelo, rotacionActual, plan, prioridades, mercado, riego, equipo, escenario, clima })` que devuelva `{ salud, tarjetas, estrategias, sensibilidad, resumen }`.
3. **Mantener los contratos** de la sección 6 (suelo, clima, estrategia, estado compartible, JSON de sensores).
4. **Reutilizar la capa de datos** (`pedir`, `consultarMensual/Diario`, `organizar`, `procesarDiario`, caché y copia de ejemplo) tal cual; está probada contra datos reales.
5. **Reconstruir solo la capa visual** con el sistema de diseño del otro proyecto, siguiendo la sección 4 (funcionalidades) y la sección 2 (reglas que no cambian).
6. **Si ya existe un backend** en el otro proyecto: las consultas a NASA/Open-Meteo pueden moverse al servidor (con la misma caché), pero **el estudio de suelo debe seguir sin salir del dispositivo** salvo consentimiento explícito.
7. **Conflictos típicos al unir:** IDs del DOM duplicados (la app usa ids fijos: `ph, mo, textura, nit, fos, pot, pend, rot1–3, plan1–3, riego, equipo, map, panel…`), claves de `localStorage` (todas con prefijo `agronasa.`), variables globales de Leaflet/Chart y versiones de librerías.
8. **Verificar con las pruebas**, adaptando el cargador si el código deja de estar en `index.html`.

### Librerías (por CDN, versión exacta)
Leaflet 1.9.4 · leaflet-draw 1.0.4 · Chart.js 4.4.1 · jsPDF 2.5.1 · Google Fonts (Orbitron, Rajdhani, Inter, JetBrains Mono). Ya no se usa html2canvas.

## 12. Pruebas y criterios de aceptación

`node tests/run-tests.js` (Node 18+, requiere internet): carga la lógica con un DOM simulado y consulta NASA POWER real en **3 climas** (trópico: Santa Cruz; templado con heladas: Madrid; semiárido: Niamey). **53 comprobaciones** que verifican, entre otras: regresión lineal exacta, puntajes 0–100, rango que contiene al puntaje, traza que suma el total, calendarios sin solapamiento, heladas donde corresponde, probabilidades 0–100, plan con fechas ordenadas, salud del suelo, proyecciones, reglas y saneamiento de sensores, recorte del terreno y validación del estado importado.

La versión fusionada debería cumplir además:
- [ ] El caso de ejemplo funciona **sin internet** y trae datos reales rotulados con su fecha.
- [ ] Cualquier dato no NASA está rotulado; los datos sintéticos dicen "NO NASA".
- [ ] El aviso de validar con un agrónomo es visible siempre y aparece en el PDF.
- [ ] Un enlace compartido con ids inventados no rompe la app ni el PDF.
- [ ] Los textos que vienen de fuera (JSON de sensores, CSV, APIs, enlace) se escapan antes de insertarse en el HTML.
- [ ] Sin errores de consola ni desbordes horizontales en 390 px y 1440 px; modo claro y oscuro legibles.
- [ ] El PDF se genera sin error y pesa del orden de 0.5 MB.

## 13. Limitaciones que el otro equipo debe conocer
- NASA POWER tiene celdas de ~50 km: no capta el microclima del terreno. Muchas tendencias a 30 años son débiles (la app lo dice).
- La **base de cultivos, los umbrales y el índice de salud del suelo son heurísticas** nuestras, sin validación agronómica local; no hay precios, costos, variedades ni plagas locales.
- Las alternativas son de 1 año con 2 cultivos (o un perenne); no hay optimización de varios años.
- SMAP, ECOSTRESS, GPM y Landsat en **números** (no solo capas) requieren cuenta de NASA Earthdata y no están integrados; la pendiente no usa SRTM.
- La comparación sensores–NASA es orientativa (unidades y escalas distintas). La cobertura verde y el NDVI de la cámara los calcula el módulo de cámara, no esta app.
- No se probó en Safari ni Firefox, ni con hardware físico de sensores.

## 14. Archivos del proyecto

| Archivo | Contenido |
|---|---|
| `index.html` | La aplicación completa (incluye logo y copia real de NASA POWER de Montero) |
| `sensores-puente.js` | Servidor de enlace con la demo de sensores (Node, sin dependencias) |
| `sensores-ejemplo.json` | Ejemplo del contrato de sensores |
| `SENSORES.md` | Guía del módulo de sensores |
| `tests/run-tests.js` | Pruebas de lógica con datos reales |
| `README.md`, `PITCH.md`, `DEMO.md` | Documentación, pitch y guion de demo |
| `respaldos/` | Versiones anteriores del diseño |
