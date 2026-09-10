"""
chunk_documents.py

Script de generación de chunks para el sistema RAG de CleoIA.

Recorre todos los documentos Markdown de `library/clean/`, los divide en
fragmentos (chunks) optimizados para búsqueda semántica y generación de
embeddings, y guarda un JSON por documento dentro de `library/chunks/`,
respetando la misma estructura de categorías.

No modifica los archivos Markdown originales: solo los lee.

Reglas de chunking:
    - Tamaño objetivo: 450 palabras por chunk.
    - Overlap: 80 palabras entre chunks consecutivos.
    - Los chunks respetan límites de oración (nunca se corta una oración
      a la mitad) y, siempre que es posible, respetan los párrafos.
    - Cada chunk conserva el encabezado (título/subtítulo) de la sección
      a la que pertenece, para no perder el contexto al fragmentar.
"""

import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_CLEAN = RAIZ_PROYECTO / "library" / "clean"
DIR_CHUNKS = RAIZ_PROYECTO / "library" / "chunks"
DIR_METADATA = RAIZ_PROYECTO / "library" / "metadata"

TAMANO_OBJETIVO_PALABRAS = 450
OVERLAP_PALABRAS = 80

# Patrón para dividir texto en oraciones sin cortar palabras a la mitad.
PATRON_FIN_ORACION = re.compile(r"(?<=[\.\!\?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9])")


# ----------------------------------------------------------------------------
# 1. Utilidades de texto
# ----------------------------------------------------------------------------

def _slugify(texto: str) -> str:
    """Convierte un texto en un identificador simple (ASCII, minúsculas,
    separado por guiones bajos), usado para generar `document_id`."""
    texto_normalizado = unicodedata.normalize("NFKD", texto)
    texto_sin_acentos = "".join(
        caracter for caracter in texto_normalizado if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^a-zA-Z0-9]+", "_", texto_sin_acentos).strip("_").lower()


def dividir_en_oraciones(texto: str) -> list[str]:
    """Divide un bloque de texto en oraciones, sin cortar ninguna a la mitad."""
    texto = texto.strip()
    if not texto:
        return []
    return [oracion.strip() for oracion in PATRON_FIN_ORACION.split(texto) if oracion.strip()]


# ----------------------------------------------------------------------------
# 2. Parseo del Markdown en secciones (encabezado + cuerpo)
# ----------------------------------------------------------------------------

def parsear_secciones(texto_markdown: str) -> list[dict]:
    """
    Recorre el Markdown línea por línea y agrupa el contenido en secciones,
    donde cada sección es un encabezado (# o ##) junto con el texto que le
    sigue, hasta el próximo encabezado.

    Returns:
        list[dict]: cada elemento tiene "encabezado" (str | None),
        "nivel" (1, 2 o 0) y "cuerpo" (texto, ya sin saltos de línea de
        página, unido en un único bloque por sección).
    """
    secciones = []
    encabezado = None
    nivel = 0
    lineas_cuerpo: list[str] = []

    def cerrar_seccion_actual():
        cuerpo = " ".join(lineas_cuerpo).strip()
        if encabezado or cuerpo:
            secciones.append({"encabezado": encabezado, "nivel": nivel, "cuerpo": cuerpo})

    for linea_original in texto_markdown.splitlines():
        linea = linea_original.strip()
        if not linea:
            continue  # las líneas en blanco solo marcan separaciones de página

        if linea.startswith("## "):
            cerrar_seccion_actual()
            encabezado, nivel, lineas_cuerpo = linea[3:].strip(), 2, []
        elif linea.startswith("# "):
            cerrar_seccion_actual()
            encabezado, nivel, lineas_cuerpo = linea[2:].strip(), 1, []
        else:
            lineas_cuerpo.append(linea)

    cerrar_seccion_actual()
    return secciones


def extraer_titulo_documento(secciones: list[dict], ruta_md: Path) -> str:
    """Obtiene el título del documento a partir de su primer encabezado
    de nivel 1 (#). Si no existe, usa el nombre del archivo como respaldo."""
    for seccion in secciones:
        if seccion["nivel"] == 1 and seccion["encabezado"]:
            return seccion["encabezado"]
    return ruta_md.stem.replace("_", " ")


# ----------------------------------------------------------------------------
# 3. Construcción de "unidades" (la unidad mínima que no se puede partir)
# ----------------------------------------------------------------------------

def construir_unidades(secciones: list[dict]) -> list[dict]:
    """
    Convierte las secciones del documento en una lista plana de unidades
    indivisibles (encabezados y oraciones), cada una con la referencia a
    la sección (contexto) a la que pertenece. Esta lista es la que luego
    se empaqueta en chunks.
    """
    unidades = []

    for seccion in secciones:
        if seccion["encabezado"]:
            marca = ("#" * seccion["nivel"]) + " " + seccion["encabezado"]
            unidades.append(
                {
                    "texto": marca,
                    "es_encabezado": True,
                    "contexto": seccion["encabezado"],
                    "palabras": len(seccion["encabezado"].split()),
                }
            )

        for oracion in dividir_en_oraciones(seccion["cuerpo"]):
            unidades.append(
                {
                    "texto": oracion,
                    "es_encabezado": False,
                    "contexto": seccion["encabezado"],
                    "palabras": len(oracion.split()),
                }
            )

    return unidades


