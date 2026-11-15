"""Guía integral de rotación de cultivos y manejo de suelos en Bolivia (docs/gu_a_de_rotaci_n_agr_cola_de_bolivia.md).

El archivo Markdown es la fuente; `python -m app.guia_rotacion` regenera `data/guia_rotacion.json`, que es lo que
usa la aplicación (así la guía viaja con el backend aunque la carpeta docs no se copie).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

RUTA_JSON = Path(__file__).resolve().parent.parent / "data" / "guia_rotacion.json"
RUTA_MD = Path(__file__).resolve().parent.parent.parent / "docs" / "gu_a_de_rotaci_n_agr_cola_de_bolivia.md"

COLORES = {"🔴": "rojo", "🟠": "naranja", "🟡": "amarillo", "🟢": "verde", "🔵": "azul", "🟣": "morado"}
ZONAS = {"Llanos": "llanos", "Valles": "valles", "Andina": "altiplano"}
NOMBRES_ZONA = {"llanos": "Llanos y trópico", "valles": "Valles", "altiplano": "Altiplano y zona andina"}

# Palabras clave (sin tildes, en minúscula) → cultivo de crops.json. Sirve para unir la guía con el motor de puntajes.
CLAVES_CULTIVO = {
    "soya": "soya", "arroz": "arroz", "maiz": "maiz", "yuca": "yuca", "papa": "papa", "tomate": "tomate",
    "cebolla": "cebolla", "zanahoria": "zanahoria", "platano": "platano", "citricos": "citricos",
    "mani": "mani", "quinua": "quinua", "haba": "haba", "girasol": "girasol",
    "frejol": "frijol", "frijol": "frijol",
}


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*+", "", texto)).strip()


def _etiquetas(celda: str) -> List[Dict[str, str]]:
    return [
        {"color": COLORES[icono], "icono": icono, "texto": texto.strip()}
        for icono, texto in re.findall(r"([🔴🟠🟡🟢🔵🟣])\s*\*\*\[(.+?)\]\*\*", celda)
    ]


def cultivos_en(texto: str) -> List[str]:
    """Ids de crops.json que se nombran en un texto (en orden, sin repetir)."""
    palabras = re.findall(r"[a-z]+", sin_tildes(texto))
    vistos: List[str] = []
    for p in palabras:
        id_ = CLAVES_CULTIVO.get(p)
        if id_ and id_ not in vistos:
            vistos.append(id_)
    return vistos


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(texto)).strip("-")


def parsear_guia(markdown: str) -> Dict[str, Any]:
    filas: List[Dict[str, Any]] = []
    zona: Optional[str] = None
    for linea in markdown.splitlines():
        m = re.match(r"## \d\. Zona (?:de los |de )?(\w+)", linea)
        if m:
            zona = ZONAS.get(m.group(1), zona)
        if not (zona and linea.startswith("| **")):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) < 5:
            continue
        producto = _limpiar(celdas[0])
        filas.append({
            "zona": zona,
            "producto": producto,
            "slug": _slug(producto),
            "cultivos": cultivos_en(producto),
            "temporada": _limpiar(celdas[1]),
            "impacto": _etiquetas(celdas[2]),
            "despues": _limpiar(celdas[3]),
            "despues_cultivos": cultivos_en(celdas[3]),
            "beneficios": _etiquetas(celdas[4]),
        })
    reglas = [
        _limpiar(m.group(1)) for m in re.finditer(r"^\d\. (.+)$", markdown.split("## Regla Práctica de Decisión")[-1], re.M)
    ] if "## Regla Práctica de Decisión" in markdown else []
    return {"zonas": NOMBRES_ZONA, "filas": filas, "reglas": reglas}


def cargar_guia() -> Dict[str, Any]:
    return json.loads(RUTA_JSON.read_text(encoding="utf-8"))


def filas_de_cultivo(guia: Dict[str, Any], cultivo_id: str) -> List[Dict[str, Any]]:
    """Filas de la guía donde aparece este cultivo como producto sembrado (todas las zonas)."""
    return [f for f in guia["filas"] if cultivo_id in f["cultivos"]]


def fila_por_slug(guia: Dict[str, Any], slug: str) -> List[Dict[str, Any]]:
    return [f for f in guia["filas"] if f["slug"] == slug]


def productos_sin_cultivo(guia: Dict[str, Any]) -> List[Dict[str, str]]:
    """Productos de la guía que no están en crops.json: se pueden elegir como 'cultivo anterior' y solo muestran la guía."""
    vistos, lista = set(), []
    for f in guia["filas"]:
        if not f["cultivos"] and f["slug"] not in vistos:
            vistos.add(f["slug"])
            lista.append({"id": f"guia:{f['slug']}", "nombre": f["producto"]})
    return lista


if __name__ == "__main__":
    texto = RUTA_MD.read_text(encoding="utf-8")
    datos = parsear_guia(texto)
    RUTA_JSON.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(datos['filas'])} filas y {len(datos['reglas'])} reglas -> {RUTA_JSON}", file=sys.stderr)
