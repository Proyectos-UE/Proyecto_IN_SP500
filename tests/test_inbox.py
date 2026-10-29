import json
import sqlite3

import pytest

from inbox import EventConflict, Inbox
from models import Evento
from test_endpoints import EVENTO, firmar


def contar(db_path) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    finally:
        con.close()


def filas(db_path):
    """(origen, event_type, resultado) de todo lo guardado, en orden de inserción."""
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT origen, event_type, resultado FROM eventos ORDER BY rowid").fetchall()
    finally:
        con.close()


def enviar(client, body=EVENTO, origen="sensor-01"):
    headers = {"x-signature": firmar(body), "x-origen": origen}
    return client.post("/verificacion", content=body, headers=headers)


# ---------------------------------------------------------------------------
# Webhook /verificacion
# ---------------------------------------------------------------------------
def test_evento_valido_se_guarda(client, data_dir):
    response = enviar(client)
    assert response.status_code == 202
    assert response.json()["status"] == "guardado"
    assert contar(data_dir / "inbox.db") == 1


def test_se_guarda_origen_id_y_tipo_del_evento(client, data_dir):
    enviar(client, origen="sensor-07")
    con = sqlite3.connect(data_dir / "inbox.db")
    try:
        assert con.execute("SELECT origen, event_id, event_type, resultado FROM eventos").fetchall() == [
            ("sensor-07", "evt-001", "verification.simple", "aceptado")]
    finally:
        con.close()


def test_reenvio_identico_es_duplicado_y_no_se_guarda_dos_veces(client, data_dir):
    enviar(client)
    response = enviar(client)
    assert response.status_code == 202
    assert response.json()["status"] == "duplicado"
    assert contar(data_dir / "inbox.db") == 1


def test_evento_distinto_se_guarda_aparte(client, data_dir):
    enviar(client)
    otro = json.dumps({"event_id": "evt-002", "event_type": "verification.simple"}).encode()
    assert enviar(client, otro).json()["status"] == "guardado"
    assert contar(data_dir / "inbox.db") == 2


def test_mismo_event_id_de_otro_dispositivo_es_otro_evento(client, data_dir):
    assert enviar(client, origen="sensor-01").json()["status"] == "guardado"
    assert enviar(client, origen="sensor-02").json()["status"] == "guardado"
    assert enviar(client, origen="sensor-02").json()["status"] == "duplicado"
    assert contar(data_dir / "inbox.db") == 2


def test_webhook_rechazado_no_guarda_nada(client, data_dir):
    bad_firma = client.post("/verificacion", content=EVENTO,
                            headers={"x-signature": "sha256=falsa", "x-origen": "sensor-09"})
    assert bad_firma.status_code == 403
    cuerpo = json.dumps({"event_id": "evt-001", "event_type": "otro.tipo"}).encode()
    assert enviar(client, cuerpo).status_code == 422
    client.headers.pop("x-origen", None)
    sin_origen = client.post("/verificacion", content=EVENTO, headers={"x-signature": firmar(EVENTO)})
    assert sin_origen.status_code == 422
    assert contar(data_dir / "inbox.db") == 0


# ---------------------------------------------------------------------------
# Endpoints GET
# ---------------------------------------------------------------------------
def test_get_se_guarda_con_origen_metodo_y_ruta(client, data_dir):
    assert client.get("/v1/sectors", headers={"x-origen": "sensor-01"}).status_code == 200
    assert filas(data_dir / "inbox.db") == [("sensor-01", "GET /v1/sectors", "recibido")]


@pytest.mark.parametrize("url", ["/v1/companies", "/v1/companies/AAPL", "/v1/companies/AAPL/prices", "/v1/sectors"])
def test_cada_get_guarda_su_llamada(client, data_dir, url):
    assert client.get(url).status_code == 200
    assert filas(data_dir / "inbox.db") == [("dispositivo-test", f"GET {url}", "recibido")]


