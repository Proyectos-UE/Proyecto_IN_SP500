"""Pruebas del guardado de eventos (bandeja SQLite) y su uso desde /verificacion."""
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


def enviar(client, body=EVENTO, origen="sensor-01"):
    headers = {"x-signature": firmar(body), "x-origen": origen}
    return client.post("/verificacion", content=body, headers=headers)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
def test_evento_valido_se_guarda(client, data_dir):
    response = enviar(client)
    assert response.status_code == 202
    assert response.json()["status"] == "guardado"
    assert contar(data_dir / "inbox.db") == 1


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


def test_se_guarda_el_origen_recibido(client, data_dir):
    enviar(client, origen="sensor-07")
    con = sqlite3.connect(data_dir / "inbox.db")
    try:
        assert con.execute("SELECT origen, event_id FROM eventos").fetchall() == [("sensor-07", "evt-001")]
    finally:
        con.close()


def test_sin_origen_no_guarda_nada(client, data_dir):
    response = client.post("/verificacion", content=EVENTO, headers={"x-signature": firmar(EVENTO)})
    assert response.status_code == 422
    assert contar(data_dir / "inbox.db") == 0


def test_firma_invalida_no_guarda_nada(client, data_dir):
    response = client.post("/verificacion", content=EVENTO, headers={"x-signature": "sha256=falsa"})
    assert response.status_code == 403
    assert contar(data_dir / "inbox.db") == 0


def test_esquema_invalido_no_guarda_nada(client, data_dir):
    body = json.dumps({"event_id": "evt-001", "event_type": "otro.tipo"}).encode()
    assert enviar(client, body).status_code == 422
    assert contar(data_dir / "inbox.db") == 0


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
