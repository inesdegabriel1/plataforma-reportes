"""Datos SINTÉTICOS inventados para probar la aplicación sin base de datos (DEMO=1).

Nada de aquí procede de la base de datos real: matrículas DEMO-xx, motores SIM-xxxx y
valores generados con un generador aleatorio con semilla fija.
Expone exactamente las mismas funciones (y la misma forma de filas) que repo_sql.
"""
import random
from datetime import date, datetime, timedelta
from functools import lru_cache

FT_UNIT = "min"

AIRPORTS = ["MAD", "BCN", "VLC", "PMI", "LEJ", "EMA", "BRU", "CDG", "FRA", "LGG", "AGP", "TFN"]

AIRCRAFT = [
    dict(id=901, matricula="DEMO-01", id_flota=1, flota="B737", variante="737-400F (demo)", motor="CFM56-3C1"),
    dict(id=902, matricula="DEMO-02", id_flota=2, flota="B737NG", variante="737-800BCF (demo)", motor="CFM56-7B26"),
    dict(id=903, matricula="DEMO-03", id_flota=3, flota="B757", variante="757-200PCF (demo)", motor="RB211-535E4"),
    dict(id=904, matricula="DEMO-04", id_flota=4, flota="A321", variante="A321P2F (demo)", motor="V2533-A5"),
    dict(id=905, matricula="DEMO-05", id_flota=5, flota="ATR", variante="ATR72-500F (demo)", motor="PW127F"),
]
# Instalaciones: por avión y posición, lista de (día desde el inicio, nº de serie)
INSTALLS = {
    901: {1: [(0, "SIM-1001")], 2: [(0, "SIM-1099"), (400, "SIM-1002")]},
    902: {1: [(0, "SIM-2001"), (450, "SIM-1099")], 2: [(0, "SIM-2002")]},
    903: {1: [(0, "SIM-3001")], 2: [(0, "SIM-3002")]},
    904: {1: [(0, "SIM-4001")], 2: [(0, "SIM-4002")]},
    905: {1: [(0, "SIM-5001")], 2: [(0, "SIM-5002")]},
}
# Perfil por flota: EGT despegue, EGT crucero, FF despegue/crucero (kg/h), aceite (cant.), duración vuelo
PROFILE = {
    "B737": (880, 640, 4200, 1250, 14.0, (60, 200)),
    "B737NG": (900, 660, 4400, 1200, 18.0, (60, 240)),
    "B757": (620, 480, 6500, 2100, 16.0, (90, 300)),
    "A321": (870, 650, 4600, 1300, 17.0, (60, 240)),
    "ATR": (760, 690, 650, 420, 9.0, (40, 120)),
}
# Motores con degradación anómala (para ver ámbar/rojo en la demo)
DEGRADING_EGT = {"SIM-2002": 700}       # sn -> día a partir del cual sube la EGT
RISING_OIL = {"SIM-3001": 850}          # sn -> día a partir del cual sube el consumo de aceite


def _sn_at(id_avion: int, pos: int, day: int) -> str:
    sn = None
    for start, s in INSTALLS[id_avion][pos]:
        if day >= start:
            sn = s
    return sn


