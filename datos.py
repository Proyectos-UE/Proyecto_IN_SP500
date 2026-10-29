"""Carga de los datos publicados (los CSV que genera sp500_yahoo.py)."""

from pathlib import Path

import pandas as pd

PRICES_FILE = "sp500_precios.csv"
FUNDAMENTALS_FILE = "sp500_fundamentales.csv"


class DataStore:
    """Guarda en memoria la versión publicada de los datos."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.companies: dict[str, dict] = {}        # ticker -> fila de fundamentales
        self.prices: dict[str, pd.DataFrame] = {}   # ticker -> precios ordenados por fecha
        self.loaded = False

    def load(self) -> None:
        """Lee los CSV. Si falta alguno, la API arranca pero responde 503 en los datos."""
        fundamentals = self.data_dir / FUNDAMENTALS_FILE
        prices = self.data_dir / PRICES_FILE
        if not fundamentals.exists() or not prices.exists():
            self.loaded = False
            return

        df = pd.read_csv(fundamentals)
        df = df.astype(object).where(df.notna(), None)          # NaN -> None (null en JSON)
        self.companies = {row["Ticker"]: row for row in df.to_dict("records")}

        p = pd.read_csv(prices, parse_dates=["Date"])
        p = p.dropna(subset=["Close"])                            # sin precio de cierre no sirve
        self.prices = {t: g.sort_values("Date") for t, g in p.groupby("Ticker")}
        self.loaded = True