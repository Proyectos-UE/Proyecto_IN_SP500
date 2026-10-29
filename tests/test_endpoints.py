"""Pruebas de los endpoints: casos correctos, inválidos y de acceso no autorizado."""
import hashlib
import hmac
import json

import pytest

from conftest import SECRET


# ---------------------------------------------------------------------------
# Casos correctos
# ---------------------------------------------------------------------------
def test_health_indica_datos_cargados(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "data_loaded": True}


def test_listar_empresas(client):
    response = client.get("/v1/companies")
    assert response.status_code == 200
    assert [c["ticker"] for c in response.json()] == ["AAPL", "MSFT", "BRK-B"]


def test_filtrar_por_sector_y_paginar(client):
    response = client.get("/v1/companies", params={"sector": "technology", "limit": 1, "offset": 1})
    assert response.status_code == 200
    assert [c["ticker"] for c in response.json()] == ["MSFT"]


def test_obtener_empresa_acepta_minusculas(client):
    response = client.get("/v1/companies/aapl")
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."          # columnas de Yahoo traducidas a nuestro modelo
    assert body["market_cap"] == 3.5e12


def test_valores_vacios_se_devuelven_como_null(client):
    body = client.get("/v1/companies/BRK-B").json()
    assert body["name"] == "Berkshire"           # sin longName se usa shortName
    assert body["trailing_pe"] is None
    assert body["dividend_yield"] is None


def test_precios_en_rango(client):
    response = client.get("/v1/companies/AAPL/prices", params={"start": "2026-10-08", "end": "2026-10-09"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert [p["date"] for p in body["prices"]] == ["2026-10-08", "2026-10-09"]


def test_precios_descarta_dias_sin_cierre(client):
    body = client.get("/v1/companies/AAPL/prices").json()
    assert body["count"] == 10                    # el 2026-10-11 no tiene Close
    assert body["prices"][-1]["date"] == "2026-10-10"


def test_precios_limit_devuelve_los_mas_recientes(client):
    body = client.get("/v1/companies/AAPL/prices", params={"limit": 3}).json()
    assert [p["date"] for p in body["prices"]] == ["2026-10-08", "2026-10-09", "2026-10-10"]


def test_empresa_sin_precios_devuelve_lista_vacia(client):
    body = client.get("/v1/companies/BRK-B/prices").json()
    assert body == {"ticker": "BRK-B", "count": 0, "prices": []}


def test_sectores(client):
    response = client.get("/v1/sectors")
    assert response.status_code == 200
    assert response.json() == [
        {"sector": "Financial Services", "companies": 1},
        {"sector": "Technology", "companies": 2},
    ]


# ---------------------------------------------------------------------------
# Casos inválidos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"sector": "x" * 61}])
def test_parametros_de_listado_invalidos(client, params):
    assert client.get("/v1/companies", params=params).status_code == 422


@pytest.mark.parametrize("ticker", ["AA$PL", "DEMASIADOLARGO"])
def test_ticker_con_formato_invalido(client, ticker):
    assert client.get(f"/v1/companies/{ticker}").status_code == 422


def test_empresa_inexistente(client):
    response = client.get("/v1/companies/ZZZZ")
    assert response.status_code == 404
    assert response.json() == {"detail": "Empresa no encontrada"}


def test_precios_de_empresa_inexistente(client):
    assert client.get("/v1/companies/ZZZZ/prices").status_code == 404


@pytest.mark.parametrize("params", [{"start": "hola"}, {"end": "2026-13-01"}, {"limit": 0}, {"limit": 5001}])
def test_parametros_de_precios_invalidos(client, params):
    assert client.get("/v1/companies/AAPL/prices", params=params).status_code == 422


def test_rango_de_fechas_invertido(client):
    response = client.get("/v1/companies/AAPL/prices", params={"start": "2026-10-09", "end": "2026-10-01"})
    assert response.status_code == 422
    assert response.json() == {"detail": "start no puede ser posterior a end"}


@pytest.mark.parametrize("url", ["/v1/companies", "/v1/companies/AAPL", "/v1/companies/AAPL/prices", "/v1/sectors"])
def test_sin_datos_responde_503(client_sin_datos, url):
    response = client_sin_datos.get(url)
    assert response.status_code == 503
    assert client_sin_datos.get("/health").json()["data_loaded"] is False


# ---------------------------------------------------------------------------
# Webhook: acceso autorizado y no autorizado
# ---------------------------------------------------------------------------
def firmar(body: bytes, secret: bytes = SECRET) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


EVENTO = json.dumps({"event_id": "evt-001", "event_type": "verification.simple"}).encode()


def test_webhook_con_firma_correcta(client):
    headers = {"x-signature": firmar(EVENTO), "x-origen": "sensor-01"}
    response = client.post("/verificacion", content=EVENTO, headers=headers)
    assert response.status_code == 202
    assert response.json()["accepted"] is True

def test_webhook_sin_firma_ni_origen_responde_403(client):
    client.headers.pop("x-origen", None)          # la firma se comprueba antes que x-origen
    assert client.post("/verificacion", content=EVENTO).status_code == 403

def test_webhook_sin_firma(client):
    assert client.post("/verificacion", content=EVENTO).status_code == 403


def test_webhook_con_firma_de_otro_secreto(client):
    headers = {"x-signature": firmar(EVENTO, b"otro-secreto")}
    assert client.post("/verificacion", content=EVENTO, headers=headers).status_code == 403


def test_webhook_cuerpo_modificado_tras_firmar(client):
    alterado = EVENTO.replace(b"evt-001", b"evt-999")
    headers = {"x-signature": firmar(EVENTO)}     # firma del cuerpo original
    assert client.post("/verificacion", content=alterado, headers=headers).status_code == 403


@pytest.mark.parametrize("origen", [None, "", "   ", "x" * 101])
def test_webhook_origen_ausente_o_invalido(client, origen):
    client.headers.pop("x-origen", None) 
    headers = {"x-signature": firmar(EVENTO)}
    if origen is not None:
        headers["x-origen"] = origen
    assert client.post("/verificacion", content=EVENTO, headers=headers).status_code == 422


def test_webhook_esquema_invalido(client):
    body = json.dumps({"event_id": "evt-001", "event_type": "otro.tipo"}).encode()
    headers = {"x-signature": firmar(body), "x-origen": "sensor-01"}
    assert client.post("/verificacion", content=body, headers=headers).status_code == 422


def test_webhook_demasiado_grande(client):
    body = b"x" * 70_000
    assert client.post("/verificacion", content=body, headers={"x-signature": firmar(body)}).status_code == 413
