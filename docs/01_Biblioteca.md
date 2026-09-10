# Biblioteca de Conocimiento — CleoIA

## Objetivo de la biblioteca

La biblioteca de conocimiento es la fuente documental que alimenta el sistema RAG
(Retrieval-Augmented Generation) de CleoIA. Reúne el material de referencia sobre
asesoría de imagen y estilo personal que el asistente utilizará para responder con
fundamento, en lugar de depender únicamente del conocimiento general del modelo.

Cada documento se procesa, se limpia y se fragmenta en unidades pequeñas (chunks)
que luego se convierten en embeddings y se almacenan en una base de datos vectorial,
permitiendo que CleoIA recupere el contenido más relevante para cada consulta del
usuario.

## Estructura de carpetas

```
library/
├── raw/         # Documentos originales (PDFs), organizados por categoría
│   ├── 01_Colorimetria/
│   ├── 02_Armario_Capsula/
│   ├── 03_Estilos_Personales/
│   ├── 04_Morfologia_Corporal/
│   ├── 05_Dress_Code/
│   └── 06_Combinacion_Colores/
├── clean/       # Texto extraído y limpio en formato Markdown
├── chunks/      # Fragmentos (chunks) listos para generar embeddings
└── library_config.json
```

## Cantidad de categorías

La biblioteca está organizada en **6 categorías** temáticas:

1. Colorimetría
2. Armario Cápsula
3. Estilos Personales
4. Morfología Corporal
5. Dress Code
6. Combinación de Colores

## Flujo de procesamiento RAG

El procesamiento de la biblioteca sigue el siguiente flujo:

```
PDF → Texto limpio → Markdown → Chunks → Embeddings → Supabase
```

1. **PDF**: documento original ubicado en `library/raw/<categoria>/`.
2. **Texto limpio**: extracción del contenido del PDF y limpieza de ruido
   (encabezados, pies de página, saltos de línea innecesarios, etc.).
3. **Markdown**: el texto limpio se guarda en `library/clean/` con formato
   Markdown, conservando su estructura semántica (títulos, listas, párrafos).
4. **Chunks**: el contenido en Markdown se divide en fragmentos pequeños y
   coherentes, almacenados en `library/chunks/`, optimizados para su
   recuperación posterior.
5. **Embeddings**: cada chunk se convierte en un vector numérico mediante un
   modelo de embeddings.
6. **Supabase**: los embeddings y sus metadatos se almacenan en Supabase
   (con la extensión `pgvector`) para su búsqueda semántica.

> Este documento describe la organización de la biblioteca. La implementación
> del procesamiento se abordará en capítulos posteriores del proyecto.
