"""API de la plataforma de salud de motores. Arranque: ver README.md."""
import logging
from datetime import date

import pymysql
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config

for w in config.validate():
    logging.warning(w)

from . import services  # noqa: E402  (importa el repositorio según DEMO)

log = logging.getLogger("ehm")

# Sin documentación automática pública (/docs): no hace falta exponer la estructura del API.
app = FastAPI(title="Swiftair Engine Health", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    # Permite que la web de GitHub Pages (pública) llame a este backend en localhost.
    # Solo para los orígenes de ALLOWED_ORIGINS.
    allow_private_network=True,
)


async def server_errors(request: Request, exc: Exception):
    log.exception("Error en %s", request.url.path)
    if isinstance(exc, pymysql.err.OperationalError) and exc.args and exc.args[0] == 1045:
        msg = ("La base de datos rechaza el usuario o la contraseña. "
               "Revisa DB_USER y DB_PASSWORD en backend/.env y reinicia el backend.")
    elif isinstance(exc, pymysql.err.OperationalError) and exc.args and exc.args[0] in (2003, 2005):
        msg = "No se puede llegar al servidor de base de datos. ¿Estás en la red de Swiftair o con VPN?"
    else:
        msg = f"Error del servidor: {type(exc).__name__}: {exc}"[:400]
    return JSONResponse(status_code=502, content={"detail": msg})


# Los manejadores de clases concretas se ejecutan DENTRO del middleware CORS, así la respuesta
# de error lleva las cabeceras CORS y la web de GitHub Pages puede leer el mensaje.
# (Un manejador de `Exception` genérico se ejecuta fuera de CORS y el navegador lo bloquearía.)
for _cls in (pymysql.MySQLError, ValueError, KeyError, TypeError, RuntimeError, AttributeError,
             IndexError, ZeroDivisionError, OSError):
    app.add_exception_handler(_cls, server_errors)


class LoginIn(BaseModel):
    password: str


@app.get("/api/health")
async def api_health():  # async: responde aunque el backend esté ocupado con otras consultas
    return {"status": "ok", "demo": config.DEMO}


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "?"
    auth.check_not_blocked(ip)
    if not auth.verify_password(body.password):
        auth.register_failure(ip)
        raise HTTPException(401, "Contraseña incorrecta")
    auth.register_success(ip)
    token, exp = auth.create_token()
    return {"token": token, "expira": exp.isoformat(), "demo": config.DEMO}


protected = [Depends(auth.require_auth)]


@app.get("/api/meta", dependencies=protected)
def meta():
    return {"aviones": services.aircraft(), "demo": config.DEMO, "dias_parada": config.STOP_DAYS}


@app.get("/api/fleet", dependencies=protected)
def fleet():
    return {"motores": services.fleet()}


@app.get("/api/engine", dependencies=protected)
def engine(sn: str, desde: date | None = None, hasta: date | None = None):
    return services.engine_detail(sn.strip(), desde, hasta)


@app.get("/api/aircraft", dependencies=protected)
def aircraft(id: int, desde: date | None = None, hasta: date | None = None):
    data = services.aircraft_detail(id, desde, hasta)
    if data is None:
        raise HTTPException(404, "Avión no encontrado")
    return data


# En local, el propio backend sirve la web (http://localhost:8000).
if config.SERVE_FRONTEND:
    app.mount("/", StaticFiles(directory=config.PROJECT_DIR / "frontend", html=True), name="web")
