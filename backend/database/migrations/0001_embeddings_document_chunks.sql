-- ============================================================================
-- CleoIA · Migración 0001 — Soporte de embeddings en document_chunks
-- ============================================================================
-- El esquema original (backend/database/schema.sql) define
-- `document_chunks.document_id` como uuid con FK a `documents(id)`. Sin
-- embargo, el pipeline de chunking (Capítulo 4) genera un `document_id`
-- propio en formato slug de texto (ej. "01_colorimetria_01_colores_..."),
-- usado de forma consistente en los JSON de `library/chunks/` y en
-- `library/metadata/`. Para no tener dos identificadores distintos del
-- mismo documento, esta migración:
--
--   1. Convierte `document_id` a texto (deja de ser FK a `documents`).
--   2. Agrega `chunk_id` (único), usado para no reinsertar un chunk que
--      ya fue indexado (ver scripts/embed_chunks.py).
--   3. Agrega columnas denormalizadas que vienen del propio chunk
--      (document_title, category, section_title, word_count), para no
--      depender de un JOIN contra `documents` en cada búsqueda semántica.
--
-- No se ejecuta automáticamente: hay que aplicarla manualmente en Supabase
-- (SQL editor o CLI) antes de correr scripts/embed_chunks.py.
-- ============================================================================

alter table document_chunks
    drop constraint if exists document_chunks_document_id_fkey;

alter table document_chunks
    alter column document_id type text using document_id::text;

alter table document_chunks
    add column if not exists chunk_id text;

alter table document_chunks
    add column if not exists document_title text;

alter table document_chunks
    add column if not exists category text;

alter table document_chunks
    add column if not exists section_title text;

alter table document_chunks
    add column if not exists word_count integer;

-- Un mismo chunk (mismo chunk_id) nunca debe insertarse dos veces.
create unique index if not exists idx_document_chunks_chunk_id
    on document_chunks (chunk_id);

-- Índice para filtrar chunks por categoría sin pasar por `documents`.
create index if not exists idx_document_chunks_category
    on document_chunks (category);
