"""
clean_library.py

Script de limpieza de la biblioteca de conocimiento de CleoIA.

Recorre todos los PDFs de `library/raw/`, extrae su texto con PyMuPDF
(`fitz`), lo limpia (elimina encabezados/pies de página repetidos, páginas
vacías y espacios/saltos de línea innecesarios) y genera una versión en
Markdown en `library/clean/`, respetando la misma estructura de categorías.

Además genera:
    - library/metadata/documents_metadata.json  (metadata por documento)
    - docs/03_Limpieza_Biblioteca.md             (log del procesamiento)
    - un resumen impreso en consola al finalizar

No modifica ni elimina los PDFs originales.
"""

import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (el paquete se importaba antes como "fitz")

# ----------------------------------------------------------------------------
# Rutas base del proyecto
# ----------------------------------------------------------------------------
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ_PROYECTO / "library" / "raw"
DIR_CLEAN = RAIZ_PROYECTO / "library" / "clean"
DIR_METADATA = RAIZ_PROYECTO / "library" / "metadata"
DIR_DOCS = RAIZ_PROYECTO / "docs"

# Palabras comunes del español, usadas para la detección heurística de idioma.
PALABRAS_ESPANOL = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las",
    "por", "un", "para", "con", "no", "una", "su", "al", "es", "lo",
    "como", "más", "o", "pero", "sus", "le", "ya", "o", "este", "sí",
    "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "también",
}


def recorrer_pdfs():
    """
    Recorre las carpetas de 'library/raw/' (una por cada categoría) y
    obtiene la lista de archivos PDF disponibles para procesar.

    Returns:
        list[tuple[str, Path]]: lista de tuplas (categoria, ruta_pdf),
        ordenada por categoría y luego por nombre de archivo.
    """
    documentos = []

    if not DIR_RAW.exists():
        return documentos

    for carpeta_categoria in sorted(DIR_RAW.iterdir()):
        if not carpeta_categoria.is_dir():
            continue

        categoria = carpeta_categoria.name
        pdfs = sorted(carpeta_categoria.glob("*.pdf"))

        for ruta_pdf in pdfs:
            documentos.append((categoria, ruta_pdf))

    return documentos


def extraer_texto_pdf(ruta_pdf: Path):
    """
    Extrae el contenido de un archivo PDF individual usando PyMuPDF.

    Para cada línea de texto se conserva también el tamaño de fuente más
    grande de esa línea, lo que luego permite distinguir títulos y
    subtítulos del texto normal en `limpiar_texto()`.

    Args:
        ruta_pdf: ruta al archivo PDF a procesar.

    Returns:
        tuple[list[list[tuple[str, float]]], int]:
            - lineas_por_pagina: lista (una entrada por página) de listas
              de tuplas (texto_de_linea, tamano_de_fuente_maximo).
            - num_paginas: cantidad total de páginas del PDF.
    """
    lineas_por_pagina = []

    with fitz.open(ruta_pdf) as documento:
        num_paginas = documento.page_count

        for pagina in documento:
            lineas_pagina = []
            datos = pagina.get_text("dict")

            for bloque in datos.get("blocks", []):
                for linea in bloque.get("lines", []):
                    spans = linea.get("spans", [])
                    if not spans:
                        continue

                    texto_linea = "".join(s.get("text", "") for s in spans).strip()
                    if not texto_linea:
                        continue

                    tamano_maximo = max(s.get("size", 0) for s in spans)
                    lineas_pagina.append((texto_linea, tamano_maximo))

            lineas_por_pagina.append(lineas_pagina)

    return lineas_por_pagina, num_paginas


def detectar_idioma(texto: str) -> str:
    """
    Detecta de forma heurística si un texto está escrito en español,
    a partir de la frecuencia de palabras (stopwords) muy comunes en
    ese idioma. No requiere librerías externas de detección de idioma.

    Args:
        texto: texto plano sobre el cual estimar el idioma.

    Returns:
        str: "español" si la proporción de palabras comunes en español
        supera el umbral esperado, o "desconocido" en caso contrario.
    """
    palabras = re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]+", texto.lower())
    if not palabras:
        return "desconocido"

    coincidencias = sum(1 for palabra in palabras if palabra in PALABRAS_ESPANOL)
    proporcion = coincidencias / len(palabras)

    return "español" if proporcion >= 0.08 else "desconocido"


def _detectar_lineas_repetidas(lineas_por_pagina):
    """
    Identifica líneas que se repiten en gran parte de las páginas de un
    documento (encabezados y pies de página típicos) para poder
    descartarlas del texto limpio.
    """
    total_paginas = len(lineas_por_pagina)
    if total_paginas < 3:
        return set()

    contador = Counter()
    for lineas_pagina in lineas_por_pagina:
        textos_unicos = {texto for texto, _ in lineas_pagina if len(texto) <= 80}
        contador.update(textos_unicos)

    umbral = max(3, int(total_paginas * 0.5))
    return {texto for texto, veces in contador.items() if veces >= umbral}


