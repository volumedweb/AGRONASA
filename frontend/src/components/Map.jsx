import React from "react";
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";

function ClickHandler({ onSelectPoint }) {
  useMapEvents({
    click(e) {
      onSelectPoint(
        Number(e.latlng.lat.toFixed(4)),
        Number(e.latlng.lng.toFixed(4))
      );
    },
  });
  return null;
}

export default function MapView({ lat, lon, onSelectPoint }) {
  return (
    <div className="map-wrapper">
      <MapContainer center={[lat, lon]} zoom={6} style={{ height: "340px", width: "100%" }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors | NASA POWER"
        />
        <Marker position={[lat, lon]} />
        <ClickHandler onSelectPoint={onSelectPoint} />
      </MapContainer>
    </div>
  );
}
