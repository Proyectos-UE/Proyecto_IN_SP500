#AQUI PARA HACER LA APLICACION
from fastapi import FastAPI

app = FastAPI(title="SP500 API", version="0.0.1")

@app.get("/health")
def health():
    return {"status": "ok"}

