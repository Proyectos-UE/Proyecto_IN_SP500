#AQUI PARA HACER LA APLICACION
from datetime import date
from pathlib import Path
from typing import Annotated
import os
import hmac
import hashlib

import pandas as pd
from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from pydantic import ValidationError
from dotenv import load_dotenv

from datos import DataStore
from models import Company, PricePoint, PriceSeries, Sector, ValidacionBase

load_dotenv()

DATA = Path(__file__).parent / 'data'

# Ticker válido: letras, números, punto o guion (AAPL, BRK-B), de 1 a 10 caracteres
Ticker = Annotated[str, PathParam(pattern=r'^[A-Za-z0-9.\-]{1,10}$', description='Símbolo, p. ej. AAPL')]

def valid_signature(body: bytes, received: str, secretWH: bytes) -> bool:
    """Verifica la firma en forma de cadena de Bytes."""
    expected = 'sha256=' + hmac.new(secretWH, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)

def to_company(row: dict) -> Company:
    """Traduce las columnas de Yahoo (modelo externo) a nuestro modelo público."""
    return Company(
        ticker=row['Ticker'],
        name=row.get('longName') or row.get('shortName'),
        sector=row.get('sector'),
        industry=row.get('industry'),
        country=row.get('country'),
        market_cap=row.get('marketCap'),
        current_price=row.get('currentPrice'),
        trailing_pe=row.get('trailingPE'),
        dividend_yield=row.get('dividendYield'),
        updated_at=row.get('FechaDescarga'),
    )


def nan_to_none(value):
    """pandas usa NaN para los huecos; en JSON tiene que ser null."""
    return None if pd.isna(value) else value

def create_app(dataDir: Path, secretWH: bytes) -> FastAPI:
    """Crea la app en local"""
    if not secretWH:
        raise ValueError('La variable WebhookSecret es necesaria')
    app = FastAPI(title='API_SP500', version="0.0.1")

    store = DataStore(dataDir)
    store.load()

    app = FastAPI(title='API_SP500', version="0.1.0")

    def require_data() -> None:
        if not store.loaded:
            raise HTTPException(503, 'Datos no disponibles: ejecuta antes sp500_yahoo.py')

    def find_company(ticker: str) -> dict:
        require_data()
        row = store.companies.get(ticker.upper())
        if row is None:
            raise HTTPException(404, 'Empresa no encontrada')
        return row
    
    @app.get("/health", tags=['sistema'])
    def health():
        return {"status": "ok", "data_loaded": store.loaded}

    @app.post('/verificacion', status_code=202)
    async def receive(request: Request) -> dict: #Al pedir directamente el request no se muestra la información a rellenar en docs
        """Comprueba tamaño, la calve WEBHOOK_SECRET y valida el cuerpo de la petición"""
        
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > 65536:
            raise HTTPException(413, 'Payload too large')

        bodyRaw = await request.body()
        
        if len(bodyRaw) > 65536:
            raise HTTPException(413, 'Payload too large')

        secret_recibido = request.headers.get('x-signature', '')    
        if not valid_signature(bodyRaw, secret_recibido, secretWH):
            raise HTTPException(403, 'Firma Invalida')
        try:
            data_salida = ValidacionBase.model_validate_json(bodyRaw)
        except ValidationError:
            raise HTTPException(422, 'Esquema de la petición invalido')
        return {'accepted': True, 'output': data_salida.model_dump()}

    @app.get('/v1/companies', response_model=list[Company], tags=['empresas'])
    def list_companies(
        sector: Annotated[str | None, Query(max_length=60)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Company]:
        """Lista las empresas, con filtro por sector y paginación."""
        require_data()
        rows = list(store.companies.values())
        if sector:
            rows = [r for r in rows if (r.get('sector') or '').lower() == sector.lower()]
        return [to_company(r) for r in rows[offset:offset + limit]]

    @app.get('/v1/companies/{ticker}', response_model=Company, tags=['empresas'],
             responses={404: {'description': 'Empresa no encontrada'}})
    def get_company(ticker: Ticker) -> Company:
        """Datos de una empresa."""
        return to_company(find_company(ticker))

    @app.get('/v1/sectors', response_model=list[Sector], tags=['empresas'])
    def list_sectors() -> list[Sector]:
        """Sectores y número de empresas de cada uno."""
        require_data()
        counts: dict[str, int] = {}
        for r in store.companies.values():
            if r.get('sector'):
                counts[r['sector']] = counts.get(r['sector'], 0) + 1
        return [Sector(sector=s, companies=n) for s, n in sorted(counts.items())]

    @app.get('/v1/companies/{ticker}/prices', response_model=PriceSeries, tags=['precios'],
             responses={404: {'description': 'Empresa no encontrada'}})
    def get_prices(
        ticker: Ticker,
        start: Annotated[date | None, Query(description='Desde (AAAA-MM-DD)')] = None,
        end: Annotated[date | None, Query(description='Hasta (AAAA-MM-DD)')] = None,
        limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    ) -> PriceSeries:
        """Precios diarios de una empresa. Si hay más de `limit`, devuelve los más recientes."""
        if start and end and start > end:
            raise HTTPException(422, 'start no puede ser posterior a end')
        find_company(ticker)

        df = store.prices.get(ticker.upper(), pd.DataFrame(columns=['Date']))
        if start:
            df = df[df['Date'] >= pd.Timestamp(start)]
        if end:
            df = df[df['Date'] <= pd.Timestamp(end)]
        df = df.tail(limit)

        prices = [
            PricePoint(
                date=r.Date.date(), open=nan_to_none(r.Open), high=nan_to_none(r.High),
                low=nan_to_none(r.Low), close=r.Close,
                volume=None if pd.isna(r.Volume) else int(r.Volume),
            )
            for r in df.itertuples()
        ]
        return PriceSeries(ticker=ticker.upper(), count=len(prices), prices=prices)
    
    return app
    

def create_from_env() -> FastAPI:
    """Requiere la variable de entorno "WEBHOOK_SECRET" para iniciar si no falla"""
    secretWH = os.environ.get('WEBHOOK_SECRET')
    if not secretWH:
        raise RuntimeError('Asigna WEBHOOK_SECRET antes de iniciar la app')
    return create_app(DATA, secretWH.encode())

app = create_from_env()