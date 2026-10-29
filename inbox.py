import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from models import Evento


class EventConflict(ValueError):
    """Un event_id se ha reutilizado con un contenido distinto."""


class Inbox:
    """Base de datos local de eventos recibidos."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS eventos (
                    origen TEXT NOT NULL, event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, resultado TEXT NOT NULL,
                    fecha DATE NOT NULL, hora TIME NOT NULL,
                    contenido TEXT NOT NULL, hash TEXT NOT NULL,
                    PRIMARY KEY (origen, event_id));
            ''')

    @contextmanager
    def connection(self):
        """Confirma si todo va bien, deshace si hay error y siempre cierra."""
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def store(self, evento: Evento, resultado: str = 'aceptado') -> str:
        """Guarda el evento. Devuelve 'guardado' o 'duplicado'.
        Si el mismo (origen, event_id) llega con contenido distinto lanza EventConflict.
        """
        contenido = json.dumps(evento.model_dump(), sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(contenido.encode()).hexdigest()
        ahora = datetime.now()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')   # bloquea escrituras: evita carreras entre duplicados
            old = db.execute('SELECT hash FROM eventos WHERE origen=? AND event_id=?',
                             (evento.origen, evento.event_id)).fetchone()
            if old is not None:
                if old['hash'] != digest:
                    raise EventConflict('event_id reutilizado con contenido distinto')
                return 'duplicado'
            db.execute(
                'INSERT INTO eventos(origen,event_id,event_type,resultado,fecha,hora,contenido,hash) '
                'VALUES(?,?,?,?,?,?,?,?)',
                (evento.origen, evento.event_id, evento.event_type, resultado,
                 ahora.date().isoformat(), ahora.strftime('%H:%M:%S'), contenido, digest))
        return 'guardado'