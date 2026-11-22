"""Login con contraseña única (hash argon2 en .env) y token JWT de corta duración."""
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

# Limitador de intentos fallidos (en memoria). Detrás de un túnel todas las peticiones
# llegan desde la misma IP, así que el bloqueo actúa de forma global: es más estricto.
MAX_FAILS = 5
WINDOW_S = 15 * 60
BLOCK_S = 15 * 60
_fails: dict[str, list[float]] = {}
_blocked_until: dict[str, float] = {}
_lock = threading.Lock()


def check_not_blocked(ip: str) -> None:
    with _lock:
        until = _blocked_until.get(ip, 0)
        if until > time.time():
            mins = int((until - time.time()) // 60) + 1
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                f"Demasiados intentos. Vuelve a probar en {mins} min.")


def register_failure(ip: str) -> None:
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(ip, []) if now - t < WINDOW_S] + [now]
        _fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            _blocked_until[ip] = now + BLOCK_S
            _fails[ip] = []


def register_success(ip: str) -> None:
    with _lock:
        _fails.pop(ip, None)


def verify_password(password: str) -> bool:
    try:
        return _ph.verify(config.APP_PASSWORD_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_token() -> tuple[str, datetime]:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS)
    token = jwt.encode({"sub": "swiftair-ehm", "exp": exp, "iat": datetime.now(timezone.utc)},
                       config.JWT_SECRET, algorithm="HS256")
    return token, exp


def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    try:
        jwt.decode(creds.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión caducada o no válida")
