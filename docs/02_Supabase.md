# Supabase — CleoIA

## ¿Qué es Supabase?

Supabase es una plataforma de backend as a service (BaaS) de código abierto,
construida sobre PostgreSQL. Ofrece base de datos relacional, autenticación,
almacenamiento de archivos (Storage) y una API generada automáticamente,
todo administrado desde un mismo proyecto.

En CleoIA, Supabase cumple dos funciones principales:

1. **Base de datos**: almacena la información estructurada de los documentos
   y sus fragmentos (chunks), junto con los embeddings generados a partir de
   ellos.
2. **Storage**: guarda los archivos PDF originales de la biblioteca de
   conocimiento.

## ¿Qué es pgvector?

`pgvector` es una extensión de PostgreSQL que agrega un nuevo tipo de dato,
`vector`, capaz de almacenar embeddings (representaciones numéricas de texto)
y realizar búsquedas por similitud entre ellos (por ejemplo, distancia
coseno o distancia euclidiana).

Gracias a `pgvector`, Supabase puede funcionar como una base de datos
vectorial: en lugar de buscar coincidencias exactas de texto, permite
encontrar los fragmentos de la biblioteca cuyo significado es más cercano a
la pregunta del usuario. Esta capacidad es la base técnica del sistema RAG
de CleoIA.

## ¿Qué es un Storage Bucket?

Un *bucket* es un espacio de almacenamiento dentro de Supabase Storage,
similar a una carpeta raíz, donde se guardan archivos binarios (PDFs,
imágenes, etc.).

Para CleoIA se define el bucket `library`, destinado a alojar los documentos
PDF originales de la biblioteca de conocimiento, organizados por categoría,
de forma equivalente a como están organizados en `library/raw/` dentro del
repositorio.

## ¿Cómo usará CleoIA Supabase?

Supabase será el componente central de persistencia del sistema RAG de
CleoIA:

1. **Documentos (`documents`)**: cada PDF de la biblioteca se registra como
   una fila en la tabla `documents`, con su categoría, nombre y metadatos.
2. **Fragmentos (`document_chunks`)**: el texto de cada documento, una vez
   limpio y dividido en chunks, se guarda en la tabla `document_chunks`,
   junto con el embedding vectorial correspondiente (columna de tipo
   `vector`, gracias a `pgvector`).
3. **Búsqueda semántica**: cuando un usuario hace una pregunta, CleoIA
   convierte la pregunta en un embedding y consulta `document_chunks` para
   encontrar los fragmentos más similares (búsqueda vectorial), que luego se
   usan como contexto para generar la respuesta.
4. **Storage**: el bucket `library` conserva los PDFs originales como fuente
   de verdad, permitiendo volver a procesarlos si cambia el pipeline de
   limpieza o chunking.

> En este capítulo solo se prepara la infraestructura (esquema SQL, cliente
> de conexión y modelos). La conexión real, la carga de datos y las
> consultas se implementarán en capítulos posteriores.
