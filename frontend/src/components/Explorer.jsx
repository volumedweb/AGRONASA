import React from "react";

export default function Explorer({ categories, selectedCategory, onSelectCategory, items }) {
  return (
    <div className="explorer-section">
      <div className="category-filters">
        <button onClick={() => onSelectCategory("")} className={!selectedCategory ? "active" : ""}>
          Todas
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => onSelectCategory(cat)}
            className={selectedCategory === cat ? "active" : ""}
          >
            {cat}
          </button>
        ))}
      </div>

      <table>
        <thead>
          <tr>
            <th>Cultivo</th>
            <th>Categoría</th>
            <th>Puntaje</th>
            <th>Etiqueta</th>
            <th>Factor Limitante</th>
            <th>Explicación</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.cultivo}</td>
              <td>{item.categoria}</td>
              <td>{item.puntaje}</td>
              <td>{item.etiqueta}</td>
              <td>{item.factor_limitante}</td>
              <td>{item.explicacion}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
