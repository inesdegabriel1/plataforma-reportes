"""Acceso a MySQL/MariaDB. Sesión en modo SOLO LECTURA y consultas siempre parametrizadas."""
import logging
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from . import config

log = logging.getLogger("ehm.db")
_read_only_supported: bool | None = None


@contextmanager
def connection():
    conn = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=300,
        autocommit=True,
    )
    try:
        # Protección extra: aunque el usuario tuviera permisos de escritura, la sesión no puede
        # modificar nada. Los servidores antiguos (MySQL < 5.6.5) no lo soportan; en ese caso
        # la protección es que el código solo ejecuta SELECT.
        global _read_only_supported
        if _read_only_supported is not False:
            try:
                with conn.cursor() as cur:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
                _read_only_supported = True
            except pymysql.err.MySQLError:
                _read_only_supported = False
                log.warning("El servidor MySQL no admite sesiones de solo lectura (versión antigua).")
        yield conn
    finally:
        conn.close()


def query(sql: str, params: list | tuple | None = None) -> list[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())
