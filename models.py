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
from datetime import date, datetime, time   # añade datetime al import


class Company(BaseModel):
    """Empresa del S&P 500 tal como la devuelve nuestra API."""
    ticker: str
    name: str | None
    sector: str | None
    industry: str | None
    country: str | None
    market_cap: float | None
    current_price: float | None
    trailing_pe: float | None
    dividend_yield: float | None
    updated_at: datetime | None


class Sector(BaseModel):
    sector: str
    companies: int


class PricePoint(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int | None


class PriceSeries(BaseModel):
    ticker: str
    count: int
    prices: list[PricePoint]