def _quitar_simbolos_decorativos(texto: str) -> str:
    """
    Elimina símbolos decorativos (ej. "¶") que algunas plantillas de PDF
    agregan como ícono de ancla al final de los títulos, y que PyMuPDF
    extrae como texto aunque no forman parte del contenido real.
    """
    return re.sub(r"\s*¶\s*$", "", texto).strip()


def _agrupar_lineas_consecutivas(lineas_clasificadas):
    """
    Agrupa líneas consecutivas que comparten el mismo nivel (título,
    subtítulo o texto normal). Esto evita que un título envuelto en varias
    líneas (por ejemplo, uno muy largo) se convierta en varios encabezados
    Markdown separados.

    Args:
        lineas_clasificadas: lista de tuplas (nivel, texto).

    Returns:
        list[tuple[int, list[str]]]: grupos (nivel, textos_del_grupo).
    """
    grupos = []
    for nivel, texto in lineas_clasificadas:
        if grupos and grupos[-1][0] == nivel and nivel != 0:
            grupos[-1][1].append(texto)
        else:
            grupos.append((nivel, [texto]))
    return grupos


def limpiar_texto(lineas_por_pagina):
    """
    Limpia el texto extraído del PDF: elimina encabezados, pies de página,
    saltos de línea innecesarios y otros elementos de ruido, conservando
    títulos y subtítulos como encabezados Markdown.

    Args:
        lineas_por_pagina: salida de `extraer_texto_pdf()`.

    Returns:
        tuple[str, int]:
            - texto_markdown: contenido limpio en formato Markdown.
            - paginas_con_contenido: cantidad de páginas que no quedaron
              vacías tras la limpieza.
    """
    lineas_repetidas = _detectar_lineas_repetidas(lineas_por_pagina)

    # Tamaño de fuente "normal" del cuerpo del texto = el más frecuente.
    tamanos = [
        round(tamano)
        for lineas_pagina in lineas_por_pagina
        for _, tamano in lineas_pagina
    ]
    tamano_cuerpo = Counter(tamanos).most_common(1)[0][0] if tamanos else 0

    bloques_paginas = []
    paginas_con_contenido = 0

    for lineas_pagina in lineas_por_pagina:
        lineas_utiles = [
            (_quitar_simbolos_decorativos(texto), tamano)
            for texto, tamano in lineas_pagina
            if texto not in lineas_repetidas
        ]
        lineas_utiles = [(texto, tamano) for texto, tamano in lineas_utiles if texto]

        if not lineas_utiles:
            # Página vacía (o solo contenía encabezados/pies de página).
            continue

        paginas_con_contenido += 1

        # Clasificar cada línea: 1 = título, 2 = subtítulo, 0 = texto normal.
        lineas_clasificadas = []
        for texto, tamano in lineas_utiles:
            if round(tamano) >= tamano_cuerpo * 1.4 and len(texto.split()) <= 12:
                nivel = 1
            elif (
                tamano_cuerpo * 1.15 <= round(tamano) < tamano_cuerpo * 1.4
                and len(texto.split()) <= 12
            ):
                nivel = 2
            else:
                nivel = 0
            lineas_clasificadas.append((nivel, texto))

        # Los títulos/subtítulos que ocupan varias líneas (texto envuelto)
        # se agrupan en un único encabezado en lugar de uno por línea.
        lineas_markdown = []
        for nivel, textos_agrupados in _agrupar_lineas_consecutivas(lineas_clasificadas):
            texto_unido = " ".join(textos_agrupados)
            if nivel == 1:
                lineas_markdown.append(f"# {texto_unido}")
            elif nivel == 2:
                lineas_markdown.append(f"## {texto_unido}")
            else:
                lineas_markdown.extend(textos_agrupados)

        bloques_paginas.append("\n".join(lineas_markdown))

    texto_completo = "\n\n".join(bloques_paginas)

    # Colapsar espacios múltiples y saltos de línea innecesarios.
    texto_completo = re.sub(r"[ \t]+", " ", texto_completo)
    texto_completo = re.sub(r"\n{3,}", "\n\n", texto_completo)
    texto_completo = texto_completo.strip() + "\n"

    return texto_completo, paginas_con_contenido


def guardar_markdown(texto_markdown: str, categoria: str, nombre_archivo: str) -> Path:
    """
    Guarda el texto limpio en formato Markdown dentro de 'library/clean/',
    respetando la categoría de origen del documento.

    Args:
        texto_markdown: contenido ya limpio, en formato Markdown.
        categoria: nombre de la carpeta de categoría (ej. "01_Colorimetria").
        nombre_archivo: nombre del PDF original (con extensión .pdf).

    Returns:
        Path: ruta del archivo Markdown generado.
    """
    carpeta_destino = DIR_CLEAN / categoria
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    nombre_md = Path(nombre_archivo).stem + ".md"
    ruta_md = carpeta_destino / nombre_md

    ruta_md.write_text(texto_markdown, encoding="utf-8")
    return ruta_md


