
from __future__ import annotations
import re
import requests
import pandas as pd
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import datetime as _dt

CHILEALERTA_ENDPOINT = "https://chilealerta.com/api/query"
GAEL_ENDPOINT = "https://api.gael.cloud/general/public/sismos"

_float_pat = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")

def _to_float(x):
    if x is None:
        return None
    s = str(x)
    m = _float_pat.search(s)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    # Map possible keys to standard ones
    colmap = {
        "fecha": ["fecha","fechautc","time","tiempo","timestamp","datetime","date"],
        "magnitud": ["magnitud","mag","magnitude","ml","mw"],
        "profundidad": ["profundidad","prof","depth","z"],
        "latitud": ["latitud","lat","latitude","y"],
        "longitud": ["longitud","lon","long","lng","longitude","x"],
        "referencia": ["referencia","referenciageografica","ref","refgeografica","lugar","place","title","location"],
    }
    def first_match(cols, columns):
        for c in cols:
            if c in columns:
                return c
        return None
    columns_lower = [c.lower() for c in df.columns]
    mapping = {}
    for k, cand in colmap.items():
        idx = first_match(cand, columns_lower)
        if idx is None:
            df[k] = None
        else:
            src = df.columns[columns_lower.index(idx)]
            df[k] = df[src]

    # Robust numeric parse
    for k in ["magnitud","profundidad","latitud","longitud"]:
        df[k] = df[k].apply(_to_float)

    # Date parse
    def parse_fecha(s):
        try:
            return pd.to_datetime(s, utc=True, errors="coerce")
        except Exception:
            return pd.NaT
    df["fecha_dt"] = df["fecha"].apply(parse_fecha)
    df = df.dropna(subset=["fecha_dt"]).copy()

    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    df["referencia"] = df["referencia"].astype(str).fillna("")
    return df.sort_values("fecha_dt", ascending=False).reset_index(drop=True)

