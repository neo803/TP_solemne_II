
from __future__ import annotations
import re, requests
import pandas as pd
from typing import Optional
from bs4 import BeautifulSoup
import datetime as _dt

CHILEALERTA_ENDPOINT = "https://chilealerta.com/api/query"
GAEL_ENDPOINT = "https://api.gael.cloud/general/public/sismos"

_float_pat = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")
def _to_float(x):
    if x is None: return None
    s = str(x); m = _float_pat.search(s)
    if not m: return None
    return float(m.group(0).replace(",", "."))

def fetch_from_evtdb(pages: int = 1, timeout: int = 20) -> pd.DataFrame:
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
        if not next_link.startswith("http"):
            url = base.rstrip("/") + "/" + next_link.lstrip("/")
        else: url = next_link
    if not rows:
        return pd.DataFrame(columns=['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia'])
    df = pd.DataFrame(rows)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], utc=True, errors="coerce")
    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    return df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)

def fetch_from_csn(date: Optional[_dt.date] = None, timeout: int = 20) -> pd.DataFrame:
    if date is None:
        date = _dt.datetime.now(tz=pd.Timestamp.now(tz='America/Santiago').tz).date()
    y = date.strftime('%Y'); m = date.strftime('%m'); d = date.strftime('%Y%m%d')
    url = f"https://www.sismologia.cl/sismicidad/catalogo/{y}/{m}/{d}.html"
    r = requests.get(url, timeout=timeout); r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml'); text = soup.get_text('\n', strip=True)
    pat = re.compile(r"(?P<local>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?(?P<lugar>[^\n]+?)\s+(?P<utc>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<lat>-?\d+\.\d+)\s+\n\s*(?P<lon>-?\d+\.\d+)\s+(?P<prof>\d+)\s+km\s+(?P<mag>[\d\.]+)\s+[A-Za-z]+")
    rows = []
    for m in pat.finditer(text):
        rows.append({
            'fecha_local_str': m.group('local'),'fecha_utc_str': m.group('utc'),'referencia': m.group('lugar'),
            'latitud': float(m.group('lat')),'longitud': float(m.group('lon')),'profundidad': float(m.group('prof')),'magnitud': float(m.group('mag')),
        })
    if not rows: return pd.DataFrame(columns=['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia'])
    df = pd.DataFrame(rows)
    df['fecha_dt'] = pd.to_datetime(df['fecha_utc_str'], utc=True, errors="coerce")
    df['fecha_local'] = pd.to_datetime(df['fecha_local_str'], utc=False, errors="coerce").dt.tz_localize('America/Santiago')
    df['dia'] = df['fecha_local'].dt.date; df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    return df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)

def fetch_from_chilealerta(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(CHILEALERTA_ENDPOINT, timeout=timeout); r.raise_for_status(); data = r.json()
    if isinstance(data, list): raw = data
    elif isinstance(data, dict):
        for key in ["data","events","sismos","ultimos","resultados","result","features","earthquakes"]:
            v = data.get(key)
            if isinstance(v, list) and v: raw = v; break
        else: raw = [data]
    else: return pd.DataFrame()
    df = pd.json_normalize(raw)
    if df.empty: return df
    df['latitud'] = df.iloc[:,df.columns.str.contains('lat',case=False)].iloc[:,0].apply(_to_float)
    df['longitud'] = df.iloc[:,df.columns.str.contains('lon|long',case=False)].iloc[:,0].apply(_to_float)
    df['profundidad'] = df.iloc[:,df.columns.str.contains('prof|depth',case=False)].iloc[:,0].apply(_to_float)
    df['magnitud'] = df.iloc[:,df.columns.str.contains('mag',case=False)].iloc[:,0].apply(_to_float)
    datecol = df.columns[df.columns.str.contains('fecha|time|date',case=False)][0]
    df['fecha_dt'] = pd.to_datetime(df[datecol], utc=True, errors="coerce")
    df['fecha_local'] = df['fecha_dt'].dt.tz_convert("America/Santiago")
    df['referencia'] = df.iloc[:,0].astype(str)
    df['dia'] = df['fecha_local'].dt.date; df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    return df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)

def fetch_from_gael(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(GAEL_ENDPOINT, timeout=timeout); r.raise_for_status(); data = r.json()
    if not isinstance(data, list): return pd.DataFrame()
    df = pd.DataFrame([{k.lower():v for k,v in d.items()} for d in data])
    df['latitud'] = df['latitud'].apply(_to_float); df['longitud'] = df['longitud'].apply(_to_float)
    df['profundidad'] = df['profundidad'].apply(_to_float); df['magnitud'] = df['magnitud'].apply(_to_float)
    df['fecha_dt'] = pd.to_datetime(df['fecha'], utc=True, errors="coerce")
    df['fecha_local'] = df['fecha_dt'].dt.tz_convert("America/Santiago")
    df['referencia'] = df.get('referencia','')
    df['dia'] = df['fecha_local'].dt.date; df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    return df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)

def fetch_sismos(evtdb_pages:int=2, timeout: int = 20) -> pd.DataFrame:
    try:
        df = fetch_from_evtdb(pages=evtdb_pages, timeout=timeout)
        if not df.empty: return df
    except Exception: pass
    try:
        df = fetch_from_csn(timeout=timeout)
        if not df.empty: return df
    except Exception: pass
    try:
        df = fetch_from_chilealerta(timeout=timeout)
        if not df.empty: return df
    except Exception: pass
    return fetch_from_gael(timeout=timeout)

def filter_sismos(df: pd.DataFrame, mag_min: Optional[float]=None,
                  fecha_desde: Optional[pd.Timestamp]=None,
                  fecha_hasta: Optional[pd.Timestamp]=None,
                  region_keyword: str="") -> pd.DataFrame:
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