# ----------------------------------------------------------------------------
# 4. Empaquetado de unidades en chunks (con overlap)
# ----------------------------------------------------------------------------

def generar_grupos_de_chunks(
    unidades: list[dict],
    tamano_objetivo: int = TAMANO_OBJETIVO_PALABRAS,
    overlap: int = OVERLAP_PALABRAS,
) -> list[list[dict]]:
    """
    Empaqueta la lista de unidades (encabezados y oraciones) en grupos de
    aproximadamente `tamano_objetivo` palabras, repitiendo al inicio de
    cada grupo (excepto el primero) las últimas unidades del grupo
    anterior hasta acumular `overlap` palabras.

    Como las unidades son oraciones completas, nunca se corta una oración
    a la mitad; los párrafos solo se dividen entre chunks cuando su
    tamaño supera el objetivo.
    """
    cola = list(unidades)
    grupos: list[list[dict]] = []

    while cola:
        grupo: list[dict] = []
        palabras_grupo = 0

        while cola:
            siguiente = cola[0]
            if grupo and palabras_grupo + siguiente["palabras"] > tamano_objetivo:
                break
            grupo.append(cola.pop(0))
            palabras_grupo += siguiente["palabras"]

        grupos.append(grupo)

        if not cola:
            break

        # Preparar el overlap: las últimas unidades del grupo se repiten
        # al comienzo del siguiente, hasta sumar ~`overlap` palabras.
        overlap_unidades: list[dict] = []
        palabras_overlap = 0
        for unidad in reversed(grupo):
            overlap_unidades.insert(0, unidad)
            palabras_overlap += unidad["palabras"]
            if palabras_overlap >= overlap:
                break

        cola = overlap_unidades + cola

    return grupos


def renderizar_chunk(grupo: list[dict]) -> str:
    """
    Convierte un grupo de unidades en el texto final del chunk: los
    encabezados quedan en su propia línea y las oraciones del cuerpo se
    agrupan en párrafos. Si el chunk no comienza con un encabezado, se
    antepone la sección de origen para no perder el contexto.
    """
    lineas = []
    buffer_oraciones: list[str] = []

    def volcar_buffer():
        if buffer_oraciones:
            lineas.append(" ".join(buffer_oraciones))
            buffer_oraciones.clear()

    for unidad in grupo:
        if unidad["es_encabezado"]:
            volcar_buffer()
            lineas.append(unidad["texto"])
        else:
            buffer_oraciones.append(unidad["texto"])
    volcar_buffer()

    texto_chunk = "\n\n".join(lineas)

    primera_unidad = grupo[0] if grupo else None
    if primera_unidad and not primera_unidad["es_encabezado"] and primera_unidad["contexto"]:
        texto_chunk = f"_(Sección: {primera_unidad['contexto']})_\n\n{texto_chunk}"

    return texto_chunk


# ----------------------------------------------------------------------------
# 5. Procesamiento de un documento completo
# ----------------------------------------------------------------------------

def procesar_documento(ruta_md: Path, categoria: str) -> list[dict]:
    """Ejecuta el pipeline completo (parsear -> unidades -> chunks) para
    un único documento Markdown y arma sus registros de chunk."""
    texto_markdown = ruta_md.read_text(encoding="utf-8")

    secciones = parsear_secciones(texto_markdown)
    titulo_documento = extraer_titulo_documento(secciones, ruta_md)
    unidades = construir_unidades(secciones)
    grupos = generar_grupos_de_chunks(unidades)

    document_id = _slugify(f"{categoria}_{ruta_md.stem}")

    chunks_documento = []
    for numero, grupo in enumerate(grupos, start=1):
        texto_chunk = renderizar_chunk(grupo)
        chunks_documento.append(
            {
                "chunk_id": f"{document_id}_chunk_{numero:03d}",
                "document_id": document_id,
                "categoria": categoria,
                "titulo_documento": titulo_documento,
                "chunk_number": numero,
                "texto": texto_chunk,
                "palabras": len(texto_chunk.split()),
                "caracteres": len(texto_chunk),
            }
        )

    return chunks_documento


