const ENV_BASE = (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_API_URL) || "";

async function requestWithFallback(path, options = {}) {
  const bases = [ENV_BASE, "http://127.0.0.1:8000", "http://localhost:8000"];
  let lastErr = null;
  for (const base of bases) {
    try {
      const res = await fetch(`${base}${path}`, options);
      if (res.ok) return await res.json();
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error(`Error consultando ${path}`);
}

export async function fetchClimate(lat, lon) {
  return requestWithFallback(`/api/climate?lat=${lat}&lon=${lon}`);
}

export async function fetchAlerts(lat, lon) {
  return requestWithFallback(`/api/alerts?lat=${lat}&lon=${lon}`);
}

export async function fetchRecommendations(payload) {
  return requestWithFallback(`/api/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchExplore(payload) {
  return requestWithFallback(`/api/explore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchRotation(payload) {
  return requestWithFallback(`/api/rotation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchIoTTelemetry(lat, lon, mes = null) {
  const qMes = mes ? `&mes=${mes}` : "";
  return requestWithFallback(`/api/iot/telemetry?lat=${lat}&lon=${lon}${qMes}`);
}

export async function postIoTTelemetry(payload) {
  return requestWithFallback(`/api/iot/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
