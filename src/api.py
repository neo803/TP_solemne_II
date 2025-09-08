from __future__ import annotations
import requests
import pandas as pd
from typing import Optional

GAEL_ENDPOINT = "https://api.gael.cloud/general/public/sismos"

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

    df["magnitud"] = pd.to_numeric(df["magnitud"], errors="coerce")
    df["profundidad"] = pd.to_numeric(df["profundidad"], errors="coerce")
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")

    def parse_fecha(s):
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ","%Y-%m-%dT%H:%M:%SZ","%d/%m/%Y %H:%M:%S","%Y-%m-%d %H:%M:%S"]:
            try:
                return pd.to_datetime(s, format=fmt, utc=True)
            except Exception:
                pass
        return pd.to_datetime(s, errors="coerce", utc=True)

    df["fecha_dt"] = df["fecha"].apply(parse_fecha)
    df.dropna(subset=["latitud","longitud","fecha_dt"], inplace=True)
    df["fecha_local"] = df["fecha_dt"].dt.tz_convert("America/Santiago")
    df["dia"] = df["fecha_local"].dt.date
    df["hora"] = df["fecha_local"].dt.strftime("%H:%M")
    df["region_inf"] = df["referencia"].str.extract(r"(Región\s+de\s+[\wÁÉÍÓÚÑáéíóúñ\s]+)", expand=False).fillna("No especificada")
    return df.sort_values("fecha_dt", ascending=False).reset_index(drop=True)

def filter_sismos(df: pd.DataFrame,
                  mag_min: Optional[float] = None,
                  fecha_desde: Optional[pd.Timestamp] = None,
                  fecha_hasta: Optional[pd.Timestamp] = None,
                  region_keyword: str = "") -> pd.DataFrame:
    out = df.copy()
    if mag_min is not None:
        out = out[out["magnitud"] >= mag_min]
    if fecha_desde is not None:
        out = out[out["fecha_dt"] >= fecha_desde]
    if fecha_hasta is not None:
        out = out[out["fecha_dt"] <= fecha_hasta]
    if region_keyword:
        rk = region_keyword.strip().lower()
        out = out[out["referencia"].str.lower().str.contains(rk, na=False)]
    return out.reset_index(drop=True)
