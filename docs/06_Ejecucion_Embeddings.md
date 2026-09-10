# Guía de ejecución: Embeddings y Base Vectorial — CleoIA

Esta guía explica, paso a paso, cómo pasar de "todo el código está listo"
a "los 125 chunks de la biblioteca están indexados con sus embeddings en
Supabase". Ningún paso se ejecutó todavía: se hace manualmente, una vez que
tengas tu propio proyecto de Supabase y tu API key de OpenAI.

## 1. Crear el proyecto en Supabase

1. Entra a [supabase.com](https://supabase.com) e inicia sesión.
2. Crea un nuevo proyecto (elige una región cercana, por ejemplo
   `us-east-1`, y define una contraseña segura para la base de datos).
3. Espera a que el proyecto termine de aprovisionarse (unos minutos).

## 2. Ejecutar `schema.sql`

1. En el panel de Supabase, ve a **SQL Editor**.
2. Abre el archivo [`backend/database/schema.sql`](../backend/database/schema.sql)
   de este repositorio, copia todo su contenido y pégalo en el editor.
3. Ejecuta la consulta. Esto crea la extensión `vector`, y las tablas
   `documents` y `document_chunks` con sus índices.

## 3. Ejecutar la migración `0001`

1. Sigue en el **SQL Editor** de Supabase.
2. Copia el contenido de
   [`backend/database/migrations/0001_embeddings_document_chunks.sql`](../backend/database/migrations/0001_embeddings_document_chunks.sql)
   y ejecútalo.
3. Esto ajusta `document_chunks.document_id` a texto y agrega las columnas
   que usa el pipeline de embeddings (`chunk_id`, `document_title`,
   `category`, `section_title`, `word_count`).

## 4. Crear el bucket de Storage `library`

1. Ve a **Storage** en el panel de Supabase.
2. Crea un bucket llamado exactamente `library` (el mismo nombre definido
   en `SUPABASE_STORAGE_BUCKET`).
3. Puede ser privado; CleoIA no necesita que sea público.

## 5. Configurar `backend/.env`

1. Copia la plantilla:

   ```bash
   cp backend/.env.example backend/.env
   ```

2. Completa cada variable con tus valores reales (Project Settings de
   Supabase → API, y tu cuenta de OpenAI → API Keys):

   ```
   SUPABASE_URL=https://tu-proyecto.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
   SUPABASE_ANON_KEY=tu-anon-key
   OPENAI_API_KEY=sk-tu-api-key
   SUPABASE_STORAGE_BUCKET=library
   SUPABASE_CHUNKS_TABLE=document_chunks
   SUPABASE_DB_URL=postgresql://postgres:tu-password@db.tu-proyecto.supabase.co:5432/postgres
   ```

   `SUPABASE_DB_URL` es opcional: solo la usa `setup_supabase.py` para
   confirmar que la extensión `vector` está activa (se obtiene en Project
   Settings → Database → Connection string → "URI").

3. **Nunca subas `backend/.env` a GitHub** — ya está listado en
   `.gitignore` precisamente por esto.

4. Instala las dependencias del backend:

   ```bash
   pip install -r backend/requirements.txt
   ```

## 6. Ejecutar `setup_supabase.py`

```bash
python3 scripts/setup_supabase.py
```

Este script **no inserta nada**: solo verifica que todo lo anterior haya
quedado bien configurado (conexión, extensión `vector`, tablas, columnas de
la migración y el bucket `library`), y muestra un reporte como:

```
Conexión con Supabase....................... ✅ OK
Extensión 'vector' (pgvector)................ ✅ Activa
Tabla 'documents'............................ ✅ Existe
Tabla 'document_chunks'...................... ✅ Existe
Migración 0001 (columnas de embeddings)...... ✅ Aplicada
Bucket de Storage 'library'.................. ✅ Existe
```

Si algo aparece en ❌, corrige ese paso específico (repite el paso de esta
guía correspondiente) antes de continuar.

## 7. Ejecutar `embed_chunks.py`

Solo cuando el reporte anterior esté completamente en ✅:

```bash
python3 scripts/embed_chunks.py
```

Esto:

1. Genera el embedding de cada uno de los 125 chunks (en lotes de 50,
   usando `text-embedding-3-small`) — **esto tiene costo real** en tu
   cuenta de OpenAI, aunque para 125 chunks es un costo mínimo (fracciones
   de centavo de dólar).
2. Inserta cada chunk en `document_chunks`, junto a su embedding.
3. Si el script se interrumpe o se corre de nuevo, no vuelve a generar ni
   insertar los chunks cuyo `chunk_id` ya exista en Supabase.
4. Al terminar, deja el resultado en
   [`library/metadata/embeddings_metadata.json`](../library/metadata/embeddings_metadata.json).

## Resumen del orden de ejecución

```
1. Crear proyecto Supabase
2. Ejecutar schema.sql            (SQL Editor)
3. Ejecutar migración 0001        (SQL Editor)
4. Crear bucket "library"         (Storage)
5. Completar backend/.env
6. pip install -r backend/requirements.txt
7. python3 scripts/setup_supabase.py   → debe salir todo en ✅
8. python3 scripts/embed_chunks.py     → indexa los 125 chunks
```
