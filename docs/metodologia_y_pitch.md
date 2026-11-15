# Metodología Agroclimática y Guion de Pitch — AgroNASA

## 1. Metodología Científica

### 1.1 Fuentes de datos de la NASA
1. **NASA POWER (`community=AG`, Agroclimatología):**
   - `T2M`, `T2M_MAX`, `T2M_MIN`: Temperatura media, máxima y mínima a 2 metros (°C).
   - `PRECTOTCORR`: Precipitación corregida (mm/día), transformada a acumulado mensual y de ventana fenológica.
   - `RH2M`: Humedad relativa a 2 metros (%).
   - `GWETROOT`: Humedad en zona radicular (fracción 0 a 1).
   - `ALLSKY_SFC_SW_DWN`: Radiación solar incidente en superficie.
2. **MODIS NDVI (Índice de Vegetación de Diferencia Normalizada):**
   - Curva mensual de salud histórica de la vegetación para contextualizar el estrés hídrico de la celda.

### 1.2 Motor Trapezoidal de Aptitud (FAO EcoCrop)
Cada cultivo en `backend/data/crops.json` define rangos absolutos (`abs_min`, `abs_max`) y óptimos (`opt_min`, `opt_max`) de temperatura, precipitación acumulada en el ciclo y pH de suelo:
- Fuera de `[abs_min, abs_max]`: factor = `0.0`.
- Dentro de `[opt_min, opt_max]`: factor = `1.0`.
- Tramos intermedios: interpolación lineal.
- Puntaje global (0 a 100): media geométrica ponderada de los factores climáticos y edáficos. Si un factor crítico vale `0`, el puntaje total cae a `0`.

### 1.3 Alertas por Percentil Histórico (No Pronóstico)
Comparamos la lluvia acumulada de los últimos 30 y 60 días frente a la distribución histórica de los últimos 20 años para esa misma época:
- `< 10`: Sequía severa (Rojo)
- `10 – 25`: Déficit de lluvia (Naranja)
- `25 – 75`: Normal (Verde)
- `75 – 90`: Exceso de lluvia (Naranja)
- `> 90`: Exceso extremo / riesgo de inundación (Rojo)

---

## 2. Guion de Pitch (3 Minutos)

1. **Problema (30 s):**
   Los pequeños agricultores deciden qué y cuándo sembrar con poca información climática localizada, mientras el cambio climático vuelve cada vez más inciertas las lluvias, las heladas y las sequías.
2. **Solución (30 s):**
   Con **AgroNASA**, el agricultor hace clic en su parcela en el mapa y los datos satelitales de la NASA se traducen en un ranking explicado de qué sembrar, alertas de anomalías hídricas y un ciclo de rotación regenerativa.
3. **Demo en vivo (60 s):**
   - Seleccionar **Altiplano (La Paz)** → destacan Quinua, Haba y Papa; alerta por heladas nocturnas.
   - Seleccionar **Valles (Cochabamba)** o **Llanos (Santa Cruz)** → cambio automático de ranking y gráficos mensuales de NASA POWER + MODIS NDVI.
   - Ingresar datos de suelo → recálculo inmediato y plan de rotación en 4 ciclos (Cereal → Leguminosa fijadora de N → Tubérculo/Raíz → Abono verde).
4. **Uso de datos NASA e Impacto (60 s):**
   - Combinamos NASA POWER (`AG`) + MODIS NDVI con caché inteligente por celda (`0.5° × 0.625°`).
   - Honestidad técnica: comunicamos anomalías frente al histórico de 20 años (no pronósticos futuros) y recomendamos validar con técnicos agrónomos locales.
