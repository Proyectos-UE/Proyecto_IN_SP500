"""Configuración común de los tests.

Los tests NO usan los CSV reales ni el .env: crean datos pequeños de ejemplo
en una carpeta temporal, así siempre sabemos qué resultado esperar.
"""
import os

# app.py crea la app al importarse y exige WEBHOOK_SECRET: se define ANTES de importarlo
os.environ.setdefault("WEBHOOK_SECRET", "secreto-de-prueba")

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import create_app

SECRET = b"secreto-de-prueba"
ORIGEN = {"x-origen": "dispositivo-test"}

@pytest.fixture
def data_dir(tmp_path):
    """Carpeta con 3 empresas y unos días de precios."""
    pd.DataFrame([
        {"Ticker": "AAPL", "FechaDescarga": "2026-10-29 10:00:00", "shortName": "Apple",
         "longName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
         "country": "United States", "marketCap": 3.5e12, "currentPrice": 230.0,
         "trailingPE": 35.0, "dividendYield": 0.4},
        {"Ticker": "MSFT", "FechaDescarga": "2026-10-29 10:00:00", "shortName": "Microsoft",
         "longName": "Microsoft Corporation", "sector": "Technology", "industry": "Software",
         "country": "United States", "marketCap": 3.1e12, "currentPrice": 410.0,
         "trailingPE": 33.0, "dividendYield": 0.8},
        {"Ticker": "BRK-B", "FechaDescarga": "2026-10-29 10:00:00", "shortName": "Berkshire",
         "longName": None, "sector": "Financial Services", "industry": "Insurance",
         "country": "United States", "marketCap": 9e11, "currentPrice": 450.0,
         "trailingPE": None, "dividendYield": None},
    ]).to_csv(tmp_path / "sp500_fundamentales.csv", index=False)

    rows = [
        {"Date": d, "Open": 100.0, "High": 110.0, "Low": 95.0, "Close": 105.0, "Volume": 1000, "Ticker": t}
        for t in ("AAPL", "MSFT")
        for d in pd.date_range("2026-10-01", "2026-10-10").strftime("%Y-%m-%d")
    ]
    # Un día sin precio de cierre: la carga debe descartarlo
    rows.append({"Date": "2026-10-11", "Open": None, "High": None, "Low": None,
                 "Close": None, "Volume": None, "Ticker": "AAPL"})
    pd.DataFrame(rows).to_csv(tmp_path / "sp500_precios.csv", index=False)
    return tmp_path


@pytest.fixture
def client(data_dir):
    """Cliente de la API con los datos de ejemplo cargados."""
    return TestClient(create_app(data_dir, SECRET), headers=ORIGEN)


@pytest.fixture
def client_sin_datos(tmp_path):
    """Cliente de la API sin CSV (como si no se hubiera ejecutado la ingesta)."""
    return TestClient(create_app(tmp_path, SECRET), headers=ORIGEN)