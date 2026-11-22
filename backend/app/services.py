"""Lógica de negocio: horas/ciclos, paradas (C-check), instalaciones, eventos y salud."""
import json
import threading
import time
from datetime import date, datetime, timedelta
from statistics import mean

from . import config
from .reports import parse_a321, parse_atr02, sn_key

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


# --------------------------------------------------------------------------- reportes ACMS (A321 / ATR)
# Se leen una vez y después solo los nuevos (ID_REPORT mayor que el último leído).
_rep_store = {k: {"last": 0, "rows": [], "ts": 0.0} for k in ("a321", "atr")}
_rep_lock = threading.Lock()
_REP_FIELDS = ("egt", "n1", "n2", "ff", "op", "ot", "vib_n1", "vib_n2", "torque")


def report_rows(kind: str) -> list[dict]:
    """Filas tipo 'serie' (una por motor y reporte) sacadas de los reportes ACMS."""
    st = _rep_store[kind]
    with _rep_lock:
        if time.time() - st["ts"] < config.CACHE_SECONDS:
            return st["rows"]
        fetch, parse = (repo.a321_reports, parse_a321) if kind == "a321" else (repo.atr_reports, parse_atr02)
        for r in fetch(st["last"]):
            st["last"] = max(st["last"], int(r["id"]))
            raw = r["contenido"] or b""
            text = raw.decode("latin-1") if isinstance(raw, (bytes, bytearray)) else str(raw)
            try:
                p = parse(text)
            except Exception:  # un reporte mal formado no debe tumbar la aplicación
                p = None
            if not p:
                continue
            pre = "crz_" if p["tipo"] == "CRZ" else "tof_"
            for pos, m in p["motores"].items():
                if m.get("egt") is None and m.get("ff") is None:
                    continue
                row = dict(
                    fecha=p["fecha"], matricula=p["matricula"] or r["matricula"], id_avion=r["id_avion"],
                    origen=p["origen"], destino=p["destino"], id_vuelo=f"R{r['id']}", id_flightfile=None,
                    pos=pos, sn=m.get("esn"), sn_key=sn_key(m.get("esn")), ft=None,
                    fuente=f"{'A321' if kind == 'a321' else 'ATR'} {r['tipo']}",
                    acms_horas=m.get("horas"), acms_ciclos=m.get("ciclos"),
                )
                row[pre + "tat"] = p["tat"]
                if pre == "crz_":
                    row.update(crz_alt=p["alt"], crz_mach=p["mach"])
                for k in _REP_FIELDS:
                    if m.get(k) is not None:
                        row[pre + k] = m[k]
                st["rows"].append(row)
        st["rows"].sort(key=lambda x: x["fecha"])
        st["ts"] = time.time()
        return st["rows"]


def all_report_rows() -> list[dict]:
    return report_rows("a321") + report_rows("atr")


def _rep_for_engine(sn: str, desde: date, hasta_excl: date) -> list[dict]:
    k = sn_key(sn)
    return [r for r in all_report_rows() if r["sn_key"] == k and desde <= r["fecha"].date() < hasta_excl]


def _rep_for_aircraft(id_avion: int, desde: date, hasta_excl: date) -> list[dict]:
    return [r for r in all_report_rows()
            if r["id_avion"] is not None and int(r["id_avion"]) == int(id_avion)
            and desde <= r["fecha"].date() < hasta_excl]


