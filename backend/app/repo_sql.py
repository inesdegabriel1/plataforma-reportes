"""Consultas a la base de datos real (esquema qar).

Todas las consultas son SELECT parametrizados. Nunca se seleccionan columnas con datos
personales de tripulación (NOMBRE_*, CODPER_*, EMAIL_*) de vuelos_loreto.
"""
from datetime import date

from . import config
from .db import query

# Tiempo de vuelo: el de vuelos_loreto y, si no hay, el del QAR.
FT = "COALESCE(NULLIF(v.VUE_FTIME, 0), v.QAR_FTIME, 0)"


def _valid_flight() -> tuple[str, list]:
    """Condición de vuelo realizado (no cancelado, ya ocurrido y con tiempo de vuelo)."""
    vals = config.CANCELLED_VALUES
    marks = ",".join(["%s"] * len(vals))
    cond = (f"(v.CANCELADO IS NULL OR UPPER(TRIM(v.CANCELADO)) NOT IN ({marks}))"
            f" AND v.FECHA_REAL <= NOW()")
    if config.REQUIRE_FLIGHT_TIME:
        cond += f" AND {FT} > 0"
    return cond, list(vals)


# --------------------------------------------------------------------------- maestros
def aircraft_list() -> list[dict]:
    return query("""
        SELECT a.ID_Avion id, a.Matricula matricula, a.ID_Flota id_flota, f.Flota flota,
               a.Variante variante, a.Motor motor, TRIM(a.SN_ENGINE_1) sn1,
               TRIM(a.SN_ENGINE_2) sn2, a.FLGACTIVO activo
        FROM aviones a LEFT JOIN flotas f ON f.ID_Flota = a.ID_Flota
        ORDER BY a.Matricula""")


def fleet_engines() -> list[dict]:
    cond, p = _valid_flight()
    half = """
        SELECT TRIM(v.SN_ENGINE_{n}) sn, {n} pos, v.FECHA_REAL fecha, v.MATRICULA matricula,
               v.ID_AVION id_avion, {ft} ft
        FROM vuelos_loreto v WHERE {cond}"""
    sql = f"""
        SELECT x.sn, COUNT(*) cycles, SUM(x.ft) ft, MIN(x.fecha) first_date, MAX(x.fecha) last_date,
          SUBSTRING_INDEX(GROUP_CONCAT(x.matricula ORDER BY x.fecha DESC SEPARATOR '|'), '|', 1) last_matricula,
          SUBSTRING_INDEX(GROUP_CONCAT(x.pos ORDER BY x.fecha DESC SEPARATOR '|'), '|', 1) last_pos,
          SUBSTRING_INDEX(GROUP_CONCAT(x.id_avion ORDER BY x.fecha DESC SEPARATOR '|'), '|', 1) last_id_avion
        FROM ({half.format(n=1, ft=FT, cond=cond)} UNION ALL {half.format(n=2, ft=FT, cond=cond)}) x
        WHERE x.sn IS NOT NULL AND x.sn <> ''
        GROUP BY x.sn"""
    return query(sql, p + p)


# --------------------------------------------------------------------------- vuelos
def engine_flights(sn: str) -> list[dict]:
    cond, p = _valid_flight()
    half = """
        SELECT v.ID id_vuelo, v.ID_AVION id_avion, v.MATRICULA matricula, v.FECHA_REAL fecha,
               v.ORIGEN origen, v.DESTINO destino, {ft} ft, {n} pos, TRIM(v.SN_ENGINE_{n}) sn
        FROM vuelos_loreto v WHERE v.SN_ENGINE_{n} = %s AND {cond}"""
    sql = (f"SELECT * FROM ({half.format(n=1, ft=FT, cond=cond)} UNION ALL "
           f"{half.format(n=2, ft=FT, cond=cond)}) x ORDER BY x.fecha")
    return query(sql, [sn] + p + [sn] + p)


def aircraft_flights(id_avion: int) -> list[dict]:
    cond, p = _valid_flight()
    return query(f"""
        SELECT v.ID id_vuelo, v.ID_AVION id_avion, v.MATRICULA matricula, v.FECHA_REAL fecha,
               v.ORIGEN origen, v.DESTINO destino, {FT} ft,
               TRIM(v.SN_ENGINE_1) sn1, TRIM(v.SN_ENGINE_2) sn2
        FROM vuelos_loreto v WHERE v.ID_AVION = %s AND {cond}
        ORDER BY v.FECHA_REAL""", [id_avion] + p)


# --------------------------------------------------------------------------- parámetros de motor
# alias -> columna de t_qar_flightsfile ({s} = L para motor 1, R para motor 2)
SERIES_COLS = {
    "tof_egt": "TOF_EGT_{s}", "crz_egt": "CRZ_EGT_{s}",
    "tof_ff": "TOF_FUELFLOW_{s}", "crz_ff": "CRZ_FUELFLOW_{s}",
    "tof_n1": "TOF_N1_{s}", "crz_n1": "CRZ_N1_{s}",
    "tof_n2": "TOF_N2_{s}", "crz_n2": "CRZ_N2_{s}",
    "tof_op": "TOF_OP_{s}", "crz_op": "CRZ_OP_{s}",
    "tof_ot": "TOF_OT_{s}", "crz_ot": "CRZ_OT_{s}",
    "crz_oq": "CRZ_OQ_{s}",
    "tof_vib_n1": "TOF_FV_N1{s}", "tof_vib_n2": "TOF_FV_N2{s}",
    "crz_vib_n1": "CRZ_FV_N1{s}", "crz_vib_n2": "CRZ_FV_N2{s}",
    "taxi_fuel": "FUEL_USED_TAXI2TAKEOFF_{s}",
}
COMMON = (f"f.ID_FLIGHTFILE id_flightfile, v.ID id_vuelo, v.MATRICULA matricula, "
          f"COALESCE(v.FECHA_REAL, f.FLIGHT_DATE) fecha, v.ORIGEN origen, v.DESTINO destino, "
          f"f.TOF_TAT tof_tat, f.CRZ_TAT crz_tat, f.CRZ_ALT crz_alt, f.CRZ_MACH crz_mach, "
          f"f.FUEL_O fuel_o, f.FUEL_D fuel_d, {FT} ft")


