from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class ValidacionBase(BaseModel):
    """Version más reducida necesaria para validar"""
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(min_length=1, max_length=100)
    event_type: Literal['verification.simple']
