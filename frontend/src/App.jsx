import React, { useEffect, useState } from "react";
import MapView from "./components/Map";
import Results from "./components/Results";
import SoilForm from "./components/SoilForm";
import Explorer from "./components/Explorer";
import { fetchClimate, fetchRecommendations, fetchRotation, fetchExplore } from "./api";

export default function App() {
  const [lat, setLat] = useState(-17.39);
  const [lon, setLon] = useState(-66.28);
  const [mesSiembra, setMesSiembra] = useState(10);
  const [suelo, setSuelo] = useState(null);
  const [recData, setRecData] = useState(null);
  const [climData, setClimData] = useState(null);
  const [rotationData, setRotationData] = useState(null);
  const [explorerCategory, setExplorerCategory] = useState("");
  const [explorerItems, setExplorerItems] = useState([]);

  useEffect(() => {
    async function load() {
      const [rec, clim, exp] = await Promise.all([
        fetchRecommendations({ lat, lon, mes_siembra: mesSiembra, suelo }),
        fetchClimate(lat, lon),
        fetchExplore({ lat, lon, mes_siembra: mesSiembra, categoria: explorerCategory || null, suelo }),
      ]);
      setRecData(rec);
      setClimData(clim);
      setExplorerItems(exp.resultados);
    }
    load();
  }, [lat, lon, mesSiembra, suelo, explorerCategory]);

  const handleSoilSubmit = async (soilInput) => {
    setSuelo(soilInput);
    const rot = await fetchRotation({
      lat,
      lon,
      mes_inicio: mesSiembra || 10,
      suelo: soilInput,
    });
    setRotationData(rot);
  };

  return (
    <div className="app-container">
      <header>
        <h1>AgroNASA — Recomendador Agroclimático de Siembra</h1>
      </header>
      <MapView
        lat={lat}
        lon={lon}
        onSelectPoint={(newLat, newLon) => {
          setLat(newLat);
          setLon(newLon);
        }}
      />
      {recData && climData && (
        <Results
          alerts={recData.alertas}
          recommendations={recData.recomendaciones}
          climateMonths={climData.climatologia.meses}
        />
      )}
      <SoilForm onSubmitSoil={handleSoilSubmit} rotationPlan={rotationData} />
      <Explorer
        categories={["cereales", "tuberculos_raices", "legumbres", "hortalizas", "oleaginosas", "frutas"]}
        selectedCategory={explorerCategory}
        onSelectCategory={setExplorerCategory}
        items={explorerItems}
      />
    </div>
  );
}
