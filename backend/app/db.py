"""Acceso a MySQL. REGLA: la aplicación SOLO ejecuta SELECT. Nunca modifica la base de datos.

Esta es la única puerta a la base de datos. Antes de ejecutar nada, `query()` comprueba que la
sentencia es un único SELECT de lectura y rechaza cualquier otra cosa (INSERT, UPDATE, DELETE,
CREATE, DROP, ALTER, SET, CALL, LOCK, SELECT ... INTO OUTFILE, SELECT ... FOR UPDATE, varias
sentencias separadas por ";", etc.).

El servidor es MySQL 5.5, que no admite sesiones de solo lectura; por eso el control se hace aquí.
Lo ideal es además usar un usuario MySQL con permiso únicamente de SELECT.
"""
import re
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from . import config


class ReadOnlyViolation(RuntimeError):
    """Se ha intentado ejecutar algo que no es un SELECT."""


_COMMENTS = re.compile(r"/\*.*?\*/|--[^\n]*|#[^\n]*", re.S)
_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|MERGE|UPSERT|CREATE|DROP|ALTER|TRUNCATE|RENAME|GRANT|REVOKE|"
    r"SET|CALL|EXECUTE|PREPARE|DEALLOCATE|DO|HANDLER|LOAD|LOCK|UNLOCK|COMMIT|ROLLBACK|SAVEPOINT|"
    r"START|BEGIN|INTO|OUTFILE|DUMPFILE|SHARE|KILL|SHUTDOWN|FLUSH|RESET|PURGE|INSTALL|UNINSTALL|"
    r"ANALYZE|OPTIMIZE|REPAIR|CHECKSUM)\b",
    re.I,
)


def assert_select_only(sql: str) -> None:
    """Lanza ReadOnlyViolation si `sql` no es exclusivamente una consulta SELECT."""
    code = _STRINGS.sub("''", _COMMENTS.sub(" ", sql)).strip()
    if ";" in code:
        raise ReadOnlyViolation("Solo se permite una sentencia (sin ';').")
    if not re.match(r"^\(?\s*SELECT\b", code, re.I):
        raise ReadOnlyViolation("Solo se permiten consultas SELECT.")
    bad = _FORBIDDEN.search(code)
    if bad or re.search(r"\bFOR\s+UPDATE\b", code, re.I):
        raise ReadOnlyViolation(f"Palabra no permitida en una consulta de solo lectura: {bad.group(1) if bad else 'FOR UPDATE'}")


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
        autocommit=False,  # nada se confirma nunca: al cerrar se descarta cualquier cosa
        client_flag=0,     # sin MULTI_STATEMENTS: el servidor rechaza varias sentencias juntas
    )
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def query(sql: str, params: list | tuple | None = None) -> list[dict]:
    assert_select_only(sql)
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())
