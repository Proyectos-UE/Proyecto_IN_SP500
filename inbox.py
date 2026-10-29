import hashlib
import json
import sqlite3
import datetime
from contextlib import contextmanager
from pathlib import Path
from models import Evento

class EventConflict(ValueError):
    """An event ID or resource revision was reused with different content."""

class Inbox:
    """Base de Datos Local."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
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
        """Commit successful work, roll back failures, and always close."""
        db = sqlite3.connect(self.path, timeout=5)
        db.row_evento = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    
    def store(self, evento: Evento) -> str:
        """Persist before acknowledging; reject changed content under the same ID."""
        contenido = json.dumps(evento.model_dump(), sort_keys=True, separators=(',', ':'))
        hash = hashlib.sha256(contenido.encode()).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT hash FROM events WHERE origen=? AND event_id=?',
                             (evento.origen, evento.event_id)).fetchone()
            if old is not None:
                if old['hash'] != hash:
                    raise EventConflict('Event ID reused with different content')
                return 'duplicado'
            db.execute('INSERT INTO events(origen,event_id,event_type,resultado,fecha,hora,contenido,hash) VALUES(?,?,?,?,?,?,?,?)',
                    (evento.origen, evento.event_id, evento.event_type, evento.resultado, datetime.date.today(), (datetime.now()).strftime("%H:%M:%S"), contenido, hash))
        return 'guardado'
