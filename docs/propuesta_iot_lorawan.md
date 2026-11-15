# Propuesta a futuro: módulo IoT de monitoreo en campo (LoRaWAN)

> **Estado:** propuesta para una posible implementación futura. No forma parte del prototipo actual de AgroNASA.

---

## 1. Resumen

AgroNASA hoy trabaja con datos satelitales (NASA POWER y MODIS NDVI), que describen la tendencia climática de una zona de decenas de kilómetros. Esta propuesta agrega un **sistema IoT (Internet of Things) instalado en el terreno** que mide las condiciones reales de la parcela y las muestra en un **apartado propio del dashboard**, separado del monitoreo satelital.

El sistema se compone de:

- **Sensores LoRaWAN** de temperatura y humedad (ambiente y suelo) y de dirección del viento.
- **Una cámara** que fotografía el terreno una vez al día.
- **Un apartado "Sensores en campo"** en el dashboard, con valores actuales y tendencias.

---

## 2. Por qué LoRaWAN

| Necesidad del terreno agrícola | Cómo responde LoRaWAN |
| :---- | :---- |
| No hay cableado eléctrico ni de datos | Comunicación inalámbrica; los nodos funcionan con batería o panel solar pequeño |
| Bajo consumo | Los nodos duermen entre mediciones; una batería puede durar años |
| Parcelas extensas y alejadas | Alcance de varios kilómetros en campo abierto con un solo gateway |
| Bajo costo de operación | Usa bandas de radio sin licencia; no requiere un plan de datos por sensor |

**Limitación a tener en cuenta:** LoRaWAN transmite muy pocos datos por mensaje. Sirve para lecturas de sensores, pero **no para enviar fotografías** (ver sección 4).

---

## 3. Variables a medir

| Variable | Sensor | Frecuencia sugerida | Para qué sirve |
| :---- | :---- | :---- | :---- |
| Temperatura del ambiente | Sensor de temperatura/humedad de aire | Cada 15–30 min | Detectar heladas y golpes de calor |
| Humedad del ambiente | El mismo sensor de aire | Cada 15–30 min | Riesgo de enfermedades por hongos, evapotranspiración |
| Temperatura del suelo | Sonda enterrada | Cada 30–60 min | Momento adecuado de siembra y germinación |
| Humedad del suelo | Sonda capacitiva enterrada | Cada 30–60 min | Decidir cuándo y cuánto regar |
| Dirección del viento | Veleta | Cada 15–30 min | Planificar fumigación, entender el avance de heladas y plagas |
| Imagen del terreno | Cámara fija | 1 foto al día | Registro visual de la evolución del cultivo |

> **Nota:** "dirección" se interpretó como **dirección del viento**. Si se refería a otra cosa (por ejemplo, la ubicación u orientación de cada sensor), hay que ajustar esta fila.

---

## 4. Cámara diaria del terreno

- Toma **una fotografía al día**, siempre a la misma hora y desde el mismo punto fijo, para que las imágenes sean comparables.
- Con el historial de fotos se puede:
  - Armar una línea de tiempo (time-lapse) del crecimiento del cultivo.
  - Calcular un índice de cobertura verde y graficar su tendencia.
  - Comparar lo que se ve en el terreno con el NDVI satelital.
- **Conectividad:** como una foto es demasiado grande para LoRaWAN, la cámara necesita otro canal: red celular (4G/LTE), Wi-Fi si hay cobertura cerca, o guardar en tarjeta SD y recoger las fotos manualmente.
- **Energía:** panel solar pequeño con batería; la cámara solo se enciende para tomar y enviar la foto.

---

## 5. Arquitectura propuesta

```
┌────────────────────┐   LoRa    ┌──────────────┐  Internet  ┌───────────────────┐
│ Nodos sensores     │ ────────▶ │   Gateway    │ ─────────▶ │ Servidor de red   │
│ (aire, suelo,      │           │   LoRaWAN    │            │ LoRaWAN           │
│  viento)           │           └──────────────┘            └─────────┬─────────┘
└────────────────────┘                                                 │
                                                                       ▼
┌────────────────────┐        4G / Wi-Fi                     ┌───────────────────┐
│ Cámara (1 foto/día)│ ────────────────────────────────────▶ │ Backend AgroNASA  │
└────────────────────┘                                       │ (FastAPI)         │
                                                             │ - lecturas        │
                                                             │ - fotos           │
                                                             │ - tendencias      │
                                                             └─────────┬─────────┘
                                                                       ▼
                                                             ┌───────────────────┐
                                                             │ Dashboard         │
                                                             │ "Sensores en      │
                                                             │  campo"           │
                                                             └───────────────────┘
```

1. Los nodos envían sus lecturas por radio al gateway.
2. El gateway las reenvía por internet al servidor de red LoRaWAN (por ejemplo The Things Network o ChirpStack).
3. El servidor de red entrega cada lectura al backend de AgroNASA.
4. El backend guarda lecturas y fotos con fecha y hora, y calcula las tendencias.
5. El dashboard muestra los datos en su apartado propio.

---

## 6. Apartado "Sensores en campo" en el dashboard

Se muestra como una sección aparte del monitoreo satelital:

- **Valores actuales:** una tarjeta por variable (temperatura y humedad del ambiente, temperatura y humedad del suelo, dirección del viento), con la hora de la última lectura.
- **Tendencias:** gráficos por día, semana y mes de cada variable.
- **Galería de fotos:** la foto del día y el historial, con opción de comparar dos fechas.
- **Estado de los equipos:** nivel de batería y última conexión de cada nodo.
- **Alertas locales:** avisos cuando una variable cruza un umbral (por ejemplo, suelo muy seco o temperatura cercana a helada).

---

## 7. Cómo se complementa con el monitoreo satelital

| | Satélite (actual) | Sensores en campo (propuesta) |
| :---- | :---- | :---- |
| Escala | Zona de decenas de km | La parcela exacta |
| Actualización | Con días de retraso | Cada pocos minutos |
| Historial | 20 años o más | Desde que se instala |
| Costo de equipos | Ninguno | Sensores, gateway y cámara |

El satélite aporta el contexto histórico y regional; los sensores aportan el dato real y actual de la parcela. Juntos permiten:

- Ajustar las recomendaciones de cultivo con datos medidos en el terreno, no solo estimados.
- Validar las alertas satelitales de sequía o helada con lo que ocurre realmente en la parcela.
- Cubrir los microclimas de valles y altiplano que la malla satelital no captura.

---

## 8. Puntos por definir antes de implementar

- Banda de frecuencia LoRaWAN permitida en el país de instalación.
- Modelos y costo de los sensores, el gateway y la cámara.
- Cantidad de nodos por parcela y ubicación del gateway (necesita energía e internet).
- Canal de conexión de la cámara según la cobertura celular de la zona.
- Servidor de red a usar (servicio público o instalación propia).
- Base de datos para las lecturas y almacenamiento para las fotos.
