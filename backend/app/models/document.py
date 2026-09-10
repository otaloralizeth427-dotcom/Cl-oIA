"""
document.py

Modelo de datos (Pydantic) que representa un documento de la biblioteca de
conocimiento de CleoIA, correspondiente a la tabla `documents` en Supabase.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class Document(BaseModel):
    """Representa un documento original (PDF) de la biblioteca de CleoIA."""

    id: Optional[UUID] = None

    # Categoría del documento (ej. "01_Colorimetria").
    categoria: str

    # Nombre del archivo original (ej. "01_Colores_que_no_debes_usar.pdf").
    nombre_archivo: str

    # Ruta o referencia al archivo dentro del Storage Bucket de Supabase.
    ruta_storage: Optional[str] = None

    # Idioma del documento.
    idioma: str = "español"

    # Metadatos adicionales en formato libre.
    metadata: Optional[dict[str, Any]] = None

    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
