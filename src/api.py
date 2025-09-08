
from __future__ import annotations
import re
import requests
import pandas as pd
from typing import Optional

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

def fetch_sismos(timeout: int = 20) -> pd.DataFrame:
    r = requests.get(GAEL_ENDPOINT, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError("La API de sismos no devolvió una lista de eventos.")
    norm = []
    for d in data:
        nd = {k.lower(): v for k, v in d.items()}
        norm.append(nd)
    df = pd.DataFrame(norm)

    colmap = {
        "fecha": ["fecha","fechautc","time","tiempo"],
        "magnitud": ["magnitud","mag"],
        "profundidad": ["profundidad","prof","depth"],
        "latitud": ["latitud","lat"],
        "longitud": ["longitud","lon","long"],
        "referencia": ["referencia","referenciageografica","ref","refgeografica","lugar","place"],
    }

    def first_match(cols):
        for c in cols:
            if c in df.columns:
                return c
        return None

    cols = {k: first_match(v) for k,v in colmap.items()}
    for req in ["fecha","magnitud","profundidad","latitud","longitud"]:
        if cols.get(req) is None:
            df[req] = None
        else:
            df[req] = df[cols[req]]
    if cols.get("referencia") is None:
        df["referencia"] = ""
    else:
        df["referencia"] = df[cols["referencia"]]

    # Tipos robustos (acepta "5,3", "5.3", "65 km", etc.)
    df["magnitud"] = df["magnitud"].apply(_to_float)
    df["profundidad"] = df["profundidad"].apply(_to_float)
    df["latitud"] = df["latitud"].apply(_to_float)
    df["longitud"] = df["longitud"].apply(_to_float)

    # Fechas robustas
    def parse_fecha(s):
        try:
            return pd.to_datetime(s, utc=True, errors="coerce")
        except Exception:
            return pd.NaT

    df["fecha_dt"] = df["fecha"].apply(parse_fecha)

    # No eliminamos por lat/long (para no vaciar el dataset si vienen nulos)
    df = df.dropna(subset=["fecha_dt"]).copy()

    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    df["region_inf"] = df["referencia"].astype(str).str.extract(r"(Región\s+de\s+[\wÁÉÍÓÚÑáéíóúñ\s]+)", expand=False).fillna("No especificada")

    return df.sort_values("fecha_dt", ascending=False).reset_index(drop=True)

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
