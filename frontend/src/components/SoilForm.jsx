import React, { useState } from "react";

export default function SoilForm({ onSubmitSoil, rotationPlan }) {
  const [ph, setPh] = useState(6.2);
  const [textura, setTextura] = useState("franco");
  const [drenaje, setDrenaje] = useState("bueno");
  const [materiaOrganica, setMateriaOrganica] = useState(1.8);
  const [nitrogeno, setNitrogeno] = useState("bajo");

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmitSoil({
      ph: Number(ph),
      textura,
      drenaje,
      materia_organica_pct: Number(materiaOrganica),
      nitrogeno,
    });
  };

  return (
    <div className="soil-section">
      <form onSubmit={handleSubmit}>
        <label>
          pH del suelo:
          <input type="number" step="0.1" value={ph} onChange={(e) => setPh(e.target.value)} />
        </label>
        <label>
          Textura:
          <select value={textura} onChange={(e) => setTextura(e.target.value)}>
            <option value="franco">Franco</option>
            <option value="franco-arenoso">Franco-arenoso</option>
            <option value="franco-arcilloso">Franco-arcilloso</option>
            <option value="arenoso">Arenoso</option>
            <option value="arcilloso">Arcilloso</option>
          </select>
        </label>
        <label>
          Drenaje:
          <select value={drenaje} onChange={(e) => setDrenaje(e.target.value)}>
            <option value="bueno">Bueno</option>
            <option value="moderado">Moderado</option>
            <option value="pobre">Pobre</option>
          </select>
        </label>
        <label>
          Materia Orgánica (%):
          <input
            type="number"
            step="0.1"
            value={materiaOrganica}
            onChange={(e) => setMateriaOrganica(e.target.value)}
          />
        </label>
        <label>
          Nitrógeno:
          <select value={nitrogeno} onChange={(e) => setNitrogeno(e.target.value)}>
            <option value="bajo">Bajo</option>
            <option value="medio">Medio</option>
            <option value="alto">Alto</option>
          </select>
        </label>
        <button type="submit">Recalcular y Generar Rotación</button>
      </form>

      {rotationPlan && (
        <div className="rotation-results">
          <h4>Ciclo de Rotación Sugerido</h4>
          {rotationPlan.ciclo_rotacion.map((step) => (
            <div key={step.ciclo} className="rotation-step">
              <strong>Ciclo {step.ciclo}: {step.nombre}</strong> ({step.rol_agronomico})
              <p>{step.razon}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
