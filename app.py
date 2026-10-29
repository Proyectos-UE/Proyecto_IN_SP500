#AQUI PARA HACER LA APLICACION
from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import ValidationError
from pathlib import Path
import os
import hmac
import hashlib
from models import ValidacionBase
from dotenv import load_dotenv
load_dotenv()

DATA = Path(__file__).parent / 'data'

def valid_signature(body: bytes, received: str, secretWH: bytes) -> bool:
    """Verifica la firma en forma de cadena de Bytes."""
    expected = 'sha256=' + hmac.new(secretWH, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)

def create_app(dataDir: Path, secretWH: bytes) -> FastAPI:
    """Crea la app en local"""
    if not secretWH:
        raise ValueError('La variable WebhookSecret es necesaria')
    app = FastAPI(title='API_SP500', version="0.0.1")

    #Al pedir directamente el request no se muestra la información a rellenar en docs
    async def validacionesBase(request: Request) -> dict: 
        """Comprueba tamaño, la calve WEBHOOK_SECRET y valida el cuerpo de la petición"""
        
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > 65536:
            raise HTTPException(413, 'Payload too large')

        bodyRaw = await request.body()
        
        if len(bodyRaw) > 65536:
            raise HTTPException(413, 'Payload too large')

        secret_recibido = request.headers.get('x-signature', '')    
        if not valid_signature(bodyRaw, secret_recibido, secretWH):
            raise HTTPException(403, 'Firma Invalida')
        try:
            data_salida = ValidacionBase.model_validate_json(bodyRaw)
        except ValidationError:
            raise HTTPException(422, 'Esquema de la petición invalido')

        return {'accepted': True, 'output': data_salida.model_dump()}

    
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post('/verificacion', status_code=202)
    async def verificacion(data_salida: dict = Depends(validacionesBase)) -> dict:
        """Endpoint para comprobar las validaciones base"""
        return data_salida
    
    return app
    

def create_from_env() -> FastAPI:
    """Requiere la variable de entorno "WEBHOOK_SECRET" para iniciar si no falla"""
    secretWH = os.environ.get('WEBHOOK_SECRET')
    if not secretWH:
        raise RuntimeError('Asigna WEBHOOK_SECRET antes de iniciar la app')
    return create_app(DATA, secretWH.encode())

app = create_from_env()