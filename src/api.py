
from __future__ import annotations
import re
import requests
import pandas as pd
from typing import Optional, List, Dict, Any

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

def fetch_sismos(timeout: int = 20) -> pd.DataFrame:
    # Try chilealerta first, fall back to GAEL
    try:
        df = fetch_from_chilealerta(timeout=timeout)
        if not df.empty:
            return df
    except Exception:
        pass
    # fallback
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
