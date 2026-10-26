#AQUI PARA HACER LA APLICACION
from fastapi import FastAPI
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

DATA = Path(__file__).parent / 'data'

def create_app(directory: Path, secretWH: bytes) -> FastAPI:
    """Crea la app en local"""
    if not secretWH:
        raise ValueError('La variable WebhookSecret es necesaria')
    app = FastAPI(title='API_SP500_V1.0', version="0.0.1")
    
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
    

def create_from_env() -> FastAPI:
    """Requiere la variable de entorno "WEBHOOK_SECRET" para iniciar si no falla"""
    secretWH = os.environ.get('WEBHOOK_SECRET')
    if not secretWH:
        raise RuntimeError('Asigna WEBHOOK_SECRET antes de iniciar la app')
    return create_app(DATA, secretWH.encode())

app = create_from_env()