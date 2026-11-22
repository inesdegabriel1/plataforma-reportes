"""Lógica de negocio: horas/ciclos, paradas (C-check), instalaciones, eventos y salud."""
import json
import threading
import time
from datetime import date, datetime, timedelta
from statistics import mean

from . import config

if config.DEMO:
    from . import repo_demo as repo
else:
    from . import repo_sql as repo

FT_UNIT = getattr(repo, "FT_UNIT", config.FLIGHT_TIME_UNIT)
RULES = json.loads((config.BACKEND_DIR / "app" / "health_rules.json").read_text(encoding="utf-8"))

EVENT_TYPES = {
    "EGT_EVE": "EGT", "CORE_EVE": "Core", "VIB_EVE": "Vibración", "FLAP_EVE": "Flaps",
    "ALT_EVE": "Altitud", "G_EVE": "Aceleración G", "OVW_EVE": "Sobrepeso",
    "HARD_EVE": "Aterrizaje duro", "LDG_EVE": "Aterrizaje",
}
ENGINE_EVENT_TYPES = {"EGT_EVE", "CORE_EVE", "VIB_EVE"}

# --------------------------------------------------------------------------- caché simple
_cache: dict = {}
_cache_lock = threading.Lock()


def cached(key, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < config.CACHE_SECONDS:
            return hit[1]
    val = fn()
    with _cache_lock:
        _cache[key] = (now, val)
    return val


# --------------------------------------------------------------------------- utilidades
def hours(ft) -> float:
    ft = float(ft or 0)
    return ft / 3600 if FT_UNIT.startswith("sec") else ft / 60


def to_dt(x):
    if x is None or isinstance(x, datetime):
        return x
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day)
    return parse_date(str(x))


def parse_date(s: str | None):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def fleet_type(flota: str | None, variante: str | None = None) -> str:
    s = f"{flota or ''} {variante or ''}".upper()
    if "ATR" in s:
        return "ATR"
    if "A32" in s or "A3" in s or "AIRBUS" in s:
        return "A321"
    if "757" in s:
        return "B757"
    if "737" in s:
        return "B737"
    if s.strip().startswith("MD") or "MD-8" in s or "MD8" in s:
        return "MD"
    return "OTRO"


