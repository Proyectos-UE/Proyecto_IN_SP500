from typing import Literal
from datetime import date, time
from pydantic import BaseModel, ConfigDict, Field

class ValidacionBase(BaseModel):
    """Version más reducida necesaria para validar"""
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(min_length=1, max_length=100)
    event_type: Literal['verification.simple']


class Evento(BaseModel):
    """Esquema usado para guardar los eventos"""
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    origen: str = Field(min_length=1, max_length=100)
    resultado: str = Field(min_length=1, max_length=100)
    fecha: date = Field(min_length=1, max_length=30)
    hora: time = Field(min_length=1, max_length=30)