import hashlib
import hmac
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Annotated

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi import Path as PathParam, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from datos import DataStore
from inbox import EventConflict, Inbox
from models import Company, Evento, PricePoint, PriceSeries, Sector, ValidacionBase

load_dotenv()

DATA = Path(__file__).parent / 'data'

# Ticker válido: letras, números, punto o guion (AAPL, BRK-B), de 1 a 10 caracteres
Ticker = Annotated[str, PathParam(pattern=r'^[A-Za-z0-9.\-]{1,10}$', description='Símbolo, p. ej. AAPL')]

def valid_signature(body: bytes, received: str, secretWH: bytes) -> bool:
    """Verifica la firma en forma de cadena de Bytes."""
    expected = 'sha256=' + hmac.new(secretWH, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)

# Declarada como Header para que aparezca como campo rellenable en /docs
XOrigen = Annotated[str | None, Header(description='Dispositivo que envía la petición (obligatoria, 1 a 100 caracteres)')]


def comprobar_origen(valor: str | None) -> str:
    """Devuelve el origen sin espacios o responde 422 si falta o no es válido."""
    origen = (valor or '').strip()
    if not 1 <= len(origen) <= 100:
        raise HTTPException(422, 'Cabecera x-origen obligatoria (1 a 100 caracteres)')
    return origen


def exigir_origen(x_origen: XOrigen = None) -> str:
    """Dependencia de los GET: lee la cabecera x-origen (FastAPI la muestra en /docs)."""
    return comprobar_origen(x_origen)


# Se declara como parámetro de los endpoints GET: origen: OrigenHeader
OrigenHeader = Annotated[str, Depends(exigir_origen)]


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

def create_app(dataDir: Path, secretWH: bytes, inboxPath: Path | None = None) -> FastAPI:
    """Crea la app. Los eventos recibidos se guardan en inboxPath (por defecto dataDir/inbox.db)."""
    if not secretWH:
        raise ValueError('La variable WebhookSecret es necesaria')

    store = DataStore(dataDir)
    store.load()
    inbox = Inbox(inboxPath or dataDir / 'inbox.db')

    app = FastAPI(title='API_SP500', version="0.1.0")

    def guardar_llamada(request: Request, origen: str) -> None:
        """Guarda en la bandeja que ha llegado esta llamada: (origen, id generado, 'MÉTODO /ruta')."""
        evento = Evento(origen=origen, event_id=os.urandom(16).hex(),
                        event_type=f'{request.method} {request.url.path}'[:100])
        try:
            inbox.store(evento, 'recibido')
        except sqlite3.Error:
            raise HTTPException(503, 'No se pudo guardar el evento')

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

    #Al pedir directamente el request no se muestra la información a rellenar en docs
    async def validacionesBase(request: Request, x_origen: XOrigen = None) -> dict: 
        """Comprueba tamaño, firma (WEBHOOK_SECRET), cabecera x-origen y valida el cuerpo de la petición"""
        
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > 65536:
            raise HTTPException(413, 'Payload too large')

        bodyRaw = await request.body()
        
        if len(bodyRaw) > 65536:
            raise HTTPException(413, 'Payload too large')

        secret_recibido = request.headers.get('x-signature', '')    
        if not valid_signature(bodyRaw, secret_recibido, secretWH):
            raise HTTPException(403, 'Firma Invalida')

        # Dispositivo que envía el evento: junto con event_id forma la clave del evento
        origen = comprobar_origen(x_origen)

        try:
            data_salida = ValidacionBase.model_validate_json(bodyRaw)
        except ValidationError:
            raise HTTPException(422, 'Esquema de la petición invalido')

        return {'accepted': True, 'origen': origen, 'output': data_salida.model_dump()}

    
    @app.post('/verificacion', status_code=202, tags=['webhook'])
    async def verificacion(data_salida: dict = Depends(validacionesBase)) -> dict:
        """Valida el evento, lo guarda en la bandeja y solo entonces confirma (202).

        La clave del evento es (cabecera x-origen, event_id). Un reenvío idéntico
        devuelve status='duplicado' sin guardarlo otra vez.
        """
        evento = Evento(origen=data_salida['origen'], **data_salida['output'])
        try:
            estado = await run_in_threadpool(inbox.store, evento)
        except EventConflict:
            raise HTTPException(409, 'event_id reutilizado con contenido distinto')
        except sqlite3.Error:
            # Si no se pudo guardar no se confirma: el emisor reintentará
            raise HTTPException(503, 'No se pudo guardar el evento')
        return {**data_salida, 'status': estado}

    @app.get('/v1/companies', response_model=list[Company], tags=['empresas'])
    def list_companies(
        request: Request,
        origen: OrigenHeader,
        sector: Annotated[str | None, Query(max_length=60)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Company]:
        """Lista las empresas, con filtro por sector y paginación."""
        guardar_llamada(request, origen)
        require_data()
        rows = list(store.companies.values())
        if sector:
            rows = [r for r in rows if (r.get('sector') or '').lower() == sector.lower()]
        return [to_company(r) for r in rows[offset:offset + limit]]

    @app.get('/v1/companies/{ticker}', response_model=Company, tags=['empresas'],
             responses={404: {'description': 'Empresa no encontrada'}})
    def get_company(request: Request, origen: OrigenHeader, ticker: Ticker) -> Company:
        """Datos de una empresa."""
        guardar_llamada(request, origen)
        return to_company(find_company(ticker))

    @app.get('/v1/sectors', response_model=list[Sector], tags=['empresas'])
    def list_sectors(request: Request, origen: OrigenHeader) -> list[Sector]:
        """Sectores y número de empresas de cada uno."""
        guardar_llamada(request, origen)
        require_data()
        counts: dict[str, int] = {}
        for r in store.companies.values():
            if r.get('sector'):
                counts[r['sector']] = counts.get(r['sector'], 0) + 1
        return [Sector(sector=s, companies=n) for s, n in sorted(counts.items())]

    @app.get('/v1/companies/{ticker}/prices', response_model=PriceSeries, tags=['precios'],
             responses={404: {'description': 'Empresa no encontrada'}})
    def get_prices(
        request: Request,
        origen: OrigenHeader,
        ticker: Ticker,
        start: Annotated[date | None, Query(description='Desde (AAAA-MM-DD)')] = None,
        end: Annotated[date | None, Query(description='Hasta (AAAA-MM-DD)')] = None,
        limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    ) -> PriceSeries:
        """Precios diarios de una empresa. Si hay más de `limit`, devuelve los más recientes."""
        guardar_llamada(request, origen)
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