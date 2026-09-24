from uuid import UUID
from fastapi import HTTPException


def parse_uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(422, "Identificador inválido.")
