import React from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";

export default function Results({ alerts, recommendations, climateMonths }) {
  return (
    <div className="results-section">
      <h3>Alertas Agroclimáticas Recientes</h3>
      <div className="alerts-grid">
        {alerts.map((a, idx) => (
          <div key={idx} className={`alert-card sev-${a.severidad}`}>
            <strong>{a.estado}</strong>
            <p>{a.mensaje}</p>
          </div>
        ))}
      </div>

      <h3>Ranking de Cultivos Recomendados</h3>
      <div className="crops-grid">
        {recommendations.map((r) => (
          <div key={r.id} className="crop-card">
            <div className="crop-header">
              <h4>{r.cultivo}</h4>
              <span className="score">{r.puntaje}/100 ({r.etiqueta})</span>
            </div>
            <p>{r.explicacion}</p>
          </div>
        ))}
      </div>

      {climateMonths && climateMonths.length > 0 && (
        <div style={{ height: 300, marginTop: "1.5rem" }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={climateMonths}>
              <XAxis dataKey="codigo" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip />
              <Legend />
              <Bar yAxisId="right" dataKey="precip_mm_mes" name="Lluvia (mm/mes)" fill="#38bdf8" />
              <Line yAxisId="left" type="monotone" dataKey="t2m" name="Temp. Media (°C)" stroke="#f97316" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
