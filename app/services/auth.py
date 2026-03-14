from datetime import datetime, timedelta, timezone
import jwt

from app.config import get_settings

def create_jwt_token(username: str):
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    return token

def verify_jwt_token(token: str):
    settings = get_settings()
    if not settings.jwt_secret_key:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        return None
