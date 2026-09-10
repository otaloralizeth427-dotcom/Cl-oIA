"""
supabase_client.py

Define la inicialización del cliente de Supabase para CleoIA.

Este módulo únicamente prepara la función que crea el cliente a partir de
las variables de entorno definidas en `.env` (ver `.env.example`). Todavía
no se realiza ninguna conexión real ni se ejecutan operaciones contra
Supabase; eso se implementará en un capítulo posterior.
"""

import os

from supabase import Client, create_client


def obtener_cliente_supabase() -> Client:
    """
    Inicializa y retorna el cliente de Supabase, leyendo la URL y la
    clave de servicio desde las variables de entorno.

    Variables de entorno esperadas (definidas en `.env`):
        - SUPABASE_URL
        - SUPABASE_SERVICE_ROLE_KEY

    Returns:
        Client: instancia del cliente de Supabase.

    Nota:
        Esta función aún no se invoca en ningún punto del proyecto.
        Se dejará lista para su uso en capítulos posteriores, cuando se
        implemente la conexión real con la base de datos y el Storage.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError(
            "Faltan variables de entorno: SUPABASE_URL y/o "
            "SUPABASE_SERVICE_ROLE_KEY. Verifica el archivo .env."
        )

    return create_client(supabase_url, supabase_key)
