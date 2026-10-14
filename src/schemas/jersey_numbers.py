"""Número opcional da camisa, compartilhado pelos elencos."""
from typing import Annotated
from pydantic import BaseModel, Field

JerseyNumber = Annotated[int, Field(strict=True, ge=0, le=100)]


class JerseyNumberRequest(BaseModel):
    jersey_number: JerseyNumber | None