@lru_cache(maxsize=1)
def _data():
    rng = random.Random(42)
    today = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = today - timedelta(days=3 * 365)
    ndays = (today - start).days
    flights, events = [], []
    flights_by_sn: dict[str, int] = {}
    fid = 100000
    for idx, ac in enumerate(AIRCRAFT):
        egt_tof0, egt_crz0, ff_tof0, ff_crz0, oq0, (ftmin, ftmax) = PROFILE[ac["flota"]]
        stop_from = 150 + idx * 170
        stop_to = stop_from + rng.randint(35, 55)
        wash_offset = {}
        loc = rng.choice(AIRPORTS)
        for day in range(ndays):
            if stop_from <= day < stop_to:
                continue
            for k in range(rng.choice([0, 1, 2, 2, 2, 3])):
                fid += 1
                dest = rng.choice([a for a in AIRPORTS if a != loc])
                when = start + timedelta(days=day, hours=6 + k * 5 + rng.randint(0, 3))
                ft = rng.randint(ftmin, ftmax)
                row = dict(id_vuelo=fid, id_flightfile=fid + 500000, id_avion=ac["id"],
                           matricula=ac["matricula"], fecha=when, origen=loc, destino=dest, ft=ft,
                           tof_tat=round(rng.uniform(5, 32), 1), crz_tat=round(rng.uniform(-35, -15), 1),
                           crz_alt=rng.choice([31000, 33000, 35000, 37000]) if ac["flota"] != "ATR" else 22000,
                           crz_mach=round(rng.uniform(0.72, 0.79), 3) if ac["flota"] != "ATR" else 0.45)
                burn = ff_crz0 * 2 * ft / 60 * rng.uniform(0.95, 1.08)
                row["fuel_o"] = round(burn + rng.uniform(3000, 9000))
                row["fuel_d"] = round(row["fuel_o"] - burn)
                pending = []
                for pos in (1, 2):
                    sn = _sn_at(ac["id"], pos, day)
                    n = flights_by_sn.get(sn, 0) + 1
                    flights_by_sn[sn] = n
                    if day >= stop_to and sn not in wash_offset:  # lavado de motor tras la parada
                        wash_offset[sn] = 12
                    drift = n * 0.012 - wash_offset.get(sn, 0)
                    if sn in DEGRADING_EGT and day > DEGRADING_EGT[sn]:
                        drift += (day - DEGRADING_EGT[sn]) * 0.09
                    oil_rate = 0.15 + rng.gauss(0, 0.03)
                    if sn in RISING_OIL and day > RISING_OIL[sn]:
                        oil_rate += (day - RISING_OIL[sn]) * 0.0012
                    tat_eff = (row["tof_tat"] - 15) * 1.6
                    row[f"sn{pos}"] = sn
                    row[f"p{pos}"] = dict(
                        tof_egt=round(egt_tof0 + drift + tat_eff + rng.gauss(0, 6), 1),
                        crz_egt=round(egt_crz0 + drift * 0.8 + rng.gauss(0, 4), 1),
                        tof_ff=round(ff_tof0 * rng.uniform(0.96, 1.04)),
                        crz_ff=round(ff_crz0 * rng.uniform(0.95, 1.05) * (1 + drift / 2000)),
                        tof_n1=round(rng.uniform(90, 97), 1), crz_n1=round(rng.uniform(82, 88), 1),
                        tof_n2=round(rng.uniform(95, 100), 1), crz_n2=round(rng.uniform(88, 94), 1),
                        tof_op=round(rng.uniform(55, 70), 1), crz_op=round(rng.uniform(40, 55), 1),
                        tof_ot=round(rng.uniform(80, 100), 1), crz_ot=round(rng.uniform(85, 110), 1),
                        crz_oq=round(oq0 - (n % 20) * oil_rate * 0.4 + rng.gauss(0, 0.2), 2),
                        tof_vib_n1=round(abs(rng.gauss(0.6, 0.25)), 2), tof_vib_n2=round(abs(rng.gauss(0.5, 0.2)), 2),
                        crz_vib_n1=round(abs(rng.gauss(0.4, 0.15)), 2), crz_vib_n2=round(abs(rng.gauss(0.3, 0.12)), 2),
                        taxi_fuel=round(rng.uniform(60, 180)),
                        oil_rate=round(max(oil_rate, 0.02), 3),
                    )
                    p_evt = 0.004 + (0.05 if sn in DEGRADING_EGT and day > DEGRADING_EGT[sn] + 200 else 0)
                    if rng.random() < p_evt:
                        pending.append((pos, rng.choice(["EGT_EVE", "EGT_EVE", "VIB_EVE", "CORE_EVE"])))
                for pos, kind in pending:
                    events.append(_event(row, pos, kind, rng))
                if rng.random() < 0.003:
                    events.append(_event(row, 0, rng.choice(["HARD_EVE", "OVW_EVE", "G_EVE"]), rng))
                flights.append(row)
                loc = dest
    return flights, events


