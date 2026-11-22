"""Lector de reportes ACMS en texto (A321 REPORT01/REPORT04, ATR REPORT02).

Los reportes son tablas de ancho fijo: una línea de cabecera con los nombres de columna y una o
varias líneas de datos que empiezan por un código de 2 caracteres (N1, S1, V3, F2...). Cada valor
se asigna a la columna de la cabecera que empieza en la misma posición.

Escalas (según los reportes):
  A321  EGT, N1, N2, TAT, T3: décimas (4061 -> 406.1)   MN: milésimas   EPR: milésimas
        FF: kg/h   GW: decenas de kg   VB1/VB2: décimas   "N" delante = negativo (N107 -> -10.7)
        EHRS/ECYC: horas y ciclos totales del motor
  ATR   valores con su punto decimal; ITT = temperatura entre turbinas (equivale a la EGT)
"""
import re
from datetime import datetime

_CODE = re.compile(r"^([A-Z][A-Z0-9]) (.*)$")
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def sn_key(sn) -> str:
    """Clave para emparejar nº de serie de distintas fuentes.

    'V16619' y '016619' -> '16619'  (V2500: el reporte pone 0 donde la BD pone V)
    'PCE-ED2124' y 'ED2124' -> 'ED2124'  (PW100: prefijo PCE opcional)
    """
    s = re.sub(r"[^A-Z0-9]", "", str(sn or "").upper())
    if s.startswith("PCE"):
        s = s[3:]
    elif s.startswith("PC"):
        s = s[2:]
    m = re.fullmatch(r"([A-Z]*)(\d+)", s)
    if not m:
        return s
    letters = "" if m.group(1) == "V" else m.group(1)
    return letters + (m.group(2).lstrip("0") or "0")


def num(raw, scale: float = 1.0):
    """'N107' -> -107*scale, '0804' -> 804*scale, '074.4' -> 74.4, '+19009' -> 19009."""
    if raw is None:
        return None
    s = str(raw).strip()
    neg = s[:1] in ("N", "-")
    s = s[1:] if s[:1] in ("N", "-", "+", "P") else s
    try:
        v = float(s)
    except ValueError:
        return None
    return round((-v if neg else v) * scale, 3)


def _tokens(line: str):
    return [(m.start(), m.group()) for m in re.finditer(r"\S+", line)]


def _assign(header, values) -> dict:
    """Asigna cada valor a la columna de cabecera que empieza en su posición (o la anterior)."""
    out = {}
    for pos, val in values:
        name = None
        for hpos, h in header:
            if hpos <= pos + 1:
                name = h
            else:
                break
        if name and name not in out:
            out[name] = val
    return out


def parse_header(text: str) -> dict:
    head = {}
    for line in text.split("\n"):
        if line.startswith("TEXT="):
            break
        if "=" in line:
            k, v = line.split("=", 1)
            head[k.strip()] = v.strip()
    return head


def parse_rows(text: str, coded_headers: bool) -> dict:
    """Devuelve {código_de_fila: {columna: valor_texto}}.

    coded_headers=False (A321): la cabecera es una línea que empieza por espacios.
    coded_headers=True  (ATR):  la cabecera es la fila con código X1 y los datos X2, X3...
    """
    body = text.split("TEXT=", 1)[-1]
    rows, header = {}, None
    for line in body.replace("\r", "").split("\n"):
        if not line.strip():
            continue
        m = _CODE.match(line)
        if coded_headers:
            if not m:
                continue
            code = m.group(1)
            if code.endswith("1"):
                header = [(p, t) for p, t in _tokens(line) if p >= 3]
                continue
        else:
            if not m:
                header = _tokens(line)
                continue
            code = m.group(1)
        if header is not None:
            values = [(p, t) for p, t in _tokens(line) if p >= 3]
            rows[code] = _assign(header, values)
    return rows


def _when(head: dict):
    d, t = head.get("DATE", ""), head.get("UTC", "")
    try:
        return datetime.strptime(d[:6] + (t + "000000")[:6], "%d%m%y%H%M%S")
    except ValueError:
        return None


# --------------------------------------------------------------------------- A321
def parse_a321(text: str) -> dict | None:
    text = text.replace("\r", "")
    head = parse_header(text)
    rows = parse_rows(text, coded_headers=False)
    rep = head.get("REPORT_NO") or ""
    tipo = "CRZ" if rep == "01" else "TOF" if rep == "04" else None
    fecha = _when(head)
    if not tipo or not fecha:
        return None
    cc, ce = rows.get("CC", {}), rows.get("CE", {})
    out = dict(
        fecha=fecha, tipo=tipo, matricula=(head.get("AC_TAIL") or "").lstrip(".") or cc.get("A/C"),
        origen=cc.get("FROM"), destino=cc.get("TO"), vuelo=cc.get("FLT"),
        tat=num(ce.get("TAT"), 0.1), alt=num(ce.get("ALT")), mach=num(ce.get("MN"), 0.001),
        gw=num(ce.get("GW"), 10), motores={},
    )
    for pos, esn_row in ((1, "EC"), (2, "EE")):
        e = rows.get(esn_row, {})
        perf = rows.get(f"N{pos}" if tipo == "CRZ" else f"S{pos}", {})
        oil = rows.get(f"V{pos}", {})
        vib = rows.get(f"V{pos + 2}", {})
        out["motores"][pos] = dict(
            esn=e.get("ESN"), horas=num(e.get("EHRS")), ciclos=num(e.get("ECYC")),
            egt=num(perf.get("EGT"), 0.1), n1=num(perf.get("N1"), 0.1), n2=num(perf.get("N2"), 0.1),
            ff=num(perf.get("FF")), epr=num(perf.get("EPR"), 0.001),
            op=num(oil.get("OIP")), ot=num(oil.get("OIT")),
            vib_n1=num(vib.get("VB1"), 0.1), vib_n2=num(vib.get("VB2"), 0.1),
        )
    return out


# --------------------------------------------------------------------------- ATR
def parse_atr02(text: str) -> dict | None:
    text = text.replace("\r", "")
    head = parse_header(text)
    rows = parse_rows(text, coded_headers=True)
    fecha = _when(head)
    if not fecha:
        return None
    e = rows.get("E2", {})
    out = dict(fecha=fecha, tipo="CRZ", matricula=None, origen=None, destino=None,
               vuelo=head.get("FLIGHT_NUMBER"), tat=num(e.get("TAT")), alt=num(e.get("ALT")),
               mach=None, gw=None, motores={})
    for pos in (1, 2):
        m = re.search(rf"^D{pos + 1}\s+ESN{pos}\s+(\S+)", text, re.M)
        f, g = rows.get(f"F{pos + 1}", {}), rows.get(f"G{pos + 1}", {})
        out["motores"][pos] = dict(
            esn=m.group(1) if m else None,
            horas=None, ciclos=None,
            egt=num(g.get("ITT")), n1=num(f.get("NL")), n2=num(g.get("NH")), ff=num(g.get("FF")),
            torque=num(f.get("TORQ")), np=num(f.get("NP")),
            op=None, ot=None, vib_n1=None, vib_n2=None,
        )
    return out
