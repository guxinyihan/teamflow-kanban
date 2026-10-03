from datetime import datetime, timedelta, timezone
import secrets
import bcrypt
import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from ..config import settings

password_hash = PasswordHash.recommended()
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_MINUTES

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(password.encode()[:72], stored.encode())
        return password_hash.verify(password, stored)
    except (ValueError, UnknownHashError):
        return False

def create_access_token(data: dict, expires_delta=None) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(data["sub"]), "type": "access", "iss": "teamflow",
                       "aud": "teamflow-api", "iat": now,
                       "exp": now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)),
                       "jti": secrets.token_hex(16)}, settings.JWT_SECRET, algorithm="HS256")

def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"],
                             issuer="teamflow", audience="teamflow-api",
                             options={"require": ["sub", "exp", "iat", "type", "jti"]})
        if payload["type"] != "access" or not str(payload["sub"]).isdigit():
            return None
        return payload
    except jwt.InvalidTokenError:
        return None