from fastapi import FastAPI, Request, HTTPException
from app.routes import assist
from app.routes import auth_routes
from app.logger import setup_logging
from fastapi.staticfiles import StaticFiles
import os

setup_logging()

app = FastAPI(title="Banking Assisstant")

app.include_router(auth_routes.router, prefix="/auth")
app.include_router(assist.router, prefix="/assist")
# Serve static frontend files from /static
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get('/health')
async def health():
    return {'status': 'ok'}
