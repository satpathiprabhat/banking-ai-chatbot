import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.auth import create_jwt_token

router = APIRouter()

_VALID_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_VALID_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginRequest):
    if req.username == _VALID_USERNAME and req.password == _VALID_PASSWORD:
        token = create_jwt_token(req.username)
        return {"token": token}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")