def _event(row: dict, eng: int, kind: str, rng) -> dict:
    texts = {
        "EGT_EVE": "EGT por encima del umbral de vigilancia en despegue (dato simulado)",
        "VIB_EVE": "Vibración N1 elevada en crucero (dato simulado)",
        "CORE_EVE": "Desviación de parámetros del core (dato simulado)",
        "HARD_EVE": "Aterrizaje con aceleración vertical alta (dato simulado)",
        "OVW_EVE": "Sobrepeso detectado (dato simulado)",
        "G_EVE": "Aceleración G fuera de rango (dato simulado)",
    }
    ev = {k: 0 for k in ("FLAP_EVE", "ALT_EVE", "G_EVE", "OVW_EVE", "HARD_EVE", "LDG_EVE",
                         "EGT_EVE", "CORE_EVE", "VIB_EVE")}
    ev[kind] = 1
    return dict(ID_FLIGHTFILE=row["id_flightfile"], ID_FLIGHT=rng.randint(1000, 9000), ID_FLOTA=0,
                MATRICULA=row["matricula"], FECHA_VUELO=row["fecha"].strftime("%d/%m/%Y %H:%M"),
                ORIGEN=row["origen"], DESTINO=row["destino"], TXT_EVENT=texts[kind], ENG=eng,
                fecha_real=row["fecha"], id_avion=row["id_avion"], sn1=row["sn1"], sn2=row["sn2"], **ev)


# --------------------------------------------------------------------------- interfaz común
def aircraft_list() -> list[dict]:
    out = []
    for ac in AIRCRAFT:
        last = 10 ** 6
        out.append({**ac, "sn1": _sn_at(ac["id"], 1, last), "sn2": _sn_at(ac["id"], 2, last), "activo": "S"})
    return out


def fleet_engines() -> list[dict]:
    flights, _ = _data()
    agg: dict[str, dict] = {}
    for f in flights:
        for pos in (1, 2):
            sn = f[f"sn{pos}"]
            a = agg.setdefault(sn, dict(sn=sn, cycles=0, ft=0, first_date=f["fecha"], last_date=f["fecha"]))
            a["cycles"] += 1
            a["ft"] += f["ft"]
            if f["fecha"] >= a["last_date"]:
                a.update(last_date=f["fecha"], last_matricula=f["matricula"], last_pos=pos,
                         last_id_avion=f["id_avion"])
    return list(agg.values())


def _flight_cols(f: dict) -> dict:
    return {k: f[k] for k in ("id_vuelo", "id_avion", "matricula", "fecha", "origen", "destino", "ft")}


def engine_flights(sn: str) -> list[dict]:
    flights, _ = _data()
    return [dict(_flight_cols(f), pos=pos, sn=sn)
            for f in flights for pos in (1, 2) if f[f"sn{pos}"] == sn]


def aircraft_flights(id_avion: int) -> list[dict]:
    flights, _ = _data()
    return [dict(_flight_cols(f), sn1=f["sn1"], sn2=f["sn2"]) for f in flights if f["id_avion"] == id_avion]


def _match(kind, key, f, pos, desde, hasta_excl):
    d = f["fecha"].date()
    if not (desde <= d < hasta_excl):
        return False
    return f[f"sn{pos}"] == key if kind == "engine" else f["id_avion"] == int(key)


def series(kind: str, key, desde: date, hasta_excl: date) -> list[dict]:
    flights, _ = _data()
    common = ("id_flightfile", "id_vuelo", "matricula", "fecha", "origen", "destino", "tof_tat",
              "crz_tat", "crz_alt", "crz_mach", "fuel_o", "fuel_d", "ft")
    out = []
    for f in flights:
        for pos in (1, 2):
            if _match(kind, key, f, pos, desde, hasta_excl):
                p = {k: v for k, v in f[f"p{pos}"].items() if k != "oil_rate"}
                out.append(dict({k: f[k] for k in common}, pos=pos, sn=f[f"sn{pos}"], **p))
    return out


def oil(kind: str, key, desde: date, hasta_excl: date) -> list[dict]:
    flights, _ = _data()
    return [dict(fecha=f["fecha"], matricula=f["matricula"], id_flightfile=f["id_flightfile"], pos=pos,
                 sn=f[f"sn{pos}"], rate=f[f"p{pos}"]["oil_rate"], qty_start=None, qty_end=None,
                 flight_time=f["ft"])
            for f in flights for pos in (1, 2) if _match(kind, key, f, pos, desde, hasta_excl)]


def events(kind: str, key, matricula: str | None = None) -> list[dict]:
    _, evs = _data()
    if kind == "engine":
        return [e for e in evs if (e["ENG"] == 1 and e["sn1"] == key) or (e["ENG"] == 2 and e["sn2"] == key)]
    return [e for e in evs if e["MATRICULA"] == matricula or e["id_avion"] == int(key)]
