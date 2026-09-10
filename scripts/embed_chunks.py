"""
embed_chunks.py

Script de generación de embeddings e indexación vectorial para CleoIA.

Recorre recursivamente todos los `*_chunks.json` de `library/chunks/`,
genera un embedding por cada chunk usando la API de OpenAI
(`text-embedding-3-small`) y lo inserta —junto con la metadata del
chunk— en la tabla `document_chunks` de Supabase.

Incluye:
    - Barra de progreso en consola (global y por documento).
    - Reintentos automáticos con backoff ante fallos transitorios, tanto
      al generar embeddings como al insertar en Supabase.
    - Un resumen final y `library/metadata/embeddings_metadata.json` con
      las estadísticas de la ejecución (se generan siempre al terminar,
      incluso si hubo errores en algunos lotes).

Solo lee `library/chunks/` (y, de forma indirecta, `library/clean/` a
través de los chunks ya generados en el Capítulo 4). No modifica ninguno
de los dos.

Requiere:
    - Variables de entorno: OPENAI_API_KEY, SUPABASE_URL,
      SUPABASE_SERVICE_ROLE_KEY (ver backend/.env.example).
    - Haber aplicado backend/database/schema.sql y
      backend/database/migrations/0001_embeddings_document_chunks.sql
      en el proyecto de Supabase.

Nota: este script realiza llamadas reales (y con costo) a la API de
OpenAI, y escribe datos reales en Supabase. No se ejecuta como parte de
la preparación del proyecto: se corre manualmente cuando las credenciales
estén configuradas.
"""

import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# Rutas y configuración
# ----------------------------------------------------------------------------
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
DIR_CHUNKS = RAIZ_PROYECTO / "library" / "chunks"
DIR_METADATA = RAIZ_PROYECTO / "library" / "metadata"

# Permite importar `obtener_cliente_supabase` desde backend/app/core.
sys.path.insert(0, str(RAIZ_PROYECTO / "backend"))

MODELO_EMBEDDING = "text-embedding-3-small"
DIMENSIONES_EMBEDDING = 1536
TABLA_DESTINO = os.getenv("SUPABASE_CHUNKS_TABLE", "document_chunks")
TAMANO_LOTE = 50  # chunks por llamada a OpenAI / por inserción en Supabase
INTENTOS_MAXIMOS = 3  # reintentos automáticos ante fallos transitorios
ESPERA_BASE_SEGUNDOS = 2  # backoff: 2s, 4s, 6s...


# ----------------------------------------------------------------------------
# 1. Lectura de los chunks generados en el Capítulo 4
# ----------------------------------------------------------------------------

def recorrer_archivos_chunks() -> list[Path]:
    """Encuentra recursivamente todos los `*_chunks.json` en library/chunks/."""
    if not DIR_CHUNKS.exists():
        return []
    return sorted(DIR_CHUNKS.rglob("*_chunks.json"))


def extraer_section_title(texto_chunk: str) -> str | None:
    """
    Obtiene el título de sección de un chunk a partir de su primera línea:
    puede ser un encabezado Markdown (# o ##) o la referencia de contexto
    "_(Sección: ...)_" que agrega `chunk_documents.py` cuando el chunk
    empieza a mitad de una sección.
    """
    primera_linea = texto_chunk.strip().splitlines()[0] if texto_chunk.strip() else ""

    if primera_linea.startswith("## "):
        return primera_linea[3:].strip()
    if primera_linea.startswith("# "):
        return primera_linea[2:].strip()

    coincidencia = re.match(r"_\(Sección: (.+)\)_", primera_linea)
    if coincidencia:
        return coincidencia.group(1).strip()

    return None


def cargar_chunks_de_archivo(ruta_json: Path) -> list[dict]:
    """
    Carga un `*_chunks.json` (generado en el Capítulo 4) y traduce cada
    registro al formato de metadata solicitado para la indexación:
    chunk_id, document_id, document_title, category, section_title,
    chunk_index, word_count y text.
    """
    chunks_originales = json.loads(ruta_json.read_text(encoding="utf-8"))

    registros = []
    for chunk in chunks_originales:
        registros.append(
            {
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "document_title": chunk["titulo_documento"],
                "category": chunk["categoria"],
                "section_title": extraer_section_title(chunk["texto"]),
                "chunk_index": chunk["chunk_number"],
                "word_count": chunk["palabras"],
                "text": chunk["texto"],
            }
        )
    return registros


# ----------------------------------------------------------------------------
# 2. Clientes externos (OpenAI y Supabase)
# ----------------------------------------------------------------------------

