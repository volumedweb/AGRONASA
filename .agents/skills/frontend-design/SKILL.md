---
name: frontend-design
description: >-
  Estándares de diseño de interfaces de alto nivel basados en waybarrios/opencode-power-pack.
  Úsala al crear o mejorar componentes visuales, dashboards, mapas interactivos y tarjetas de datos
  para garantizar estética cuidada, sistema de color OKLCH cohesivo, tipografía expresiva y accesibilidad.
---

# Frontend Design (waybarrios/opencode-power-pack)

Guía operativa para diseñar y refinar interfaces web con acabado de producto real, evitando la estética genérica.

## Principios Fundamentales

1. **Dirección Estética Clara (`Claymorphism / Mapa Amigable` en AgroNASA)**
   - Mantener una identidad visual memorable: superficies táctiles con volumen suave (`--inflado`, `--inflado-chico`, `--pulsado`), bordes orgánicos y jerarquía clara entre el mapa de fondo y los paneles flotantes.
2. **Sistema de Color Perceptual (OKLCH)**
   - Derivar toda la paleta desde `--tono-marca` usando `oklch()` para garantizar contraste uniforme entre estados semánticos (`--bien`, `--medio`, `--mal`, `--cielo`).
   - Nunca usar grises puros apagados; mantener un ligero matiz cromático coherente con la marca.
3. **Tipografía Expresiva y Legible en Campo**
   - Títulos con personalidad (`Baloo 2`, peso 800) y cuerpo de lectura limpia (`Nunito`, pesos 400/600/800).
   - Números y métricas clave (`T2M`, `PRECTOTCORR`, `GWETROOT`, puntajes 0–100) con tamaño destacado y unidad explícita.
4. **Micro-interacciones y Estados con Significado**
   - Botones con respuesta física al pasar el cursor (`translateY(-2px)`) y al presionar (`--pulsado`).
   - Indicadores de origen de datos siempre visibles (`🛰️ NASA POWER`, `📡 LoRaWAN`, `Datos de ejemplo`).
   - Respetar siempre `@media (prefers-reduced-motion: reduce)`.
5. **Accesibilidad y Responsividad Real**
   - Roles ARIA (`aria-live="polite"`, `aria-expanded`, `aria-pressed`) en controles dinámicos.
   - En móvil (`<= 48rem`), transformar el panel lateral en hoja inferior deslizable (*bottom sheet*).
