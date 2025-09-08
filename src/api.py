
from __future__ import annotations
import re, requests
import pandas as pd
import numpy as _np
from typing import Optional
from bs4 import BeautifulSoup
import datetime as _dt

CHILEALERTA_ENDPOINT = "https://chilealerta.com/api/query"
GAEL_ENDPOINT = "https://api.gael.cloud/general/public/sismos"

STANDARD_COLS = ['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']

_float_pat = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")
def _to_float(x):
    if x is None: return None
    s = str(x); m = _float_pat.search(s)
    if not m: return None
    return float(m.group(0).replace(",", "."))

def _ensure_standard(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLS)
    for c in STANDARD_COLS:
        if c not in df.columns:
            df[c] = _np.nan
    return df[STANDARD_COLS].sort_values('fecha_dt', ascending=False).reset_index(drop=True)

def fetch_from_evtdb(pages: int = 2, timeout: int = 20) -> pd.DataFrame:
    base = "https://evtdb.csn.uchile.cl/"
    rows = []; url = base
    for _ in range(max(1, int(pages))):
        r = requests.get(url, timeout=timeout); r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a'):
            txt = a.get_text(strip=True)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", txt):
                tail = a.find_parent().get_text(" ", strip=True)
                m = re.search(rf"{re.escape(txt)}\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(\d+)\s+(\d+(?:\.\d+)?)", tail)
                if m:
                    rows.append({
                        "fecha": txt,
                        "latitud": float(m.group(1)),
                        "longitud": float(m.group(2)),
                        "profundidad": float(m.group(3)),
                        "magnitud": float(m.group(4)),
                        "referencia": "",
                    })
        next_link = None
        for a in soup.find_all('a'):
            if a.get_text(strip=True) == "[Siguiente]":
                next_link = a.get('href'); break
        if not next_link: break
        url = next_link if next_link.startswith("http") else (base.rstrip("/") + "/" + next_link.lstrip("/"))
    if not rows:
        return _ensure_standard(pd.DataFrame())
    df = pd.DataFrame(rows)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], utc=True, errors="coerce")
    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    df["referencia"] = df.get("referencia", "")
    return _ensure_standard(df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']])

def fetch_from_csn(date: Optional[_dt.date] = None, timeout: int = 20) -> pd.DataFrame:  # noqa: C901
    if date is None:
        date = _dt.datetime.now(tz=pd.Timestamp.now(tz='America/Santiago').tz).date()
    y = date.strftime('%Y'); m = date.strftime('%m'); d = date.strftime('%Y%m%d')
    url = f"https://www.sismologia.cl/sismicidad/catalogo/{y}/{m}/{d}.html"
    r = requests.get(url, timeout=timeout); r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml'); text = soup.get_text('\n', strip=True)

    pat = re.compile(
        r"(?P<local>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
        r"(?P<lugar>[^\n]+?)\s+(?P<utc>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
        r"(?P<lat>-?\d+\.\d+)\s+\n\s*(?P<lon>-?\d+\.\d+)\s+"
        r"(?P<prof>\d+)\s+km\s+(?P<mag>[\d\.]+)\s+[A-Za-z]+"
    )
    rows = []
    for m in pat.finditer(text):
        rows.append({
            'fecha_local_str': m.group('local'), 'fecha_utc_str': m.group('utc'),
            'referencia': m.group('lugar'),
            'latitud': float(m.group('lat')), 'longitud': float(m.group('lon')),
            'profundidad': float(m.group('prof')), 'magnitud': float(m.group('mag')),
        })

    if not rows:
        try:
            tables = pd.read_html(url, flavor='lxml')
            for t in tables:
                cols = [str(c).strip().lower() for c in t.columns]
                if any("lat" in c for c in cols) and any(("lon" in c or "long" in c or "longitud" in c) for c in cols):
                    def pick(opts):
                        for o in opts:
                            for j, c in enumerate(cols):
                                if o in c: return t.columns[j]
                        return None
                    col_lat = pick(["latitud","lat"]); col_lon = pick(["longitud","lon","long"])
                    col_prof = pick(["profundidad","prof","depth"]); col_mag = pick(["magnitud","mag"])
                    col_fecha = pick(["fecha","utc","datetime","hora"])
                    df = pd.DataFrame()
                    if col_fecha is not None: df['fecha_dt'] = pd.to_datetime(t[col_fecha], utc=True, errors='coerce')
                    if col_lat is not None: df['latitud'] = pd.to_numeric(t[col_lat], errors='coerce')
                    if col_lon is not None: df['longitud'] = pd.to_numeric(t[col_lon], errors='coerce')
                    if col_prof is not None: df['profundidad'] = pd.to_numeric(t[col_prof], errors='coerce')
                    if col_mag is not None: df['magnitud'] = pd.to_numeric(t[col_mag], errors='coerce')
                    df['fecha_local'] = df.get('fecha_dt', pd.NaT).dt.tz_convert('America/Santiago')
                    df['referencia'] = ""
                    return _ensure_standard(df)
        except Exception:
            pass
        return _ensure_standard(pd.DataFrame())

    df = pd.DataFrame(rows)
    df['fecha_dt'] = pd.to_datetime(df['fecha_utc_str'], utc=True, errors="coerce")
    df['fecha_local'] = pd.to_datetime(df['fecha_local_str'], utc=False, errors="coerce").dt.tz_localize('America/Santiago')
    df['dia'] = df['fecha_local'].dt.date
    df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    return _ensure_standard(df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']])

def fetch_from_chilealerta(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(CHILEALERTA_ENDPOINT, timeout=timeout); r.raise_for_status()
    data = r.json()
    if isinstance(data, list): raw = data
    elif isinstance(data, dict):
        raw = None
        for key in ["data","events","sismos","ultimos","resultados","result","features","earthquakes"]:
            v = data.get(key)
            if isinstance(v, list) and v: raw = v; break
        if raw is None: raw = [data]
    else:
        return _ensure_standard(pd.DataFrame())
    df = pd.json_normalize(raw)
    if df.empty: return _ensure_standard(df)

    def pickcol(patterns):
        for p in patterns:
            cols = [c for c in df.columns if p.lower() in c.lower()]
            if cols: return cols[0]
        return None
    col_lat = pickcol(["lat"]); col_lon = pickcol(["lon","long"])
    col_prof = pickcol(["prof","depth"]); col_mag = pickcol(["mag"])
    col_fecha = pickcol(["fecha","time","date"])

    out = pd.DataFrame()
    if col_fecha: out['fecha_dt'] = pd.to_datetime(df[col_fecha], utc=True, errors="coerce")
    if col_lat:   out['latitud'] = df[col_lat].apply(_to_float)
    if col_lon:   out['longitud'] = df[col_lon].apply(_to_float)
    if col_prof:  out['profundidad'] = df[col_prof].apply(_to_float)
    if col_mag:   out['magnitud'] = df[col_mag].apply(_to_float)
    out['fecha_local'] = out.get('fecha_dt', pd.NaT).dt.tz_convert("America/Santiago")
    out['referencia'] = ""
    out['dia'] = out['fecha_local'].dt.date
    out['hora'] = out['fecha_local'].dt.strftime('%H:%M')
    return _ensure_standard(out)

def fetch_from_gael(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(GAEL_ENDPOINT, timeout=timeout); r.raise_for_status()
    data = r.json()
    if not isinstance(data, list): return _ensure_standard(pd.DataFrame())
    df = pd.DataFrame([{k.lower(): v for k, v in d.items()} for d in data])
    for k in ["latitud","longitud","profundidad","magnitud"]:
        if k in df.columns:
            df[k] = df[k].apply(_to_float)
    df['fecha_dt'] = pd.to_datetime(df.get('fecha', _np.nan), utc=True, errors="coerce")
    df['fecha_local'] = df['fecha_dt'].dt.tz_convert("America/Santiago")
    df['referencia'] = df.get('referencia', "")
    df['dia'] = df['fecha_local'].dt.date
    df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    return _ensure_standard(df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']])

def fetch_sismos(evtdb_pages: int = 2, timeout: int = 20) -> pd.DataFrame:
    try:
        df = fetch_from_evtdb(pages=evtdb_pages, timeout=timeout)
        if not df.empty: return df
    except Exception:
        pass
    try:
        df = fetch_from_csn(timeout=timeout)
        if not df.empty: return df
    except Exception:
        pass
    try:
        df = fetch_from_chilealerta(timeout=timeout)
        if not df.empty: return df
    except Exception:
        pass
    return fetch_from_gael(timeout=timeout)

def filter_sismos(df: pd.DataFrame,
                  mag_min: Optional[float] = None,
                  fecha_desde: Optional[pd.Timestamp] = None,
                  fecha_hasta: Optional[pd.Timestamp] = None,
                  region_keyword: str = "") -> pd.DataFrame:
    out = df.copy()
    if mag_min is not None:
        out = out[(out["magnitud"].fillna(-999) >= mag_min)]
    if fecha_desde is not None:
        out = out[out["fecha_dt"] >= fecha_desde]
    if fecha_hasta is not None:
        out = out[out["fecha_dt"] <= fecha_hasta]
    if region_keyword:
        rk = region_keyword.strip().lower()
        out = out[out["referencia"].astype(str).str.lower().str.contains(rk, na=False)]
    return out.reset_index(drop=True)
