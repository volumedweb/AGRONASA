# 📡 Guía del Módulo de Sensores en Campo (IoT LoRaWAN) y Acoplamiento para Demo

> **Propósito de este documento:** Explicar de forma clara, técnica y práctica **cómo funciona el apartado de Sensores en Campo**, **de qué partes consta para mostrar la información** y **cómo conectarlo o acoplarlo fácilmente con la otra demo** (ya sea hardware físico con sensores reales, un gateway LoRa/ESP32 o un simulador externo).

---

## 1. ¿Cómo funciona el módulo dentro del proyecto AgroNASA?

AgroNASA combina **dos escalas de observación** que se complementan entre sí:

1. **Escala Macro / Regional (Satélite NASA POWER + MODIS NDVI):**
   - Cubre celdas de ~50 km (`0.5° × 0.625°`) con más de 20 años de historial climático.
   - Sirve para saber qué cultivos son viables en la zona, en qué mes sembrar y si la región atraviesa una anomalía histórica de sequía o exceso de lluvia.
2. **Escala Micro / Parcela (Sensores en Campo IoT LoRaWAN + Cámara Diaria):**
   - Mide lo que pasa **hoy y cada pocos minutos dentro de la parcela exacta** del agricultor.
   - Corrige el efecto de microclimas (laderas, valles cerrados, retención real de agua del terreno) que el satélite no puede ver por su resolución.

### Flujo de funcionamiento de punta a punta

```text
[Nodos en Parcela] ──(Radio LoRa)──▶ [Gateway LoRaWAN] ──(Internet)──▶ [Backend AgroNASA] ──▶ [Dashboard Web]
  • Aire y Viento                                                             ▲
  • Sonda de Suelo                                                            │
                                                                              │
[Cámara Fija Solar] ───────────────(4G / LTE o Wi-Fi: 1 foto/día)─────────────┘
```

1. **Captura en terreno:** Los nodos miden las variables agroclimáticas cada 15–30 minutos y duermen el resto del tiempo para ahorrar batería.
2. **Transmisión dividida por peso de datos:**
   - **Datos numéricos ligeros (Temperatura, Humedad, Viento, Batería):** Viajan por radio **LoRaWAN** hasta el Gateway sin usar planes de datos móviles por sensor.
   - **Fotografía diaria del cultivo:** Como una imagen es demasiado pesada para LoRaWAN, la cámara se enciende una vez al día (12:00 m.) y envía la foto por **4G/LTE o Wi-Fi** (o tarjeta SD).
3. **Cruce con NASA POWER:** El backend compara el dato medido en la parcela con el dato satelital de la celda NASA POWER (por ejemplo: *"Satélite estima 43% de humedad regional, pero la Sonda #02 mide 26% en tu parcela → regar hoy"*).
4. **Visualización en el Dashboard:** El usuario ve en una sola pantalla las lecturas actuales, alertas de riego/helada, tendencias, fotos comparativas y salud de las baterías.

---

## 2. ¿De qué consta el apartado para mostrar información? (Los 5 bloques visuales)

