"""Configuración leída SOLO de variables de entorno (.env). Nada sensible en el código."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si", "sí")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


# --- Modo demo (datos sintéticos inventados, sin base de datos) ---
DEMO = _bool("DEMO")

# --- Base de datos (MySQL / MariaDB) ---
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "qar")

# --- Autenticación ---
APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
TOKEN_HOURS = float(os.getenv("TOKEN_HOURS", "8"))

# --- Web ---
ALLOWED_ORIGINS = _list(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,https://inesdegabriel1.github.io",
)
SERVE_FRONTEND = _bool("SERVE_FRONTEND", "1")

# --- Reglas de negocio (ajustables sin tocar código) ---
# Unidad de vuelos_loreto.VUE_FTIME / QAR_FTIME: "min" o "sec"
FLIGHT_TIME_UNIT = os.getenv("FLIGHT_TIME_UNIT", "min").lower()
# Valores de vuelos_loreto.CANCELADO que indican vuelo cancelado
CANCELLED_VALUES = [v.upper() for v in _list("CANCELLED_VALUES", "S,SI,Y,1,X")]
# Contar como ciclo solo vuelos con tiempo de vuelo > 0 (descarta vuelos planificados)
REQUIRE_FLIGHT_TIME = _bool("REQUIRE_FLIGHT_TIME", "1")
# Días sin volar a partir de los cuales se considera parada (posible C-check)
STOP_DAYS = int(os.getenv("STOP_DAYS", "30"))
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "600"))


def validate() -> list[str]:
    """Comprueba la configuración al arrancar. Devuelve avisos; lanza error si falta algo crítico."""
    global APP_PASSWORD_HASH, JWT_SECRET
    warnings = []
    if not JWT_SECRET:
        JWT_SECRET = secrets.token_urlsafe(48)
        warnings.append("JWT_SECRET no definido: se usa uno aleatorio (las sesiones caducan al reiniciar).")
    if not APP_PASSWORD_HASH:
        if DEMO:
            from argon2 import PasswordHasher
            APP_PASSWORD_HASH = PasswordHasher().hash("demo")
            warnings.append("Modo DEMO sin APP_PASSWORD_HASH: la contraseña es 'demo'.")
        else:
            raise RuntimeError(
                "Falta APP_PASSWORD_HASH en backend/.env. Genera uno con: python hash_password.py"
            )
    if not DEMO and not (DB_HOST and DB_USER):
        raise RuntimeError("Faltan DB_HOST / DB_USER en backend/.env (o activa DEMO=1).")
    return warnings
