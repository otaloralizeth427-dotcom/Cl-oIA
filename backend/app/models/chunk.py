"""
chunk.py

Modelo de datos (Pydantic) que representa un fragmento (chunk) de texto de
un documento, correspondiente a la tabla `document_chunks` en Supabase.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentChunk(BaseModel):
    """Representa un fragmento de texto vectorizado de un documento."""

    id: Optional[UUID] = None

    # Documento al que pertenece este fragmento.
    document_id: UUID

    # Número de orden del chunk dentro del documento (0, 1, 2, ...).
    chunk_index: int

    # Contenido de texto limpio del fragmento.
    contenido: str

    # Representación vectorial (embedding) del contenido.
    embedding: Optional[list[float]] = None

    # Metadatos adicionales del fragmento (página, sección, etc.).
    metadata: Optional[dict[str, Any]] = None

    creado_en: Optional[datetime] = None
