# Embeddings e Indexación Vectorial — CleoIA

## ¿Qué es un embedding?

Un *embedding* es la representación numérica del significado de un texto: un
vector (una lista de números, en este caso 1536) que un modelo de lenguaje
genera a partir de una oración, un párrafo o —en el caso de CleoIA— un
chunk completo.

Dos textos con significados parecidos generan vectores parecidos, aunque
usen palabras distintas. Por ejemplo, "colores que favorecen a piel fría" y
"paleta ideal para subtono frío" producirían embeddings muy cercanos entre
sí, incluso sin compartir las mismas palabras exactas. Esa es la propiedad
que hace posible la búsqueda semántica.

En CleoIA, cada uno de los 125 chunks generados en el Capítulo 4 se convierte
en un embedding usando el modelo `text-embedding-3-small` de OpenAI.

## ¿Qué es una base de datos vectorial?

Una base de datos vectorial es una base de datos preparada para almacenar
embeddings y responder preguntas del tipo "¿qué vectores son más parecidos a
este?", en lugar de las consultas exactas típicas de una base de datos
relacional ("¿qué fila tiene este ID?").

CleoIA no usa una base de datos vectorial dedicada aparte: usa **Supabase**
(PostgreSQL) con la extensión **pgvector**, que agrega el tipo de dato
`vector` y algoritmos de búsqueda por similitud directamente a Postgres. Así,
una misma base de datos guarda tanto los datos relacionales del proyecto
(categorías, títulos, metadata) como los embeddings, sin necesidad de
sincronizar dos sistemas distintos.

## ¿Cómo realiza Supabase la búsqueda semántica?

1. Cada fila de la tabla `document_chunks` guarda, junto al texto del
   chunk y su metadata, su embedding en una columna de tipo
   `vector(1536)`.
2. Cuando se necesita buscar contenido relevante, la pregunta del usuario
   también se convierte en un embedding (con el mismo modelo,
   `text-embedding-3-small`, para que los vectores sean comparables).
3. Postgres, gracias a `pgvector`, puede calcular la distancia (similitud
   coseno) entre ese embedding y los de todos los chunks almacenados, y
   devolver los más cercanos con una consulta SQL como:

   ```sql
   select *
   from document_chunks
   order by embedding <=> '[...vector de la pregunta...]'
   limit 5;
   ```

4. El índice `ivfflat` creado en `schema.sql` acelera esa búsqueda para que
   siga siendo rápida incluso cuando la biblioteca crezca a miles de
   chunks.

## ¿Cómo indexa CleoIA sus embeddings? (`scripts/embed_chunks.py`)

El script de este capítulo:

1. Recorre todos los `*_chunks.json` de `library/chunks/` (generados en el
   Capítulo 4, sin modificarlos).
2. Genera el embedding de cada chunk en lotes (por defecto, de 50 chunks
   por llamada a la API de OpenAI), para no exceder los límites de tamaño
   de solicitud.
3. Antes de insertar, consulta qué `chunk_id` ya existen en
   `document_chunks`, para no volver a generar (ni pagar) el embedding de
   un chunk ya indexado si el script se corre más de una vez.
4. Inserta cada lote en Supabase con toda su metadata: `chunk_id`,
   `document_id`, `document_title`, `category`, `section_title`,
   `chunk_index`, `word_count` y el texto del chunk.
5. Al finalizar, guarda `library/metadata/embeddings_metadata.json` con las
   estadísticas de la ejecución (chunks encontrados, insertados, omitidos
   por ya existir, errores y tiempo total).

> Este script requiere credenciales reales (`OPENAI_API_KEY`,
> `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) y que la migración
> [`0001_embeddings_document_chunks.sql`](../backend/database/migrations/0001_embeddings_document_chunks.sql)
> ya se haya aplicado en el proyecto de Supabase. No se ejecuta
> automáticamente como parte de la preparación del repositorio, porque
> genera costo real en la API de OpenAI y escribe datos reales en la base
> de datos.

## ¿Cómo recuperará CleoIA contexto usando estos embeddings?

Cuando el sistema esté completo (backend + frontend), el flujo de una
pregunta del usuario será:

1. El usuario escribe una pregunta (ej. "¿qué me pongo para una boda de
   día?").
2. El backend (FastAPI) genera el embedding de esa pregunta con
   `text-embedding-3-small` — el mismo modelo usado para indexar la
   biblioteca, para que los vectores sean comparables.
3. El backend consulta `document_chunks` en Supabase pidiendo los chunks
   cuyo embedding sea más cercano al de la pregunta (por ejemplo, los 5
   más relevantes).
4. Esos chunks —con su texto, categoría y sección de origen— se le entregan
   como contexto al modelo de lenguaje (Cloudflare AI / Qwen), que redacta
   la respuesta final basándose en el contenido real de la biblioteca de
   CleoIA, en lugar de responder de forma genérica.

Este capítulo deja lista la biblioteca para ese último paso: la generación
de embeddings y su carga en Supabase se ejecutarán cuando las credenciales
estén configuradas; la lógica de búsqueda y respuesta (el endpoint de chat)
se construirá en un capítulo posterior.
