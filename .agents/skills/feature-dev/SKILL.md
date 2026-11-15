---
name: feature-dev
description: >-
  Flujo estructurado de desarrollo de funcionalidades extremo a extremo basado en waybarrios/opencode-power-pack
  (Exploración -> Arquitectura -> Implementación -> Revisión). Úsala al agregar nuevos endpoints,
  integraciones satelitales o módulos IoT en AgroNASA.
---

# Feature Development Workflow (waybarrios/opencode-power-pack)

Metodología en 4 fases para construir funcionalidades sólidas sin romper contratos existentes.

## Fase 1: Exploración (`code-explorer`)
- Identificar los puntos de entrada en el backend (`backend/app/main.py`, `schemas.py`) y en el frontend (`frontend/dist/index.html`, `frontend/src/api.js`).
- Trazar el flujo de datos desde la fuente externa (NASA POWER API / Open-Meteo / Sensores IoT) hasta la caché y la vista del usuario.

## Fase 2: Arquitectura (`code-architect`)
- Diseñar esquemas Pydantic estrictos en `backend/app/schemas.py` con validaciones de rango y valores por defecto seguros.
- Asegurar degradación elegante (*graceful degradation*) en 3 niveles:
  1. Backend local FastAPI + NASA POWER / Sensores en vivo.
  2. Consulta directa desde el navegador a NASA POWER API + caché en `localStorage`.
  3. Modelo determinista offline para que la demo nunca falle en una presentación.

## Fase 3: Implementación Limpia
- Mantener funciones puras para cálculos agroclimáticos (funciones trapezoidales FAO EcoCrop, percentiles históricos, fusión satélite-sensor).
- Documentar unidades físicas en los nombres de campos (`_c`, `_mm`, `_pct`, `_kmh`, `_dbm`).

## Fase 4: Verificación (`code-reviewer`)
- Añadir pruebas automatizadas en `backend/tests/test_agronasa.py` cubriendo casos normales y bordes.
- Ejecutar `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_agronasa.py -v`.