En el dashboard ([`frontend/dist/index.html`](file:///home/brayan/Documentos/hakaton%20proyecto%202/frontend/dist/index.html) y el mockup dedicado [`docs/mockup_dashboard_iot_lorawan.html`](file:///home/brayan/Documentos/hakaton%20proyecto%202/docs/mockup_dashboard_iot_lorawan.html)), la información se divide en **5 bloques claros**:

### Bloque 1: Tarjetas de Alertas Locales y Fusión Satélite + Terreno
Muestra avisos inmediatos cuando un sensor cruza un umbral crítico y compara la lectura local con la celda de **NASA POWER**:
- **Alerta de parcela:** Ejemplo: *"Sonda #02: La humedad del suelo bajó a 26 % (umbral de riego: 30 %)"*.
- **Comparativa Satélite NASA + Sensores:** Muestra la celda NASA activa (`[lat°, lon°]`), la temperatura media satelital (`T2M`), la humedad radicular satelital (`GWETROOT`) y el `NDVI` frente al microclima real medido por los sensores.

### Bloque 2: Las 5 Tarjetas de Variables en Tiempo Real
Cada tarjeta muestra **nombre de la variable**, **valor actual con unidad**, **estado interpretado en lenguaje simple para el agricultor**, **nodo de origen** y **hace cuántos minutos se leyó**:

| # | Variable mostrada | Sensor físico | Frecuencia | Qué le dice al agricultor en pantalla |
| :- | :--- | :--- | :--- | :--- |
| **1** | **🌡️ Temperatura ambiente** | Sensor digital de aire (ej. SHT31 / BME280) | Cada 15 min | Valor en `°C` + mínima nocturna para alertar **heladas** (`< 2 °C`) o golpes de calor (`> 35 °C`). |
| **2** | **💧 Humedad ambiente** | Sensor digital de aire | Cada 15 min | Valor en `%` + aviso de **riesgo de hongos** si supera el `75–80 %` sostenido. |
| **3** | **🌱 Temperatura del suelo** | Sonda impermeable enterrada (15–20 cm, ej. DS18B20) | Cada 30 min | Valor en `°C` + indicador de si el suelo tiene la temperatura óptima para **sembrar y germinar**. |
| **4** | **🌊 Humedad del suelo** | Sonda capacitiva enterrada (ej. RS485 / capacitiva) | Cada 30 min | Valor en `%` + semáforo de riego (**Seco `< 30 %`**, **Óptimo `40–65 %`**, **Saturado `> 75 %`**). |
| **5** | **🧭 Dirección y velocidad del viento** | Veleta + anemómetro | Cada 15 min | Rumbo cardinal (`NE`, `SO`, grados) y `km/h` + aviso de si es **seguro fumigar** (`< 15 km/h`). |

### Bloque 3: Gráfico de Tendencias (Día / Semana / Mes)
Permite cambiar entre **Día (24 h)**, **Semana (7 días)** y **Mes (30 días)** para ver:
- Cómo baja la curva de **humedad del suelo (%)** día tras día después de una lluvia o riego.
- El ciclo diario de **temperatura del aire (°C)** frente a la **temperatura del suelo (°C)** (que es más estable).

### Bloque 4: Cámara Diaria del Terreno (Time-Lapse y Cobertura Verde)
Muestra dos cuadros comparativos (*Fecha anterior* vs. *Foto de hoy a las 12:00*):
- Calcula el **porcentaje de cobertura verde (%)** de las hojas sobre la tierra.
- Lo compara con el índice satelital **MODIS NDVI** (`0.0` a `1.0`) para confirmar visualmente que el cultivo está creciendo sano.

### Bloque 5: Estado de los Equipos (Diagnóstico de Red LoRaWAN)
Una lista/tabla técnica para saber si todos los dispositivos en el campo están funcionando:
- **Nombre del equipo:** `Nodo #01 (Aire + Veleta)`, `Nodo #02 (Suelo Norte)`, `Nodo #03 (Suelo Sur)`, `Gateway Solar`, `Cámara 4G`.
- **Nivel de batería (`%`) y fuente:** Indicando cuáles tienen panel solar (`☀`) y marcando en rojo/naranja si alguna batería baja del `45 %`.
- **Calidad de señal de radio (`RSSI` en `dBm` y `SNR`):** Por ejemplo `-78 dBm` (excelente) o `-95 dBm` (límite de alcance).
- **Hora de la última conexión:** Para detectar rápido si un nodo dejó de reportar.

---

## 3. ¿Cómo acoplarlo con la otra demo? (Formato de datos e integración)

Si en la otra demo están montando **sensores físicos** (por ejemplo con Arduino, ESP32, nodo LoRaWAN, Raspberry Pi o un script en Python/Node.js), **no necesitan reescribir el dashboard**. Solo necesitan enviar o compartir un objeto JSON con esta estructura.

### 3.1 Estructura JSON estándar que espera el Dashboard

Este es el contrato de datos sencillo para alimentar todas las tarjetas del apartado de sensores:

```json
{
  "parcela_id": "parcela_valle_01",
  "ultima_actualizacion": "2026-11-14T12:05:00-04:00",
  "lecturas_actuales": {
    "temp_ambiente_c": 22.4,
    "temp_ambiente_min_noche_c": 8.4,
    "humedad_ambiente_pct": 54.0,
    "temp_suelo_c": 18.9,
    "humedad_suelo_pct": 26.0,
    "viento_direccion": "NE",
    "viento_grados": 45,
    "viento_velocidad_kmh": 11.0
  },
  "camara_diaria": {
    "fecha_anterior": "25 Oct",
    "cobertura_verde_anterior_pct": 24,
    "ndvi_anterior": 0.34,
    "fecha_actual": "Hoy 14 Nov",
    "cobertura_verde_actual_pct": 58,
    "ndvi_actual": 0.48,
    "url_foto_actual": "/fotos/parcela_hoy.jpg"
  },
  "equipos": [
    {
      "id": "nodo_01",
      "nombre": "Nodo #01 · aire + veleta",
      "canal": "LoRaWAN 15 min",
      "bateria_pct": 94,
      "solar": true,
      "rssi_dbm": -78,
      "hace_minutos": 4
    },
    {
      "id": "nodo_02",
      "nombre": "Nodo #02 · suelo norte",
      "canal": "LoRaWAN 30 min",
      "bateria_pct": 88,
      "solar": false,
      "rssi_dbm": -89,
      "hace_minutos": 12
    }
  ]
}
```

---

### 3.2 Reglas simples para calcular los textos automáticos en la demo

Si la otra demo envía valores en vivo (por ejemplo, calentando el sensor con la mano o metiendo la sonda de suelo en un vaso con agua durante la presentación ante el jurado), el dashboard cambia automáticamente el estado con estas 4 reglas:

1. **Humedad del suelo (`humedad_suelo_pct`):**
   - `< 30 %`: Tarjeta en color naranja/rojo → `⚠️ Suelo seco: regar hoy` (activa la alerta principal).
   - `30 % a 70 %`: Tarjeta en verde → `✓ Humedad óptima en raíces`.
   - `> 70 %`: Tarjeta en amarillo → `⚠️ Suelo saturado: evitar riego`.
2. **Temperatura ambiente (`temp_ambiente_c`):**
   - `<= 2.5 °C`: `🚨 Riesgo de helada en parcela`.
   - `2.6 °C a 32 °C`: `✓ Sin helada ni estrés térmico`.
   - `> 32 °C`: `⚠️ Golpe de calor: revisar evaporación`.
3. **Humedad ambiente (`humedad_ambiente_pct`):**
   - `< 75 %`: `✓ Riesgo de hongos bajo`.
   - `>= 75 %`: `⚠️ Humedad alta: vigilar hongos foliares`.
4. **Viento (`viento_velocidad_kmh`):**
   - `< 15 km/h`: `✓ Apto para fumigar`.
   - `>= 15 km/h`: `⚠️ Viento fuerte: no fumigar ahora`.

---

### 3.3 Tres formas rápidas de conectar ambas demos el día de la presentación

Dependiendo de cómo esté hecha la otra demo, pueden elegir cualquiera de estas **3 opciones**:

#### Opción A (La más fácil si la otra demo corre en otra laptop o microcontrolador): Endpoint en FastAPI
Agregamos o usamos una ruta en el backend de AgroNASA (`POST /api/iot/update` y `GET /api/iot/latest`):
1. La otra demo hace un `POST http://<IP_DE_AGRONASA>:8000/api/iot/update` cada 5 segundos con las lecturas de los sensores reales.
2. El frontend de AgroNASA consulta `GET /api/iot/latest` y actualiza las tarjetas de `<details class="seccion iot">` en vivo sin recargar la página.

#### Opción B (Si la otra demo escribe un archivo JSON o corre en la misma PC)
1. La otra demo guarda las lecturas en un archivo local (por ejemplo `backend/data/iot_live.json`).
2. AgroNASA lee ese archivo y muestra los cambios al instante en el mapa y en las tarjetas de sensores.

#### Opción C (Para mostrar el Dashboard IoT en pantalla completa junto a la maqueta física)
- Pueden abrir directamente [`docs/mockup_dashboard_iot_lorawan.html`](file:///home/brayan/Documentos/hakaton%20proyecto%202/docs/mockup_dashboard_iot_lorawan.html) en un monitor secundario al lado de la maqueta de sensores, mientras en el monitor principal muestran el mapa interactivo satelital ([`frontend/dist/index.html`](file:///home/brayan/Documentos/hakaton%20proyecto%202/frontend/dist/index.html)).

---

## 4. Resumen para explicar al jurado en 20 segundos

> *"El satélite de la NASA nos da 20 años de historia climática en celdas de 50 kilómetros para planificar la campaña agrícola, y nuestro módulo de sensores LoRaWAN en campo mide cada 15 minutos la humedad y temperatura real de la parcela sin necesitar cables ni internet por sensor, validando en terreno cuándo regar o proteger contra heladas."*
