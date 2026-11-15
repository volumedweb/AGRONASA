---
name: iot-nasa-fusion
description: >-
  Playbook de fusión de datos satelitales (NASA POWER + MODIS NDVI) con telemetría IoT LoRaWAN en campo.
  Úsala al acoplar sensores físicos o simuladores de otra demo con el motor agroclimático de AgroNASA.
---

# Fusión Satélite NASA POWER + Sensores IoT LoRaWAN

Guía para combinar la macro-escala satelital (~50 km) con la micro-escala de parcela (<1 km).

## Reglas de Fusión Agroclimática

1. **Cruce Temperatura Aire (`T2M` vs. Nodo #01)**
   - Calcular `delta_t2m_c = temp_ambiente_c - nasa_t2m_c`.
   - Si `temp_min_24h_c <= 2.5`, activar alerta temprana de helada local aunque la media mensual de la celda NASA sea superior.
2. **Cruce Humedad de Suelo (`GWETROOT` vs. Sonda #02)**
   - Convertir `GWETROOT` (0–1) a porcentaje (`0–100 %`) y comparar con `humedad_suelo_pct` medido a 15–30 cm.
   - Si `humedad_suelo_pct < 30 %`, marcar estado `seco` y recomendar riego prioritario.
3. **Cruce Vigor Vegetal (`MODIS_NDVI` vs. Cámara Fenológica)**
   - Comparar el índice satelital `ndvi` de la celda con el porcentaje de cobertura verde (`cobertura_verde_pct`) e índice NDVI local calculado en terreno.
4. **Ventana de Aplicación Fitosanitaria (Veleta #01)**
   - Evaluar `viento_velocidad_kmh`: óptimo `< 15 km/h` y sin probabilidad alta de lluvia en las próximas horas.