def fetch_from_chilealerta(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(CHILEALERTA_ENDPOINT, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # The API may return a dict containing a list under various keys; try common patterns
    # If it's already a list of events, use it directly.
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        # candidates: 'data', 'events', 'ultimos', 'sismos', 'resultados', etc.
        for key in ["data","events","sismos","ultimos","resultados","result","features","earthquakes"]:
            v = data.get(key)
            if isinstance(v, list) and len(v) > 0:
                raw = v
                break
        else:
            # If the dict looks like a single event, wrap it
            raw = [data]
    else:
        raise ValueError("Respuesta inesperada de chilealerta.com")
    df = pd.json_normalize(raw)
    return _normalize_df(df)

def fetch_from_gael(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(GAEL_ENDPOINT, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError("La API de GAEL no devolvió una lista de eventos.")
    df = pd.json_normalize([{k.lower(): v for k, v in d.items()} for d in data])
    return _normalize_df(df)





def fetch_from_evtdb(pages: int = 1, timeout: int = 20) -> pd.DataFrame:
    """Scrapea https://evtdb.csn.uchile.cl/ (registro de eventos significativos).
    Extrae columnas: fecha (UTC), lat, lon, profundidad, magnitud. Permite recorrer N páginas.
    """
    base = "https://evtdb.csn.uchile.cl/"
    rows = []
    url = base
    for _ in range(max(1, int(pages))):
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')
        # Buscar filas bajo el bloque 'Registro de Eventos Significativos'
        # Formato: <a>fecha</a>  lat  lon  prof  mag
        # Mejor: capturar todos los enlaces que parecen fechas y luego leer los números que le siguen
        candidates = soup.find_all('a')
        for a in candidates:
            txt = a.get_text(strip=True)
            # fecha UTC como 'YYYY-MM-DD HH:MM:SS'
            if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", txt):
                # tomar los siguientes textos cercanos con números
                tail = a.find_parent().get_text(" ", strip=True)
                # construir una línea que contenga fecha y los números
                m = re.search(rf"{re.escape(txt)}\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(\d+)\s+(\d+(?:\.\d+)?)", tail)
                if m:
                    rows.append({
                        "fecha": txt,
                        "latitud": float(m.group(1)),
                        "longitud": float(m.group(2)),
                        "profundidad": float(m.group(3)),
                        "magnitud": float(m.group(4)),
                        "referencia": "",  # EVDB no muestra lugar aquí, queda vacío
                    })
        # paginación: enlace con texto "[Siguiente]"
        next_link = None
        for a in soup.find_all('a'):
            if a.get_text(strip=True) == "[Siguiente]":
                next_link = a.get('href')
                break
        if not next_link:
            break
        if not next_link.startswith("http"):
            url = base.rstrip("/") + "/" + next_link.lstrip("/")
        else:
            url = next_link

    if not rows:
        return pd.DataFrame(columns=['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia'])

    df = pd.DataFrame(rows)
    df["fecha_dt"] = pd.to_datetime(df["fecha"], utc=True, errors="coerce")
    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    return df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)


def fetch_from_csn(date: Optional[_dt.date] = None, timeout: int = 20) -> pd.DataFrame:
    """Scrapea el catálogo diario del CSN (sismologia.cl) y devuelve DataFrame normalizado.
    Estructura del HTML: líneas con Fecha Local / Lugar, Fecha UTC, Latitud, Longitud, Profundidad, Magnitud.
    """
    if date is None:
        # Usamos la fecha local de Chile
        date = _dt.datetime.now(tz=pd.Timestamp.now(tz='America/Santiago').tz).date()
    y = date.strftime('%Y'); m = date.strftime('%m'); d = date.strftime('%Y%m%d')
    url = f"https://www.sismologia.cl/sismicidad/catalogo/{y}/{m}/{d}.html"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    text = soup.get_text('\n', strip=True)

    # Regex que captura un bloque por evento: Local, Lugar, UTC, Lat, Lon, Prof km, Mag y unidad
    pat = re.compile(
        r"(?P<local>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?"
        r"(?P<lugar>[^\n]+?)\s+(?P<utc>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
        r"(?P<lat>-?\d+\.\d+)\s+\n\s*(?P<lon>-?\d+\.\d+)\s+"
        r"(?P<prof>\d+)\s+km\s+(?P<mag>[\d\.]+)\s+[A-Za-z]+"
    )

    rows = []
    for m in pat.finditer(text):
        rows.append({
            'fecha_local_str': m.group('local'),
            'fecha_utc_str': m.group('utc'),
            'referencia': m.group('lugar'),
            'latitud': float(m.group('lat')),
            'longitud': float(m.group('lon')),
            'profundidad': float(m.group('prof')),
            'magnitud': float(m.group('mag')),
        })

    if not rows:
        return pd.DataFrame(columns=['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia'])

    df = pd.DataFrame(rows)
    # Fechas
    df['fecha_dt'] = pd.to_datetime(df['fecha_utc_str'], utc=True, errors='coerce')
    df['fecha_local'] = pd.to_datetime(df['fecha_local_str'], utc=False, errors='coerce').dt.tz_localize('America/Santiago')
    # Derivadas
    df['dia'] = df['fecha_local'].dt.date
    df['hora'] = df['fecha_local'].dt.strftime('%H:%M')
    # Orden
    df = df[['fecha_dt','fecha_local','magnitud','profundidad','latitud','longitud','referencia']].sort_values('fecha_dt', ascending=False).reset_index(drop=True)
    return df




def fetch_sismos(timeout: int = 20) -> pd.DataFrame:
    # 1) EVTD B (eventos significativos, con lat/lon) con 1-2 páginas
    try:
        df = fetch_from_evtdb(pages=2, timeout=timeout)
        if not df.empty:
            return df
    except Exception:
        pass
    # 2) CSN diario
    try:
        df = fetch_from_csn(timeout=timeout)
        if not df.empty:
            return df
    except Exception:
        pass
    # 3) ChileAlerta
    try:
        df = fetch_from_chilealerta(timeout=timeout)
        if not df.empty:
            return df
    except Exception:
        pass
    # 4) GAEL
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
