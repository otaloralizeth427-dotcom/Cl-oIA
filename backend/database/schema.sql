-- ============================================================================
-- CleoIA · Esquema de base de datos para el sistema RAG
-- ============================================================================
-- Este script define la estructura de la base de datos utilizada para
-- almacenar los documentos de la biblioteca de conocimiento y sus
-- fragmentos (chunks) vectorizados, sobre los que se realizará la búsqueda
-- semántica del sistema RAG.
--
-- No inserta datos. Solo define extensión, tablas e índices.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Extensión pgvector
-- ----------------------------------------------------------------------------
-- Habilita el tipo de dato "vector" en PostgreSQL, necesario para almacenar
-- embeddings y realizar búsquedas por similitud.
create extension if not exists vector;

-- ----------------------------------------------------------------------------
-- 2. Tabla: documents
-- ----------------------------------------------------------------------------
-- Representa cada documento original (PDF) de la biblioteca de conocimiento.
create table if not exists documents (
    id uuid primary key default gen_random_uuid(),

    -- Categoría del documento (ej. "01_Colorimetria", "02_Armario_Capsula").
    categoria text not null,

    -- Nombre del archivo original (ej. "01_Colores_que_no_debes_usar.pdf").
    nombre_archivo text not null,

    -- Ruta o referencia al archivo dentro del Storage Bucket de Supabase.
    ruta_storage text,

    -- Idioma del documento (por defecto, español).
    idioma text not null default 'español',

    -- Metadatos adicionales en formato libre (autor, fuente, notas, etc.).
    metadata jsonb,

    creado_en timestamptz not null default now(),
    actualizado_en timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- 3. Tabla: document_chunks
-- ----------------------------------------------------------------------------
-- Representa cada fragmento (chunk) de texto extraído de un documento,
-- junto con su embedding vectorial correspondiente.
create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),

    -- Documento al que pertenece este fragmento.
    document_id uuid not null references documents (id) on delete cascade,

    -- Número de orden del chunk dentro del documento (0, 1, 2, ...).
    chunk_index integer not null,

    -- Contenido de texto limpio del fragmento.
    contenido text not null,

    -- Representación vectorial (embedding) del contenido.
    -- La dimensión (1536) debe ajustarse según el modelo de embeddings usado.
    embedding vector(1536),

    -- Metadatos adicionales del fragmento (página, sección, etc.).
    metadata jsonb,

    creado_en timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- 4. Índices
-- ----------------------------------------------------------------------------

-- Índice para filtrar rápidamente documentos por categoría.
create index if not exists idx_documents_categoria
    on documents (categoria);

-- Índice para acceder rápidamente a los chunks de un documento específico.
create index if not exists idx_document_chunks_document_id
    on document_chunks (document_id);

-- Índice vectorial (ivfflat) para búsqueda por similitud sobre los
-- embeddings de los chunks. Se utiliza distancia coseno, adecuada para
-- embeddings de modelos de lenguaje.
create index if not exists idx_document_chunks_embedding
    on document_chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);
