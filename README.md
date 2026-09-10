# CleoIA

CleoIA es un asistente de inteligencia artificial especializado en asesoría de
imagen y estilo personal. Su objetivo es ofrecer recomendaciones fundamentadas
sobre colorimetría, armario cápsula, estilos personales, morfología corporal,
dress code y combinación de colores, apoyándose en una biblioteca de
conocimiento propia mediante un sistema RAG (Retrieval-Augmented Generation).

En lugar de responder solo con el conocimiento general del modelo, CleoIA
recupera información relevante desde su propia biblioteca documental antes de
generar una respuesta, asegurando recomendaciones más precisas y consistentes.

## Tecnologías

- **React** — interfaz de usuario (frontend).
- **FastAPI** — API y lógica de backend.
- **Supabase** — base de datos y backend as a service.
- **pgvector** — extensión de Supabase para almacenamiento y búsqueda de
  vectores (embeddings).
- **RAG (Retrieval-Augmented Generation)** — arquitectura para combinar
  recuperación de información con generación de lenguaje natural.
- **Cloudflare AI (Qwen)** — modelo de lenguaje utilizado para la generación
  de respuestas.
- **Vercel** — plataforma de despliegue del frontend.

## Arquitectura del Proyecto

```
CleoIA/
│
├── backend/          # API construida con FastAPI
├── frontend/          # Interfaz de usuario construida con React
├── docs/               # Documentación del proyecto
├── scripts/           # Scripts de procesamiento (limpieza, chunking, etc.)
├── library/            # Biblioteca de conocimiento para el sistema RAG
│   ├── raw/            # Documentos originales (PDFs) por categoría
│   ├── clean/          # Texto limpio en formato Markdown
│   └── chunks/         # Fragmentos listos para generar embeddings
│
└── README.md
```

El flujo de conocimiento de la biblioteca sigue el siguiente proceso:

```
PDF → Texto limpio → Markdown → Chunks → Embeddings → Supabase
```

Para más detalle sobre la biblioteca de conocimiento, ver
[`docs/01_Biblioteca.md`](docs/01_Biblioteca.md).

## Estado del Proyecto

- ✅ **Capítulo 1 — Estructura inicial del repositorio**: creación del
  repositorio y la organización base de carpetas (`frontend`, `backend`,
  `library`, `docs`).
- ✅ **Capítulo 2 — Preparación de la biblioteca**: definición de la
  arquitectura de la biblioteca de conocimiento (`raw`, `clean`, `chunks`),
  documentación del flujo RAG, configuración de categorías y estructura base
  de scripts y dependencias.
- ⏳ **Próximos capítulos**: implementación del pipeline de limpieza de
  documentos, generación de chunks y embeddings, integración con Supabase, y
  desarrollo de frontend y backend.