def _where(kind: str, n: int) -> str:
    key = f"v.SN_ENGINE_{n} = %s" if kind == "engine" else "v.ID_AVION = %s"
    return f"{key} AND v.FECHA_REAL >= %s AND v.FECHA_REAL < %s"


def series(kind: str, key, desde: date, hasta_excl: date) -> list[dict]:
    halves = []
    for n, s in ((1, "L"), (2, "R")):
        cols = ", ".join(f"f.{tpl.format(s=s)} {alias}" for alias, tpl in SERIES_COLS.items())
        halves.append(f"SELECT {COMMON}, {n} pos, TRIM(v.SN_ENGINE_{n}) sn, {cols} "
                      f"FROM t_qar_flightsfile f JOIN vuelos_loreto v ON v.ID = f.ID_VUELO "
                      f"WHERE {_where(kind, n)}")
    p = [key, desde, hasta_excl]
    return query(f"SELECT * FROM ({' UNION ALL '.join(halves)}) x ORDER BY x.fecha", p + p)


def oil(kind: str, key, desde: date, hasta_excl: date) -> list[dict]:
    halves = []
    for n, s in ((1, "L"), (2, "R")):
        halves.append(
            f"SELECT v.FECHA_REAL fecha, v.MATRICULA matricula, o.ID_FLIGHTFILE id_flightfile, "
            f"{n} pos, TRIM(v.SN_ENGINE_{n}) sn, o.OIL_CONS_RATE_{s}_CRZ_AVG rate, "
            f"o.OIL_QTY_{s}_START qty_start, o.OIL_QTY_{s}_END qty_end, o.FLIGHT_TIME flight_time "
            f"FROM tmp_oil_qty_crz o JOIN vuelos_loreto v ON v.ID = o.ID_VUELO "
            f"WHERE {_where(kind, n)}")
    p = [key, desde, hasta_excl]
    return query(f"SELECT * FROM ({' UNION ALL '.join(halves)}) x ORDER BY x.fecha", p + p)


# --------------------------------------------------------------------------- reportes ACMS
def a321_reports(after_id: int) -> list[dict]:
    """Reportes de motor A321 (01 crucero, 04 despegue) con ID_REPORT > after_id."""
    return query("""
        SELECT r.ID_REPORT id, r.TYPE_FILE tipo, fo.ID_Avion id_avion, a.Matricula matricula,
               r.CONTENT_FILE contenido
        FROM t_qar_a321_reports r
        JOIN t_qar_folder fo ON fo.Id_Folder = r.ID_FOLDER
        LEFT JOIN aviones a ON a.ID_Avion = fo.ID_Avion
        WHERE r.TYPE_FILE IN ('REPORT01', 'REPORT04') AND r.ID_REPORT > %s
        ORDER BY r.ID_REPORT""", [after_id])


def atr_reports(after_id: int) -> list[dict]:
    """Reportes de motor ATR (REPORT02, en crucero) con ID_REPORT > after_id."""
    return query("""
        SELECT r.ID_REPORT id, r.TYPE_FILE tipo, fo.ID_Avion id_avion, a.Matricula matricula,
               r.CONTENT_FILE contenido
        FROM t_qar_atr_reports r
        JOIN t_qar_folder_atr fo ON fo.Id_Folder = r.ID_FOLDER
        LEFT JOIN aviones a ON a.ID_Avion = fo.ID_Avion
        WHERE r.TYPE_FILE = 'REPORT02' AND r.ID_REPORT > %s
        ORDER BY r.ID_REPORT""", [after_id])


# --------------------------------------------------------------------------- eventos
_EVENT_COLS = ("ID_FLIGHTFILE, ID_FLIGHT, ID_FLOTA, MATRICULA, FECHA_VUELO, ORIGEN, DESTINO, "
               "FLAP_EVE, ALT_EVE, G_EVE, OVW_EVE, HARD_EVE, LDG_EVE, EGT_EVE, CORE_EVE, VIB_EVE, "
               "TXT_EVENT, ENG")
_EVENTS_BASE = f"""
    SELECT e.*, v.FECHA_REAL fecha_real, v.ID_AVION id_avion,
           TRIM(v.SN_ENGINE_1) sn1, TRIM(v.SN_ENGINE_2) sn2
    FROM (SELECT {_EVENT_COLS} FROM tmp_import_engines
          UNION
          SELECT {_EVENT_COLS} FROM tmp_import_file4_ines) e
    LEFT JOIN t_qar_flightsfile f ON f.ID_FLIGHTFILE = e.ID_FLIGHTFILE
    LEFT JOIN vuelos_loreto v ON v.ID = f.ID_VUELO"""


def events(kind: str, key, matricula: str | None = None) -> list[dict]:
    if kind == "engine":
        return query(_EVENTS_BASE + " WHERE (e.ENG = 1 AND v.SN_ENGINE_1 = %s)"
                     " OR (e.ENG = 2 AND v.SN_ENGINE_2 = %s)", [key, key])
    return query(_EVENTS_BASE + " WHERE e.MATRICULA = %s OR v.ID_AVION = %s", [matricula, key])
