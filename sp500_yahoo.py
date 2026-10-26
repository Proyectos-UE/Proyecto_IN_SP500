"""
Descarga y actualiza datos del S&P 500 desde Yahoo Finance (yfinance):
  - Precios diarios de todas las empresas  -> sp500_precios.csv
  - Datos fundamentales (yf.Ticker().info) -> sp500_fundamentales.csv

Está configurado de forma MUY conservadora para no llegar al límite de Yahoo:
tarda más, pero es reanudable. Si Yahoo bloquea, el script guarda lo que lleva
y se detiene; al volver a ejecutarlo continúa donde se quedó.

Instalación:  pip install yfinance pandas
Uso:          python sp500_yahoo.py               # precios + fundamentales
              python sp500_yahoo.py precios
              python sp500_yahoo.py fundamentales
"""
import argparse
import os
import time
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:  # versiones antiguas de yfinance
    class YFRateLimitError(Exception):
        pass

# ----------------------------- CONFIGURACIÓN ------------------------------
TICKERS_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
PRICES_FILE = "./data/sp500_precios.csv"
FUNDAMENTALS_FILE = "./data/sp500_fundamentales.csv"
START_DATE = "2015-01-01"        # fecha inicial en la primera ejecución

# Precios (una petición por lote)
PRICE_BATCH_SIZE = 20            # tickers por lote
PRICE_SLEEP = 8                  # segundos de pausa entre lotes

# Fundamentales (una petición por ticker: es lo que más riesgo de bloqueo tiene)
INFO_SLEEP = 3                   # segundos de pausa entre tickers
INFO_BATCH_SIZE = 25             # cada cuántos tickers se hace una pausa larga
INFO_BATCH_PAUSE = 90            # segundos de la pausa larga (y se guarda progreso)
FUNDAMENTALS_MAX_AGE_DAYS = 7    # no vuelve a pedir un ticker descargado hace menos de X días

# Reintentos y protección
MAX_RETRIES = 3                  # reintentos ante errores normales
RETRY_BACKOFF = 15               # segundos base (15, 30, 60...)
RATE_LIMIT_COOLDOWN = 600        # segundos de espera si Yahoo dice "demasiadas peticiones"
MAX_CONSECUTIVE_FAILURES = 5     # fallos seguidos antes de parar (probable bloqueo)

INFO_FIELDS = [
    "shortName", "longName", "sector", "industry", "country", "website",
    "fullTimeEmployees", "currentPrice", "previousClose", "marketCap",
    "enterpriseValue", "sharesOutstanding", "averageVolume",
    "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "beta",
    "trailingPE", "forwardPE", "priceToBook", "priceToSalesTrailing12Months",
    "enterpriseToEbitda", "trailingEps", "forwardEps",
    "dividendYield", "dividendRate", "payoutRatio",
    "totalRevenue", "revenueGrowth", "ebitda", "grossMargins",
    "operatingMargins", "profitMargins", "returnOnEquity", "returnOnAssets",
    "debtToEquity", "currentRatio", "freeCashflow",
    "recommendationKey", "targetMeanPrice", "numberOfAnalystOpinions",
]


class StopRun(Exception):
    """Se detiene la descarga (posible bloqueo); el progreso ya está guardado."""


def is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return (isinstance(e, YFRateLimitError) or "too many requests" in msg
            or "rate limit" in msg or "429" in msg)


