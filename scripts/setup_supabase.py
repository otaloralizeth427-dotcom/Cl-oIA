"""
setup_supabase.py

Script de verificación de la infraestructura de Supabase para CleoIA.

Comprueba que todo lo necesario para indexar embeddings ya esté en su
lugar: conexión válida, extensión `vector` activa, tablas `documents` y
`document_chunks` (con las columnas agregadas por la migración 0001), y
el bucket de Storage `library`.

Este script es de solo lectura: no crea, modifica ni inserta absolutamente
nada. Si algo falta, lo reporta para que se corrija manualmente (ver
docs/06_Ejecucion_Embeddings.md).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROYECTO / "backend"))

BUCKET_REQUERIDO = os.getenv("SUPABASE_STORAGE_BUCKET", "library")
COLUMNAS_DOCUMENTS = ["id", "categoria", "nombre_archivo"]
COLUMNAS_DOCUMENT_CHUNKS_BASE = ["id", "document_id", "chunk_index", "contenido", "embedding"]
COLUMNAS_MIGRACION_0001 = ["chunk_id", "document_title", "category", "section_title", "word_count"]


# ----------------------------------------------------------------------------
# 1. Verificaciones individuales (todas de solo lectura)
# ----------------------------------------------------------------------------

def obtener_cliente_supabase_local():
    """Reutiliza el cliente definido en backend/app/core/supabase_client.py."""
    from app.core.supabase_client import obtener_cliente_supabase

    return obtener_cliente_supabase()


def verificar_conexion_y_bucket(cliente) -> dict:
    """
    Verifica la conexión y autenticación contra Supabase listando los
    buckets de Storage (una operación liviana que no depende de que las
    tablas del proyecto ya existan) y, de paso, revisa si el bucket
    requerido ('library') está entre ellos.
    """
    try:
        buckets = cliente.storage.list_buckets()
        nombres = {
            (b.get("name") if isinstance(b, dict) else getattr(b, "name", None))
            for b in buckets
        }
        nombres.discard(None)
        return {
            "conexion_ok": True,
            "error": None,
            "bucket_existe": BUCKET_REQUERIDO in nombres,
            "buckets_encontrados": sorted(nombres),
        }
    except Exception as error:  # noqa: BLE001
        return {
            "conexion_ok": False,
            "error": str(error),
            "bucket_existe": False,
            "buckets_encontrados": [],
        }


def verificar_tabla(cliente, nombre_tabla: str, columnas: list[str]) -> dict:
    """
    Verifica que una tabla exista y tenga las columnas indicadas,
    haciendo un `select ... limit 1` (no trae ni modifica datos reales).
    """
    try:
        cliente.table(nombre_tabla).select(",".join(columnas)).limit(1).execute()
        return {"existe": True, "columnas_completas": True, "error": None}
    except Exception as error:  # noqa: BLE001
        mensaje = str(error)
        if "relation" in mensaje and "does not exist" in mensaje:
            return {"existe": False, "columnas_completas": False, "error": mensaje}
        if "column" in mensaje and "does not exist" in mensaje:
            return {"existe": True, "columnas_completas": False, "error": mensaje}
        return {"existe": False, "columnas_completas": False, "error": mensaje}


def verificar_extension_vector(url_conexion_db: str | None) -> dict:
    """
    Verifica si la extensión `vector` está activa, consultando
    `pg_extension` con una conexión directa a Postgres.

    Nota: la API REST de Supabase (PostgREST) solo expone el esquema
    `public`, no `pg_catalog`, así que esta verificación puntual necesita
    la cadena de conexión directa a la base (SUPABASE_DB_URL, disponible
    en Supabase en Project Settings → Database → Connection string). Si
    no está configurada, se omite con una advertencia en vez de fallar.
    """
    if not url_conexion_db:
        return {
            "verificable": False,
            "activa": None,
            "error": "Falta SUPABASE_DB_URL en backend/.env (solo se usa para esta verificación).",
        }

    try:
        import psycopg2

        conexion = psycopg2.connect(url_conexion_db)
        try:
            with conexion.cursor() as cursor:
                cursor.execute("select exists(select 1 from pg_extension where extname = 'vector');")
                (activa,) = cursor.fetchone()
        finally:
            conexion.close()
        return {"verificable": True, "activa": bool(activa), "error": None}
    except Exception as error:  # noqa: BLE001
        return {"verificable": False, "activa": None, "error": str(error)}


# ----------------------------------------------------------------------------
# 2. Reporte final
# ----------------------------------------------------------------------------

def _linea(etiqueta: str, estado: str, ancho: int = 45) -> str:
    return f"{etiqueta.ljust(ancho, '.')} {estado}"


def imprimir_reporte(
    conexion: dict,
    extension_vector: dict,
    tabla_documents: dict,
    tabla_document_chunks: dict,
    columnas_migracion: dict,
) -> bool:
    """Imprime el reporte de estado y devuelve True si todo está listo."""
    print("Reporte de estado — Infraestructura Supabase de CleoIA")
    print("=" * 60)

    todo_listo = True

    if conexion["conexion_ok"]:
        print(_linea("Conexión con Supabase", "✅ OK"))
    else:
        print(_linea("Conexión con Supabase", f"❌ Error: {conexion['error']}"))
        todo_listo = False

    if extension_vector["verificable"]:
        estado = "✅ Activa" if extension_vector["activa"] else "❌ No instalada"
        print(_linea("Extensión 'vector' (pgvector)", estado))
        todo_listo = todo_listo and extension_vector["activa"]
    else:
        print(_linea("Extensión 'vector' (pgvector)", f"⚠️  No verificable — {extension_vector['error']}"))

    print(
        _linea(
            "Tabla 'documents'",
            "✅ Existe" if tabla_documents["existe"] else f"❌ No existe — {tabla_documents['error']}",
        )
    )
    todo_listo = todo_listo and tabla_documents["existe"]

    print(
        _linea(
            "Tabla 'document_chunks'",
            "✅ Existe" if tabla_document_chunks["existe"] else f"❌ No existe — {tabla_document_chunks['error']}",
        )
    )
    todo_listo = todo_listo and tabla_document_chunks["existe"]

    if tabla_document_chunks["existe"]:
        if columnas_migracion["columnas_completas"]:
            print(_linea("Migración 0001 (columnas de embeddings)", "✅ Aplicada"))
        else:
            print(
                _linea(
                    "Migración 0001 (columnas de embeddings)",
                    "❌ Falta aplicarla (chunk_id, document_title, category, section_title, word_count)",
                )
            )
            todo_listo = False

    if conexion["conexion_ok"]:
        estado_bucket = "✅ Existe" if conexion["bucket_existe"] else f"❌ No existe (buckets encontrados: {conexion['buckets_encontrados'] or 'ninguno'})"
        print(_linea(f"Bucket de Storage '{BUCKET_REQUERIDO}'", estado_bucket))
        todo_listo = todo_listo and conexion["bucket_existe"]
    else:
        print(_linea(f"Bucket de Storage '{BUCKET_REQUERIDO}'", "⚠️  No verificable (sin conexión)"))

    print("=" * 60)
    if todo_listo:
        print("✅ Todo listo: puedes ejecutar scripts/embed_chunks.py")
    else:
        print("⚠️  Hay pasos pendientes. Revisa docs/06_Ejecucion_Embeddings.md")
    print()

    return todo_listo


# ----------------------------------------------------------------------------
# 3. Orquestación
# ----------------------------------------------------------------------------

def main():
    load_dotenv(RAIZ_PROYECTO / "backend" / ".env")

    print("Verificando configuración de Supabase para CleoIA...\n")

    try:
        cliente = obtener_cliente_supabase_local()
    except Exception as error:  # noqa: BLE001
        print(
            "No se pudo crear el cliente de Supabase (revisa SUPABASE_URL y "
            f"SUPABASE_SERVICE_ROLE_KEY en backend/.env): {error}"
        )
        return

    conexion = verificar_conexion_y_bucket(cliente)
    extension_vector = verificar_extension_vector(os.getenv("SUPABASE_DB_URL"))
    tabla_documents = verificar_tabla(cliente, "documents", COLUMNAS_DOCUMENTS)
    tabla_document_chunks = verificar_tabla(cliente, "document_chunks", COLUMNAS_DOCUMENT_CHUNKS_BASE)
    columnas_migracion = verificar_tabla(cliente, "document_chunks", COLUMNAS_MIGRACION_0001)

    imprimir_reporte(
        conexion,
        extension_vector,
        tabla_documents,
        tabla_document_chunks,
        columnas_migracion,
    )


if __name__ == "__main__":
    main()
