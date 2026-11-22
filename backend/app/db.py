"""Acceso a MySQL/MariaDB. Sesión en modo SOLO LECTURA y consultas siempre parametrizadas."""
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from . import config


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
        with conn.cursor() as cur:
            # Protección extra: aunque el usuario tuviera permisos de escritura,
            # esta sesión no puede modificar nada.
            cur.execute("SET SESSION TRANSACTION READ ONLY")
        yield conn
    finally:
        conn.close()


def query(sql: str, params: list | tuple | None = None) -> list[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())