def get_tickers() -> list[str]:
    """Lista actual del S&P 500 desde Wikipedia. Yahoo usa '-' en lugar de '.' (BRK.B -> BRK-B)."""
    # Wikipedia devuelve 403 sin User-Agent, por eso se usa requests en vez de pd.read_csv(url)
    html = requests.get(TICKERS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    df = pd.read_html(StringIO(html))[0]
    return df["Symbol"].str.replace(".", "-", regex=False).tolist()


# ------------------------------- PRECIOS ----------------------------------
def download_batch(batch: list[str], start: pd.Timestamp) -> pd.DataFrame:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = yf.download(
                batch, start=start.strftime("%Y-%m-%d"), auto_adjust=True,
                group_by="ticker", threads=False, progress=False,
            )
            break
        except Exception as e:
            if is_rate_limit(e):
                print(f"  Límite de Yahoo detectado. Esperando {RATE_LIMIT_COOLDOWN}s...")
                time.sleep(RATE_LIMIT_COOLDOWN)
            else:
                wait = RETRY_BACKOFF * 2 ** (attempt - 1)
                print(f"  Error ({e}). Reintento {attempt}/{MAX_RETRIES} en {wait}s")
                time.sleep(wait)
    else:
        raise StopRun("El lote de precios falló tras varios reintentos.")

    if data is None or data.empty:
        return pd.DataFrame()
    if not isinstance(data.columns, pd.MultiIndex):  # un solo ticker
        data.columns = pd.MultiIndex.from_product([[batch[0]], data.columns])

    frames = []
    for t in batch:
        if t not in data.columns.get_level_values(0):
            continue
        sub = data[t].dropna(how="all").copy()
        if not sub.empty:
            sub["Ticker"] = t
            frames.append(sub.reset_index())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def update_prices(tickers: list[str]) -> None:
    old, last = None, {}
    if os.path.exists(PRICES_FILE):
        old = pd.read_csv(PRICES_FILE, parse_dates=["Date"])
        last = old.groupby("Ticker")["Date"].max().to_dict()
    today = pd.Timestamp.today().normalize()
    default_start = pd.Timestamp(START_DATE)

    def next_day(t):
        return last[t] + timedelta(days=1) if t in last else default_start

    parts = []
    try:
        for i in range(0, len(tickers), PRICE_BATCH_SIZE):
            batch = tickers[i:i + PRICE_BATCH_SIZE]
            start = min(next_day(t) for t in batch)  # cada lote parte de su fecha más antigua
            n = i // PRICE_BATCH_SIZE + 1
            total = -(-len(tickers) // PRICE_BATCH_SIZE)
            if start > today:
                print(f"Lote {n}/{total}: ya está al día")
                continue
            print(f"Lote {n}/{total}: {len(batch)} tickers desde {start.date()}")
            df = download_batch(batch, start)
            if df.empty:
                print("  Sin datos nuevos en este lote")
            else:
                parts.append(df)
            time.sleep(PRICE_SLEEP)
    except StopRun as e:
        print(f"\nDetenido: {e}\nSe guarda lo descargado; vuelve a ejecutar más tarde para continuar.")
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario. Se guarda lo descargado.")

    if not parts:
        print("No hay datos nuevos de precios.")
        return
    new = pd.concat(parts, ignore_index=True)
    if old is not None:
        new = pd.concat([old, new], ignore_index=True)
    new = (new.drop_duplicates(subset=["Date", "Ticker"], keep="last")
              .sort_values(["Ticker", "Date"]))
    new.to_csv(PRICES_FILE, index=False)
    print(f"Guardado {PRICES_FILE}: {len(new):,} filas, {new['Ticker'].nunique()} tickers")


# ---------------------------- FUNDAMENTALES -------------------------------
def fetch_info(ticker: str) -> dict | None:
    rate_limit_hits = 0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            info = yf.Ticker(ticker).info
            if not info or len(info) <= 1:
                raise ValueError("respuesta vacía")
            return info
        except Exception as e:
            if is_rate_limit(e):
                rate_limit_hits += 1
                if rate_limit_hits > 1:  # segundo bloqueo: mejor parar y reintentar otro día
                    raise StopRun("Yahoo sigue limitando las peticiones.")
                print(f"  Límite de Yahoo detectado. Esperando {RATE_LIMIT_COOLDOWN}s...")
                time.sleep(RATE_LIMIT_COOLDOWN)
            else:
                wait = RETRY_BACKOFF * 2 ** (attempt - 1)
                print(f"  {ticker}: error ({e}). Reintento {attempt}/{MAX_RETRIES} en {wait}s")
                time.sleep(wait)
    return None


def save_fundamentals(old: pd.DataFrame, rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    df = df.drop_duplicates(subset="Ticker", keep="last").sort_values("Ticker")
    cols = ["Ticker", "FechaDescarga"] + INFO_FIELDS
    df[cols].to_csv(FUNDAMENTALS_FILE, index=False)


def update_fundamentals(tickers: list[str]) -> None:
    old = pd.DataFrame(columns=["Ticker", "FechaDescarga"] + INFO_FIELDS)
    pending = tickers
    if os.path.exists(FUNDAMENTALS_FILE):
        old = pd.read_csv(FUNDAMENTALS_FILE)
        limit = datetime.now() - timedelta(days=FUNDAMENTALS_MAX_AGE_DAYS)
        fresh = old.loc[pd.to_datetime(old["FechaDescarga"]) >= limit, "Ticker"]
        pending = [t for t in tickers if t not in set(fresh)]

    print(f"Fundamentales: {len(pending)} tickers pendientes de {len(tickers)}")
    if not pending:
        print("Todo está actualizado (menos de "
              f"{FUNDAMENTALS_MAX_AGE_DAYS} días).")
        return
    est = (len(pending) * INFO_SLEEP + (len(pending) // INFO_BATCH_SIZE) * INFO_BATCH_PAUSE) / 60
    print(f"Tiempo estimado: ~{est:.0f} minutos")

    rows, failed, consecutive = [], [], 0
    try:
        for i, t in enumerate(pending, 1):
            info = fetch_info(t)
            if info is None:
                failed.append(t)
                consecutive += 1
                print(f"[{i}/{len(pending)}] {t}: sin datos")
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    raise StopRun(f"{consecutive} fallos seguidos (posible bloqueo).")
            else:
                consecutive = 0
                row = {c: info.get(c) for c in INFO_FIELDS}
                row["Ticker"] = t
                row["FechaDescarga"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                rows.append(row)
                print(f"[{i}/{len(pending)}] {t}: OK")
            time.sleep(INFO_SLEEP)
            if i % INFO_BATCH_SIZE == 0 and i < len(pending):
                save_fundamentals(old, rows)  # guarda progreso
                print(f"Pausa de {INFO_BATCH_PAUSE}s (progreso guardado)...")
                time.sleep(INFO_BATCH_PAUSE)
    except StopRun as e:
        print(f"\nDetenido: {e}\nVuelve a ejecutar más tarde: continuará donde se quedó.")
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario. Se guarda el progreso.")
    finally:
        save_fundamentals(old, rows)
        print(f"Guardado {FUNDAMENTALS_FILE}: {len(rows)} tickers nuevos en esta ejecución")
        if failed:
            print(f"Sin datos ({len(failed)}): {', '.join(failed)}")


# --------------------------------- MAIN -----------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("modo", nargs="?", default="todo",
                        choices=["todo", "precios", "fundamentales"])
    args = parser.parse_args()

    tickers = get_tickers()
    if args.modo in ("todo", "precios"):
        update_prices(tickers)
    if args.modo in ("todo", "fundamentales"):
        update_fundamentals(tickers)


if __name__ == "__main__":
    main()
