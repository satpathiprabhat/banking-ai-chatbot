from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.auth import create_jwt_token
from app.config import get_settings

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginRequest):
    settings = get_settings()
    if not settings.auth_configured:
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    if req.username == settings.admin_username and req.password == settings.admin_password:
        token = create_jwt_token(req.username)
        return {"token": token}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")