def obtener_cliente_openai():
    """Inicializa el cliente de OpenAI a partir de OPENAI_API_KEY."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "Falta la variable de entorno OPENAI_API_KEY. Defínela en "
            "backend/.env antes de ejecutar este script."
        )
    return OpenAI(api_key=api_key)


def obtener_cliente_supabase_local():
    """Reutiliza el cliente definido en backend/app/core/supabase_client.py."""
    from app.core.supabase_client import obtener_cliente_supabase

    return obtener_cliente_supabase()


def obtener_chunk_ids_existentes(cliente_supabase, tabla: str) -> set[str]:
    """
    Consulta en Supabase los `chunk_id` ya indexados, para no volver a
    insertar (ni volver a pagar el embedding de) un chunk que ya existe.
    """
    existentes: set[str] = set()
    desde = 0
    tamano_pagina = 1000

    while True:
        respuesta = (
            cliente_supabase.table(tabla)
            .select("chunk_id")
            .range(desde, desde + tamano_pagina - 1)
            .execute()
        )
        filas = respuesta.data or []
        existentes.update(fila["chunk_id"] for fila in filas if fila.get("chunk_id"))

        if len(filas) < tamano_pagina:
            break
        desde += tamano_pagina

    return existentes


# ----------------------------------------------------------------------------
# 3. Embeddings e inserción por lotes
# ----------------------------------------------------------------------------

def con_reintentos(funcion, *args, **kwargs):
    """
    Ejecuta `funcion(*args, **kwargs)` con reintentos automáticos y
    backoff progresivo (2s, 4s, 6s...) ante fallos transitorios: caídas de
    red, límites de tasa (rate limiting) de OpenAI, o errores momentáneos
    de Supabase. Si se agotan los intentos, se relanza el último error
    para que el llamador lo registre y continúe con el siguiente lote.
    """
    ultimo_error = None
    for intento in range(1, INTENTOS_MAXIMOS + 1):
        try:
            return funcion(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 - se reintenta o se relanza
            ultimo_error = error
            if intento < INTENTOS_MAXIMOS:
                espera = ESPERA_BASE_SEGUNDOS * intento
                print(
                    f"\n  ⚠️  Intento {intento}/{INTENTOS_MAXIMOS} falló ({error}); "
                    f"reintentando en {espera}s..."
                )
                time.sleep(espera)
    raise ultimo_error


def generar_embeddings_lote(cliente_openai, textos: list[str]) -> list[list[float]]:
    """Genera embeddings para una lista de textos en una sola llamada a la API."""
    respuesta = cliente_openai.embeddings.create(model=MODELO_EMBEDDING, input=textos)
    return [item.embedding for item in respuesta.data]


def insertar_lote_supabase(cliente_supabase, tabla: str, registros: list[dict]) -> None:
    """Inserta un lote de chunks (ya con su embedding) en Supabase."""
    filas = [
        {
            "document_id": r["document_id"],
            "chunk_id": r["chunk_id"],
            "chunk_index": r["chunk_index"],
            "contenido": r["text"],
            "embedding": r["embedding"],
            "document_title": r["document_title"],
            "category": r["category"],
            "section_title": r["section_title"],
            "word_count": r["word_count"],
        }
        for r in registros
    ]
    cliente_supabase.table(tabla).insert(filas).execute()


# ----------------------------------------------------------------------------
# 4. Progreso, metadata final y resumen en consola
# ----------------------------------------------------------------------------

def barra_progreso(actual: int, total: int, ancho: int = 30) -> str:
    """Construye una barra de progreso de texto, ej. '[████████░░] 78.0%'."""
    fraccion = min(actual / total, 1.0) if total else 1.0
    llenado = int(ancho * fraccion)
    barra = "█" * llenado + "░" * (ancho - llenado)
    return f"[{barra}] {fraccion * 100:5.1f}%"


def imprimir_progreso(
    indice_documento: int,
    total_documentos: int,
    nombre_documento: str,
    chunks_procesados_doc: int,
    total_chunks_doc: int,
    procesados_global: int,
    total_chunks_global: int,
) -> None:
    """Imprime una barra de progreso global que se actualiza en la misma
    línea, mostrando además el documento actual y su avance."""
    barra = barra_progreso(procesados_global, total_chunks_global)
    linea = (
        f"\r{barra} | doc [{indice_documento}/{total_documentos}] {nombre_documento} "
        f"({chunks_procesados_doc}/{total_chunks_doc})"
    )
    # Rellena con espacios por si la línea anterior era más larga.
    print(linea.ljust(120), end="", flush=True)


def guardar_metadata_embeddings(estadisticas: dict) -> Path:
    """Guarda `library/metadata/embeddings_metadata.json` con el resultado
    de la indexación."""
    DIR_METADATA.mkdir(parents=True, exist_ok=True)
    ruta = DIR_METADATA / "embeddings_metadata.json"
    ruta.write_text(json.dumps(estadisticas, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def imprimir_resumen_final(estadisticas: dict) -> None:
    print("\nResumen de indexación de embeddings")
    print("-" * 60)
    print(f"Modelo de embeddings: {estadisticas['modelo_embedding']}")
    print(f"Tabla destino: {estadisticas['tabla_destino']}")
    print(f"Chunks encontrados en la biblioteca: {estadisticas['total_chunks_biblioteca']}")
    print(f"Chunks ya indexados (omitidos): {estadisticas['total_chunks_omitidos']}")
    print(f"Chunks nuevos insertados: {estadisticas['total_chunks_insertados']}")
    print(f"Errores: {len(estadisticas['errores'])}")
    for error in estadisticas["errores"]:
        print(f"  - {error['archivo']}: {error['mensaje']}")
    print(f"Tiempo total: {estadisticas['tiempo_segundos']:.2f} segundos")
    print("-" * 60)


# ----------------------------------------------------------------------------
# 5. Orquestación
# ----------------------------------------------------------------------------

def main():
    load_dotenv(RAIZ_PROYECTO / "backend" / ".env")
    inicio = time.perf_counter()

    try:
        cliente_openai = obtener_cliente_openai()
        cliente_supabase = obtener_cliente_supabase_local()
    except Exception as error:  # noqa: BLE001 - error de configuración, no de datos
        print(
            "No se pudo iniciar la indexación (revisa credenciales en "
            f"backend/.env y que las dependencias estén instaladas): {error}"
        )
        return

    print("Consultando chunks ya indexados en Supabase...")
    try:
        chunk_ids_existentes = obtener_chunk_ids_existentes(cliente_supabase, TABLA_DESTINO)
    except Exception as error:  # noqa: BLE001
        print(
            f"No se pudo consultar la tabla '{TABLA_DESTINO}'. Verifica que "
            f"el esquema y la migración 0001 ya se hayan aplicado en Supabase. "
            f"Detalle: {error}"
        )
        return

    rutas_chunks = recorrer_archivos_chunks()
    documentos = [(ruta, cargar_chunks_de_archivo(ruta)) for ruta in rutas_chunks]

    total_chunks_biblioteca = sum(len(chunks) for _, chunks in documentos)
    total_chunks_omitidos = 0
    total_chunks_insertados = 0
    chunks_por_categoria = Counter()
    errores = []
    procesados_global = 0

    for indice_documento, (ruta, registros) in enumerate(documentos, start=1):
        nombre_documento = ruta.stem
        pendientes = [r for r in registros if r["chunk_id"] not in chunk_ids_existentes]
        total_chunks_omitidos += len(registros) - len(pendientes)
        procesados_doc = len(registros) - len(pendientes)

        for inicio_lote in range(0, len(pendientes), TAMANO_LOTE):
            lote = pendientes[inicio_lote : inicio_lote + TAMANO_LOTE]
            try:
                embeddings = con_reintentos(generar_embeddings_lote, cliente_openai, [r["text"] for r in lote])
                for registro, embedding in zip(lote, embeddings):
                    registro["embedding"] = embedding

                con_reintentos(insertar_lote_supabase, cliente_supabase, TABLA_DESTINO, lote)

                for registro in lote:
                    chunk_ids_existentes.add(registro["chunk_id"])
                    chunks_por_categoria[registro["category"]] += 1

                total_chunks_insertados += len(lote)
                procesados_doc += len(lote)
                procesados_global += len(lote)
            except Exception as error:  # noqa: BLE001 - ya se reintentó; se registra y se continúa
                print(f"\n  ❌ Falló definitivamente el lote de '{nombre_documento}': {error}")
                errores.append({"archivo": nombre_documento, "mensaje": str(error)})

            imprimir_progreso(
                indice_documento,
                len(documentos),
                nombre_documento,
                procesados_doc,
                len(registros),
                procesados_global + total_chunks_omitidos,
                total_chunks_biblioteca,
            )

    print()  # cierra la línea de la barra de progreso antes del resumen
    tiempo_total = time.perf_counter() - inicio

    estadisticas = {
        "modelo_embedding": MODELO_EMBEDDING,
        "dimensiones_embedding": DIMENSIONES_EMBEDDING,
        "tabla_destino": TABLA_DESTINO,
        "total_chunks_biblioteca": total_chunks_biblioteca,
        "total_chunks_omitidos": total_chunks_omitidos,
        "total_chunks_insertados": total_chunks_insertados,
        "chunks_por_categoria": dict(chunks_por_categoria),
        "errores": errores,
        "tiempo_segundos": round(tiempo_total, 2),
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
    }

    guardar_metadata_embeddings(estadisticas)
    imprimir_resumen_final(estadisticas)


if __name__ == "__main__":
    main()
