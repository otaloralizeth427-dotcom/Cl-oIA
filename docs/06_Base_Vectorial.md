# Base Vectorial — CleoIA

## ¿Qué es pgvector?

`pgvector` es una extensión de PostgreSQL (la usada por Supabase) que agrega
un nuevo tipo de dato, `vector`, junto con operadores y algoritmos para medir
qué tan parecidos son dos vectores entre sí (distancia coseno, distancia
euclidiana, producto interno).

Sin `pgvector`, Postgres podría guardar un embedding como una lista de
números, pero no sabría cómo compararlos de forma eficiente. Con `pgvector`,
una columna `vector(1536)` —como la de `document_chunks.embedding`— se puede
ordenar por cercanía a otro vector directamente en una consulta SQL, y un
índice especializado (`ivfflat`, ya creado en `schema.sql`) hace que esa
búsqueda siga siendo rápida aunque la biblioteca crezca a miles de chunks.

## ¿Qué es una base vectorial?

Una base de datos vectorial es cualquier base de datos capaz de responder la
pregunta "¿qué elementos son más similares a este?", usando embeddings en
lugar de coincidencias exactas de texto.

CleoIA no depende de un motor vectorial dedicado y separado (como Pinecone o
Weaviate): usa **Supabase + pgvector**, es decir, la misma base de datos
PostgreSQL que ya guarda toda la metadata del proyecto también funciona como
base vectorial. Esto simplifica la arquitectura: una sola base de datos, una
sola fuente de verdad, sin sincronizar dos sistemas distintos.

## ¿Cómo funcionará la búsqueda semántica?

1. Cada chunk de la biblioteca (ver [`docs/04_Chunks.md`](04_Chunks.md)) está
   guardado en `document_chunks`, junto con su embedding —un vector de 1536
   posiciones generado con `text-embedding-3-small` (ver
   [`docs/05_Embeddings.md`](05_Embeddings.md))—.
2. Cuando llegue una pregunta, se genera su embedding con el mismo modelo.
3. Postgres compara ese embedding contra los de todos los chunks usando el
   operador de distancia coseno (`<=>`) y devuelve los más cercanos:

   ```sql
   select chunk_id, document_title, category, contenido
   from document_chunks
   order by embedding <=> '[...vector de la pregunta...]'
   limit 5;
   ```

4. El índice `ivfflat` sobre `embedding` evita que Postgres tenga que
   comparar la pregunta contra *todos* los chunks uno por uno, agrupándolos
   en "listas" (clusters) para acotar la búsqueda a las más relevantes.

## Flujo completo: de la pregunta del usuario a la respuesta

```
Usuario pregunta
      │
      ▼
FastAPI recibe la pregunta
      │
      ▼
Se genera el embedding de la pregunta (OpenAI, text-embedding-3-small)
      │
      ▼
Supabase (pgvector) busca los chunks más similares en document_chunks
      │
      ▼
Se arma el contexto con esos chunks (texto + categoría + sección)
      │
      ▼
El modelo de lenguaje (Cloudflare AI / Qwen) redacta la respuesta
usando ese contexto real de la biblioteca de CleoIA
      │
      ▼
FastAPI devuelve la respuesta a React (frontend)
```

Este flujo depende de que la base de datos vectorial esté correctamente
configurada (extensión `vector` activa, tablas y columnas listas) *antes* de
indexar los embeddings. Ese es exactamente el propósito de este capítulo: el
script [`scripts/setup_supabase.py`](../scripts/setup_supabase.py) verifica
que toda esa infraestructura exista, sin insertar ningún dato todavía.

> La generación real de embeddings (`scripts/embed_chunks.py`) y las
> consultas de búsqueda semántica en tiempo real (el endpoint de chat) se
> ejecutarán en capítulos posteriores, una vez configuradas las credenciales
> reales de Supabase y OpenAI.