def test_cada_llamada_repetida_es_un_evento_distinto(client, data_dir):
    client.get("/v1/sectors")
    client.get("/v1/sectors")
    assert contar(data_dir / "inbox.db") == 2


@pytest.mark.parametrize("url", ["/v1/companies", "/v1/companies/AAPL", "/v1/companies/AAPL/prices", "/v1/sectors"])
def test_get_sin_origen_responde_422_y_no_se_guarda(client, data_dir, url):
    client.headers.pop("x-origen", None)
    response = client.get(url)
    assert response.status_code == 422
    assert "x-origen" in response.json()["detail"]
    assert contar(data_dir / "inbox.db") == 0


@pytest.mark.parametrize("origen", ["", "   ", "x" * 101])
def test_get_con_origen_invalido_responde_422(client, data_dir, origen):
    assert client.get("/v1/sectors", headers={"x-origen": origen}).status_code == 422
    assert contar(data_dir / "inbox.db") == 0


def test_health_no_exige_origen_ni_se_guarda(client, data_dir):
    client.headers.pop("x-origen", None)
    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"x-origen": "sensor-01"}).status_code == 200
    assert contar(data_dir / "inbox.db") == 0


def test_get_de_empresa_inexistente_se_guarda_aunque_responda_404(client, data_dir):
    assert client.get("/v1/companies/ZZZZ").status_code == 404
    assert filas(data_dir / "inbox.db") == [("dispositivo-test", "GET /v1/companies/ZZZZ", "recibido")]


@pytest.mark.parametrize("url", ["/v1/companies?limit=0", "/v1/companies/AA$PL"])
def test_get_con_parametros_invalidos_no_llega_al_endpoint_ni_se_guarda(client, data_dir, url):
    assert client.get(url).status_code == 422
    assert contar(data_dir / "inbox.db") == 0


def test_sin_datos_tambien_se_guarda_la_llamada(client_sin_datos, tmp_path):
    assert client_sin_datos.get("/v1/sectors").status_code == 503
    assert filas(tmp_path / "inbox.db") == [("dispositivo-test", "GET /v1/sectors", "recibido")]


def test_ruta_inexistente_y_documentacion_no_se_guardan(client, data_dir):
    assert client.get("/no-existe").status_code == 404
    client.get("/docs")
    client.get("/openapi.json")
    assert contar(data_dir / "inbox.db") == 0


def test_si_no_se_puede_guardar_el_get_responde_503(client, monkeypatch):
    def falla(self, evento, resultado="aceptado"):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(Inbox, "store", falla)
    response = client.get("/v1/sectors")
    assert response.status_code == 503
    assert response.json() == {"detail": "No se pudo guardar el evento"}


# ---------------------------------------------------------------------------
# Inbox directamente
# ---------------------------------------------------------------------------
@pytest.fixture
def inbox(tmp_path):
    return Inbox(tmp_path / "sub" / "inbox.db")      # crea la carpeta si no existe


def evento(**kw) -> Evento:
    base = {"event_id": "a", "event_type": "tipo.x", "origen": "origen1"}
    return Evento(**{**base, **kw})


def test_inbox_guarda_y_detecta_duplicado(inbox):
    assert inbox.store(evento()) == "guardado"
    assert inbox.store(evento()) == "duplicado"


def test_inbox_mismo_id_con_contenido_distinto_es_conflicto(inbox):
    inbox.store(evento())
    with pytest.raises(EventConflict):
        inbox.store(evento(event_type="tipo.y"))


def test_inbox_mismo_id_en_otro_origen_es_otro_evento(inbox):
    inbox.store(evento())
    assert inbox.store(evento(origen="origen2")) == "guardado"


def test_inbox_conserva_los_datos_tras_reabrir(inbox):
    inbox.store(evento())
    reabierta = Inbox(inbox.path)
    assert reabierta.store(evento()) == "duplicado"