def acms_counters(sn: str) -> dict | None:
    """Horas y ciclos del motor según su último reporte ACMS (solo A321).

    Estos contadores los lleva la unidad de adquisición del avión y pueden reiniciarse (cambio de
    unidad, reconfiguración...). Si el valor baja bruscamente se marca el reinicio y se da una
    estimación = valor antes del reinicio + valor actual. La interfaz lo muestra como estimación.
    """
    k = sn_key(sn)
    rows = [r for r in all_report_rows() if r["sn_key"] == k and r.get("acms_horas") is not None]
    if not rows:
        return None
    reinicio, prev = None, None
    for r in rows:  # ya ordenadas por fecha
        if prev and r["acms_horas"] < prev["acms_horas"] * 0.5:
            reinicio = dict(fecha=r["fecha"], antes_horas=prev["acms_horas"], antes_ciclos=prev["acms_ciclos"],
                            antes_fecha=prev["fecha"])
        prev = r
    last = rows[-1]
    out = dict(horas=last["acms_horas"], ciclos=last["acms_ciclos"], fecha=last["fecha"],
               matricula=last["matricula"], reinicio=reinicio)
    if reinicio:
        out["estimado_horas"] = reinicio["antes_horas"] + last["acms_horas"]
        out["estimado_ciclos"] = reinicio["antes_ciclos"] + (last["acms_ciclos"] or 0)
    return out


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
        # Horas y ciclos totales del motor según los reportes ACMS (A321), si existen
        for m in out:
            a = acms_counters(m["sn"])
            m["horas_acms"] = a["horas"] if a else None
            m["ciclos_acms"] = a["ciclos"] if a else None
            m["acms_reiniciado"] = bool(a and a["reinicio"])
        out.sort(key=lambda x: (x["montado_en"] is None, x["montado_en"] or "", x["posicion"] or 9))
        return out
    return cached("fleet", load)


def engine_flights(sn: str) -> list[dict]:
    """Historial completo de vuelos del motor (en caché: no depende del periodo elegido)."""
    return cached(("ef", sn), lambda: repo.engine_flights(sn))


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
    flights = engine_flights(sn)
    ser = repo.series("engine", sn, fetch_from, hasta_excl) + _rep_for_engine(sn, fetch_from, hasta_excl)
    oil_rows = repo.oil("engine", sn, fetch_from, hasta_excl)
    evs = cached(("ev_e", sn), lambda: normalize_events(repo.events("engine", sn)))
    cur = current_install(sn)
    if cur is None and flights:
        last = max(flights, key=lambda f: to_dt(f["fecha"]))
        ac = aircraft_by_id(last["id_avion"])
        cur = dict(id_avion=last["id_avion"], matricula=last["matricula"], pos=last["pos"],
                   tipo=ac["tipo"] if ac else "OTRO", desmontado=True)
    resumen = summarize(flights)
    resumen["acms"] = acms_counters(sn)
    return dict(
        sn=sn, actual=cur, resumen=resumen, instalaciones=installations(flights),
        salud=health(ser, oil_rows, evs),
        series=_in_range(ser, desde, hasta_excl), aceite=_in_range(oil_rows, desde, hasta_excl),
        eventos=evs, rango=dict(desde=desde, hasta=hasta),
    )


def aircraft_detail(id_avion: int, desde: date | None, hasta: date | None) -> dict | None:
    ac = aircraft_by_id(id_avion)
    if ac is None:
        return None
    desde, hasta, fetch_from, hasta_excl = _ranges(desde, hasta)
    flights = cached(("af", id_avion), lambda: repo.aircraft_flights(id_avion))
    ser = (repo.series("aircraft", id_avion, fetch_from, hasta_excl)
           + _rep_for_aircraft(id_avion, fetch_from, hasta_excl))
    oil_rows = repo.oil("aircraft", id_avion, fetch_from, hasta_excl)
    evs = cached(("ev_a", id_avion), lambda: normalize_events(repo.events("aircraft", id_avion, ac["matricula"])))
    motores = []
    for pos in (1, 2):
        sn = (ac.get(f"sn{pos}") or "").strip()
        if not sn:
            continue
        k = sn_key(sn)
        resumen = summarize(engine_flights(sn))
        resumen["acms"] = acms_counters(sn)
        motores.append(dict(
            pos=pos, sn=sn, resumen=resumen,
            salud=health([r for r in ser if sn_key(r["sn"]) == k], [r for r in oil_rows if sn_key(r["sn"]) == k],
                         [e for e in evs if sn_key(e["sn"]) == k]),
        ))
    return dict(
        avion=ac, resumen=summarize(flights), motores=motores,
        series=_in_range(ser, desde, hasta_excl), aceite=_in_range(oil_rows, desde, hasta_excl),
        eventos=evs, rango=dict(desde=desde, hasta=hasta),
    )