def guardar_chunks_json(chunks_documento: list[dict], categoria: str, nombre_base: str) -> Path:
    """Guarda los chunks de un documento en `library/chunks/<categoria>/`."""
    carpeta_destino = DIR_CHUNKS / categoria
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    ruta_json = carpeta_destino / f"{nombre_base}_chunks.json"
    ruta_json.write_text(
        json.dumps(chunks_documento, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_json


def recorrer_documentos_markdown():
    """Recorre `library/clean/` y devuelve la lista de (categoria, ruta_md)."""
    documentos = []
    if not DIR_CLEAN.exists():
        return documentos

    for carpeta_categoria in sorted(DIR_CLEAN.iterdir()):
        if not carpeta_categoria.is_dir():
            continue
        for ruta_md in sorted(carpeta_categoria.glob("*.md")):
            documentos.append((carpeta_categoria.name, ruta_md))

    return documentos


# ----------------------------------------------------------------------------
# 6. Índice general y reportes
# ----------------------------------------------------------------------------

def guardar_indice_general(resultados: list[dict]) -> Path:
    """Genera `library/metadata/chunks_metadata.json` con las estadísticas
    globales de la generación de chunks."""
    DIR_METADATA.mkdir(parents=True, exist_ok=True)

    total_chunks = sum(r["cantidad_chunks"] for r in resultados)
    total_palabras = sum(r["palabras_totales"] for r in resultados)
    chunks_por_categoria = defaultdict(int)
    for r in resultados:
        chunks_por_categoria[r["categoria"]] += r["cantidad_chunks"]

    documento_mas_chunks = max(resultados, key=lambda r: r["cantidad_chunks"], default=None)
    documento_menos_chunks = min(resultados, key=lambda r: r["cantidad_chunks"], default=None)

    indice = {
        "total_documentos_procesados": len(resultados),
        "total_chunks_generados": total_chunks,
        "chunks_por_categoria": dict(chunks_por_categoria),
        "promedio_palabras_por_chunk": round(total_palabras / total_chunks, 1) if total_chunks else 0,
        "documento_con_mas_chunks": (
            {
                "documento": documento_mas_chunks["nombre"],
                "categoria": documento_mas_chunks["categoria"],
                "chunks": documento_mas_chunks["cantidad_chunks"],
            }
            if documento_mas_chunks
            else None
        ),
        "documento_con_menos_chunks": (
            {
                "documento": documento_menos_chunks["nombre"],
                "categoria": documento_menos_chunks["categoria"],
                "chunks": documento_menos_chunks["cantidad_chunks"],
            }
            if documento_menos_chunks
            else None
        ),
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
    }

    ruta_indice = DIR_METADATA / "chunks_metadata.json"
    ruta_indice.write_text(
        json.dumps(indice, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_indice


def imprimir_resumen_consola(
    resultados: list[dict],
    documentos_por_categoria: Counter,
    errores: list[dict],
    tiempo_total: float,
):
    """Imprime la tabla por categoría y el resumen final del proceso."""
    chunks_por_categoria = defaultdict(int)
    palabras_por_categoria = defaultdict(int)
    for r in resultados:
        chunks_por_categoria[r["categoria"]] += r["cantidad_chunks"]
        palabras_por_categoria[r["categoria"]] += r["palabras_totales"]

    categorias = sorted(documentos_por_categoria.keys())
    ancho_categoria = max([len("Categoría")] + [len(c) for c in categorias]) + 2

    print("\nResumen de generación de chunks")
    print("-" * (ancho_categoria + 46))
    print(
        f"{'Categoría'.ljust(ancho_categoria)}"
        f"{'Documentos'.rjust(12)}{'Chunks'.rjust(10)}{'Prom. palabras'.rjust(18)}"
    )
    print("-" * (ancho_categoria + 46))

    for categoria in categorias:
        total_docs = documentos_por_categoria[categoria]
        total_chunks = chunks_por_categoria.get(categoria, 0)
        promedio = (
            round(palabras_por_categoria[categoria] / total_chunks, 1)
            if total_chunks
            else 0
        )
        print(
            f"{categoria.ljust(ancho_categoria)}"
            f"{str(total_docs).rjust(12)}{str(total_chunks).rjust(10)}{str(promedio).rjust(18)}"
        )

    print("-" * (ancho_categoria + 46))

    total_chunks_creados = sum(chunks_por_categoria.values())
    print(f"\nTotal de chunks creados: {total_chunks_creados}")
    print(f"Tiempo de ejecución: {tiempo_total:.2f} segundos")
    if errores:
        print(f"Errores encontrados: {len(errores)}")
        for error in errores:
            print(f"  - {error['archivo']}: {error['mensaje']}")
    else:
        print("Errores encontrados: 0")


# ----------------------------------------------------------------------------
# 7. Orquestación
# ----------------------------------------------------------------------------

def main():
    inicio = time.perf_counter()

    documentos = recorrer_documentos_markdown()
    documentos_por_categoria = Counter(categoria for categoria, _ in documentos)

    resultados = []
    errores = []

    for categoria, ruta_md in documentos:
        try:
            chunks_documento = procesar_documento(ruta_md, categoria)
            guardar_chunks_json(chunks_documento, categoria, ruta_md.stem)

            resultados.append(
                {
                    "nombre": ruta_md.name,
                    "categoria": categoria,
                    "cantidad_chunks": len(chunks_documento),
                    "palabras_totales": sum(c["palabras"] for c in chunks_documento),
                }
            )
        except Exception as excepcion:  # noqa: BLE001 - se registra y se continúa
            errores.append({"archivo": ruta_md.name, "mensaje": str(excepcion)})

    tiempo_total = time.perf_counter() - inicio

    guardar_indice_general(resultados)
    imprimir_resumen_consola(resultados, documentos_por_categoria, errores, tiempo_total)


if __name__ == "__main__":
    main()