def num(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- maestros
def aircraft() -> list[dict]:
    def load():
        rows = repo.aircraft_list()
        for r in rows:
            r["tipo"] = fleet_type(r.get("flota"), r.get("variante"))
        return rows
    return cached("aircraft", load)


def aircraft_by_id(id_avion: int) -> dict | None:
    return next((a for a in aircraft() if int(a["id"]) == int(id_avion)), None)


def current_install(sn: str) -> dict | None:
    for a in aircraft():
        for pos in (1, 2):
            if (a.get(f"sn{pos}") or "").strip() == sn:
                return dict(id_avion=a["id"], matricula=a["matricula"], pos=pos, tipo=a["tipo"])
    return None


def fleet() -> list[dict]:
    def load():
        ac = {int(a["id"]): a for a in aircraft()}
        now = datetime.now()
        out = []
        for r in repo.fleet_engines():
            cur = current_install(r["sn"])
            last_ac = ac.get(int(r["last_id_avion"])) if r.get("last_id_avion") else None
            last = to_dt(r["last_date"])
            out.append(dict(
                sn=r["sn"], horas=round(hours(r["ft"]), 1), ciclos=int(r["cycles"]),
                primer_vuelo=to_dt(r["first_date"]), ultimo_vuelo=last,
                dias_sin_volar=(now - last).days if last else None,
                ultimo_avion=r.get("last_matricula"), ultima_pos=int(r["last_pos"]) if r.get("last_pos") else None,
                montado_en=cur["matricula"] if cur else None, posicion=cur["pos"] if cur else None,
                id_avion=cur["id_avion"] if cur else (int(r["last_id_avion"]) if r.get("last_id_avion") else None),
                tipo=(cur["tipo"] if cur else (last_ac["tipo"] if last_ac else "OTRO")),
            ))
        out.sort(key=lambda x: (x["montado_en"] is None, x["montado_en"] or "", x["posicion"] or 9))
        return out
    return cached("fleet", load)


# --------------------------------------------------------------------------- utilización
def compute_stops(dates: list[datetime]) -> list[dict]:
    stops = []
    for prev, nxt in zip(dates, dates[1:]):
        gap = (nxt - prev).total_seconds() / 86400
        if gap > config.STOP_DAYS:
            stops.append(dict(desde=prev, hasta=nxt, dias=int(gap)))
    return stops


def summarize(flights: list[dict]) -> dict:
    flights = sorted((dict(f, fecha=to_dt(f["fecha"])) for f in flights if f.get("fecha")),
                     key=lambda f: f["fecha"])
    now = datetime.now()
    d30, d365 = now - timedelta(days=30), now - timedelta(days=365)
    stops = compute_stops([f["fecha"] for f in flights])
    last_stop = stops[-1] if stops else None
    since = [f for f in flights if last_stop and f["fecha"] >= last_stop["hasta"]]

    def h(fs):
        return round(sum(hours(f["ft"]) for f in fs), 1)

    last = flights[-1]["fecha"] if flights else None
    return dict(
        horas_totales=h(flights), ciclos_totales=len(flights),
        horas_30d=h([f for f in flights if f["fecha"] >= d30]),
        ciclos_30d=sum(1 for f in flights if f["fecha"] >= d30),
        horas_12m=h([f for f in flights if f["fecha"] >= d365]),
        ciclos_12m=sum(1 for f in flights if f["fecha"] >= d365),
        primer_vuelo=flights[0]["fecha"] if flights else None, ultimo_vuelo=last,
        dias_sin_volar=(now - last).days if last else None,
        paradas=stops, ultima_parada=last_stop,
        horas_desde_ultima_parada=h(since) if last_stop else None,
        ciclos_desde_ultima_parada=len(since) if last_stop else None,
    )


def installations(flights: list[dict]) -> list[dict]:
    segs = []
    for f in sorted(flights, key=lambda f: to_dt(f["fecha"])):
        key = (f["id_avion"], f["pos"])
        if not segs or segs[-1]["_key"] != key:
            segs.append(dict(_key=key, id_avion=f["id_avion"], matricula=f["matricula"], pos=f["pos"],
                             desde=to_dt(f["fecha"]), hasta=to_dt(f["fecha"]), ciclos=0, horas=0.0))
        s = segs[-1]
        s["hasta"] = to_dt(f["fecha"])
        s["ciclos"] += 1
        s["horas"] += hours(f["ft"])
    for s in segs:
        s.pop("_key")
        s["horas"] = round(s["horas"], 1)
    return segs


# --------------------------------------------------------------------------- eventos
def normalize_events(rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        eng = int(r["ENG"]) if r.get("ENG") is not None else None
        fecha = to_dt(r.get("fecha_real")) or parse_date(r.get("FECHA_VUELO"))
        tipos = [k for k in EVENT_TYPES if (r.get(k) or 0) > 0]
        key = (r.get("ID_FLIGHTFILE"), eng, r.get("TXT_EVENT"), tuple(tipos))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(
            fecha=fecha, fecha_texto=r.get("FECHA_VUELO"), matricula=r.get("MATRICULA"),
            origen=r.get("ORIGEN"), destino=r.get("DESTINO"), motor=eng,
            sn=r.get(f"sn{eng}") if eng in (1, 2) else None,
            tipos=[EVENT_TYPES[k] for k in tipos],
            de_motor=any(k in ENGINE_EVENT_TYPES for k in tipos),
            texto=r.get("TXT_EVENT"), id_flightfile=r.get("ID_FLIGHTFILE"),
        ))
    out.sort(key=lambda e: e["fecha"] or datetime.min, reverse=True)
    return out


# --------------------------------------------------------------------------- salud
def _trend(rows: list[dict], field: str):
    """(media últimos N vuelos, media del periodo de referencia) o None si faltan datos."""
    now = datetime.now()
    ref_from = now - timedelta(days=RULES["referencia_desde_dias"])
    ref_to = now - timedelta(days=RULES["referencia_hasta_dias"])
    pts = [(to_dt(r["fecha"]), num(r.get(field))) for r in rows]
    pts = sorted((p for p in pts if p[0] and p[1] is not None), key=lambda p: p[0])
    n_rec = RULES["vuelos_recientes"]
    recent = [v for d, v in pts[-n_rec:] if d > ref_to]
    base = [v for d, v in pts if ref_from <= d < ref_to]
    if len(recent) < n_rec // 2 or len(base) < RULES["minimo_vuelos_referencia"]:
        return None
    return mean(recent), mean(base)


def health(series_rows: list[dict], oil_rows: list[dict], events: list[dict]) -> dict:
    """Semáforo por motor. Compara los últimos N vuelos con los N anteriores (referencia)."""
    level = 0
    reasons = []
    names = ["verde", "ambar", "rojo"]

    def bump(lv, msg):
        nonlocal level
        level = max(level, lv)
        reasons.append(dict(nivel=names[lv], texto=msg))

    rows = series_rows
    for field, label, amb, red in (
        ("crz_egt", "EGT crucero", RULES["egt_crucero_delta_ambar"], RULES["egt_crucero_delta_rojo"]),
        ("tof_egt", "EGT despegue", RULES["egt_despegue_delta_ambar"], RULES["egt_despegue_delta_rojo"]),
    ):
        t = _trend(rows, field)
        if t is None:
            reasons.append(dict(nivel="sin_datos", texto=f"{label}: sin datos suficientes"))
            continue
        delta = t[0] - t[1]
        lv = 2 if delta >= red else 1 if delta >= amb else 0
        bump(lv, f"{label}: {delta:+.1f} °C respecto a la referencia")

    t = _trend(oil_rows, "rate")
    if t is None or not t[1]:
        reasons.append(dict(nivel="sin_datos", texto="Consumo de aceite: sin datos suficientes"))
    else:
        ratio = t[0] / t[1]
        lv = 2 if ratio >= RULES["aceite_ratio_rojo"] else 1 if ratio >= RULES["aceite_ratio_ambar"] else 0
        bump(lv, f"Consumo de aceite: ×{ratio:.2f} respecto a la referencia")

    since = datetime.now() - timedelta(days=RULES["eventos_dias"])
    n_ev = sum(1 for e in events if e["de_motor"] and e["fecha"] and e["fecha"] >= since)
    lv = 2 if n_ev >= RULES["eventos_rojo"] else 1 if n_ev >= RULES["eventos_ambar"] else 0
    bump(lv, f"{n_ev} evento(s) de motor en los últimos {RULES['eventos_dias']} días")

    has_data = any(r["nivel"] != "sin_datos" for r in reasons[:-1])
    return dict(estado=names[level] if has_data or n_ev else "sin_datos", motivos=reasons)


# --------------------------------------------------------------------------- detalle
def _ranges(desde: date | None, hasta: date | None):
    hasta = hasta or date.today()
    desde = desde or (hasta - timedelta(days=365))
    fetch_from = min(desde, date.today() - timedelta(days=365))  # la salud usa siempre el último año
    return desde, hasta, fetch_from, hasta + timedelta(days=1)


def _in_range(rows, desde, hasta_excl):
    out = []
    for r in rows:
        if not (desde <= to_dt(r["fecha"]).date() < hasta_excl):
            continue
        if "fuel_o" in r:  # combustible consumido por vuelo y por hora (nivel avión)
            fo, fd, h = num(r.get("fuel_o")), num(r.get("fuel_d")), hours(r.get("ft"))
            used = fo - fd if fo is not None and fd is not None and fo > fd else None
            r = dict(r, fuel_used=used, fuel_h=round(used / h, 1) if used and h > 0.2 else None)
        out.append(r)
    return out


def engine_detail(sn: str, desde: date | None, hasta: date | None) -> dict:
    desde, hasta, fetch_from, hasta_excl = _ranges(desde, hasta)
    flights = repo.engine_flights(sn)
    ser = repo.series("engine", sn, fetch_from, hasta_excl)
    oil_rows = repo.oil("engine", sn, fetch_from, hasta_excl)
    evs = normalize_events(repo.events("engine", sn))
    cur = current_install(sn)
    if cur is None and flights:
        last = max(flights, key=lambda f: to_dt(f["fecha"]))
        ac = aircraft_by_id(last["id_avion"])
        cur = dict(id_avion=last["id_avion"], matricula=last["matricula"], pos=last["pos"],
                   tipo=ac["tipo"] if ac else "OTRO", desmontado=True)
    return dict(
        sn=sn, actual=cur, resumen=summarize(flights), instalaciones=installations(flights),
        salud=health(ser, oil_rows, evs),
        series=_in_range(ser, desde, hasta_excl), aceite=_in_range(oil_rows, desde, hasta_excl),
        eventos=evs, rango=dict(desde=desde, hasta=hasta),
    )


def aircraft_detail(id_avion: int, desde: date | None, hasta: date | None) -> dict | None:
    ac = aircraft_by_id(id_avion)
    if ac is None:
        return None
    desde, hasta, fetch_from, hasta_excl = _ranges(desde, hasta)
    flights = repo.aircraft_flights(id_avion)
    ser = repo.series("aircraft", id_avion, fetch_from, hasta_excl)
    oil_rows = repo.oil("aircraft", id_avion, fetch_from, hasta_excl)
    evs = normalize_events(repo.events("aircraft", id_avion, ac["matricula"]))
    motores = []
    for pos in (1, 2):
        sn = (ac.get(f"sn{pos}") or "").strip()
        if not sn:
            continue
        motores.append(dict(
            pos=pos, sn=sn, resumen=summarize(repo.engine_flights(sn)),
            salud=health([r for r in ser if r["sn"] == sn], [r for r in oil_rows if r["sn"] == sn],
                         [e for e in evs if e["sn"] == sn]),
        ))
    return dict(
        avion=ac, resumen=summarize(flights), motores=motores,
        series=_in_range(ser, desde, hasta_excl), aceite=_in_range(oil_rows, desde, hasta_excl),
        eventos=evs, rango=dict(desde=desde, hasta=hasta),
    )
