from fastapi import FastAPI
from app.routes import assist
from app.routes import auth_routes
from app.logger import setup_logging
from fastapi.staticfiles import StaticFiles
from app.config import get_settings

setup_logging()

app = FastAPI(title="Banking Assisstant")

app.include_router(auth_routes.router, prefix="/auth")
app.include_router(assist.router, prefix="/assist")
# Serve static frontend files from /static
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def validate_settings():
    settings = get_settings()
    if not settings.auth_configured:
        raise RuntimeError(
            "Authentication is not configured. Set JWT_SECRET_KEY, ADMIN_USERNAME, and ADMIN_PASSWORD."
        )

@app.get('/health')
async def health():
    return {'status': 'ok'}