def _procesar_documento(categoria: str, ruta_pdf: Path):
    """
    Ejecuta el pipeline completo (extraer -> limpiar -> guardar) para un
    único documento y arma su entrada de metadata.
    """
    lineas_por_pagina, num_paginas = extraer_texto_pdf(ruta_pdf)
    texto_markdown, _ = limpiar_texto(lineas_por_pagina)
    ruta_md = guardar_markdown(texto_markdown, categoria, ruta_pdf.name)

    idioma = detectar_idioma(texto_markdown)

    metadata = {
        "nombre": ruta_pdf.name,
        "categoria": categoria,
        "ruta_pdf": str(ruta_pdf.relative_to(RAIZ_PROYECTO)),
        "ruta_markdown": str(ruta_md.relative_to(RAIZ_PROYECTO)),
        "cantidad_paginas": num_paginas,
        "cantidad_caracteres": len(texto_markdown),
        "idioma_detectado": idioma,
        "fecha_procesamiento": datetime.now().isoformat(timespec="seconds"),
    }
    return metadata


def guardar_metadata(lista_metadata: list) -> Path:
    """Guarda la metadata de todos los documentos procesados en un JSON."""
    DIR_METADATA.mkdir(parents=True, exist_ok=True)
    ruta_json = DIR_METADATA / "documents_metadata.json"
    ruta_json.write_text(
        json.dumps(lista_metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ruta_json


def generar_log(
    total_encontrados: int,
    procesados_ok: list,
    errores: list,
    tiempo_total: float,
) -> Path:
    """Genera el log en Markdown del proceso de limpieza de la biblioteca."""
    DIR_DOCS.mkdir(parents=True, exist_ok=True)
    ruta_log = DIR_DOCS / "03_Limpieza_Biblioteca.md"

    lineas = [
        "# Limpieza de la Biblioteca — CleoIA",
        "",
        f"Fecha de ejecución: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Resumen del procesamiento",
        "",
        f"- PDFs encontrados: **{total_encontrados}**",
        f"- Procesados correctamente: **{len(procesados_ok)}**",
        f"- Errores: **{len(errores)}**",
        f"- Tiempo total de procesamiento: **{tiempo_total:.2f} segundos**",
        "",
    ]

    if errores:
        lineas.append("## Errores encontrados")
        lineas.append("")
        for error in errores:
            lineas.append(f"- `{error['archivo']}`: {error['mensaje']}")
        lineas.append("")
    else:
        lineas.append("## Errores encontrados")
        lineas.append("")
        lineas.append("Ninguno. Todos los PDFs se procesaron correctamente.")
        lineas.append("")

    lineas.append("## Documentos procesados")
    lineas.append("")
    lineas.append("| Categoría | Archivo | Páginas | Caracteres | Idioma |")
    lineas.append("|---|---|---|---|---|")
    for doc in procesados_ok:
        lineas.append(
            f"| {doc['categoria']} | {doc['nombre']} | "
            f"{doc['cantidad_paginas']} | {doc['cantidad_caracteres']} | "
            f"{doc['idioma_detectado']} |"
        )
    lineas.append("")

    ruta_log.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_log


def imprimir_resumen_consola(procesados_ok: list, documentos_por_categoria: dict):
    """Imprime en consola una tabla: Categoría | PDFs | Markdown generados."""
    generados_por_categoria = Counter(doc["categoria"] for doc in procesados_ok)

    categorias = sorted(documentos_por_categoria.keys())
    ancho_categoria = max([len("Categoría")] + [len(c) for c in categorias]) + 2

    print("\nResumen de limpieza de la biblioteca")
    print("-" * (ancho_categoria + 24))
    print(f"{'Categoría'.ljust(ancho_categoria)}{'PDFs'.rjust(8)}{'Markdown generados'.rjust(20)}")
    print("-" * (ancho_categoria + 24))

    for categoria in categorias:
        total_pdfs = documentos_por_categoria[categoria]
        total_md = generados_por_categoria.get(categoria, 0)
        print(f"{categoria.ljust(ancho_categoria)}{str(total_pdfs).rjust(8)}{str(total_md).rjust(20)}")

    print("-" * (ancho_categoria + 24))


def main():
    """Orquesta el flujo completo de limpieza de la biblioteca."""
    inicio = time.perf_counter()

    documentos = recorrer_pdfs()
    documentos_por_categoria = Counter(categoria for categoria, _ in documentos)

    procesados_ok = []
    errores = []

    for categoria, ruta_pdf in documentos:
        try:
            metadata = _procesar_documento(categoria, ruta_pdf)
            procesados_ok.append(metadata)
        except Exception as excepcion:  # noqa: BLE001 - se registra y se continúa
            errores.append({"archivo": ruta_pdf.name, "mensaje": str(excepcion)})

    tiempo_total = time.perf_counter() - inicio

    guardar_metadata(procesados_ok)
    generar_log(len(documentos), procesados_ok, errores, tiempo_total)
    imprimir_resumen_consola(procesados_ok, documentos_por_categoria)


if __name__ == "__main__":
    main()
