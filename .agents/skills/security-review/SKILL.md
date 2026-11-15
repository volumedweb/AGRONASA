---
name: security-review
description: >-
  Auditoría de seguridad y endurecimiento de aplicaciones web y APIs basada en waybarrios/opencode-power-pack.
  Úsala para revisar entradas de usuario, prevenir XSS/SSRF, validar esquemas Pydantic, configurar cabeceras HTTP
  seguras y proteger integraciones con APIs externas e IoT.
---

# Security Review & Hardening (waybarrios/opencode-power-pack)

Lista de verificación práctica para auditar cambios en el backend FastAPI, el frontend y la ingesta IoT.

## 1. Validación Estricta de Entradas (API & IoT)
- **Coordenadas geográficas**: Validar siempre `lat` en `[-90, 90]` y `lon` en `[-180, 180]`.
- **Parámetros agronómicos y sensores**: Restringir `ph` (`3.0–10.0`), porcentajes (`0–100`), temperaturas (`-60–70 °C`) y listas de filtros con longitudes máximas (`max_length`).
- **Identificadores de nodos IoT**: Limitar longitud y caracteres permitidos en `parcela_id` y `nodo_id`.

## 2. Prevención de XSS en el Frontend
- Todo dato dinámico renderizado con `innerHTML` debe pasar obligatoriamente por la función de escape `esc()`.
- Nunca interpolar cadenas externas sin escapar en atributos HTML o bloques SVG.

## 3. Protección de Clientes HTTP Externos (NASA POWER / Open-Meteo)
- Usar siempre `timeout` explícito (`AbortController` en navegador y `httpx.Client(timeout=...)` en Python) para evitar bloqueos por agotamiento de conexiones.
- Nunca construir URLs externas concatenando parámetros sin codificar o validar numéricamente.

## 4. Cabeceras de Seguridad HTTP
- Incluir en las respuestas del servidor:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Referrer-Policy: strict-origin-when-cross-origin`
