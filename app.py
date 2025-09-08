
import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium import CircleMarker
from streamlit_folium import st_folium
import plotly.express as px
from src.api import fetch_sismos, filter_sismos

st.set_page_config(page_title="Sismos Chile • Solemne II", page_icon="🌎", layout="wide")
st.title("🌎 Análisis de Sismos en Chile - Solemne II")
st.caption("Autor: Claudio Navarrete Jara • Fuentes: EVTDB / CSN / ChileAlerta / GAEL")

with st.sidebar:
    st.header("⚙️ Controles")
    mag_sel = st.select_slider("Umbral de magnitud", options=[0, 2, 3, 4, 5, 6], value=3)
    dias = st.select_slider("Ventana de días", options=[1, 3, 7, 14, 30], value=7)
    region_kw = st.text_input("Buscar por referencia (región/ciudad)", value="")
    radius = st.slider("Tamaño de marcador (px)", min_value=3, max_value=20, value=8)
    color_mode = st.radio("Color por", options=["profundidad", "magnitud"], index=0)
    mostrar_mapa = st.checkbox("Mostrar mapa", value=True)
    evtdb_pages = st.slider("Número de páginas EVTDB", min_value=1, max_value=5, value=2)

@st.cache_data(ttl=300, show_spinner=True)
def load_data(pages: int):
    return fetch_sismos(evtdb_pages=pages)

try:
    df = load_data(evtdb_pages)
except Exception as e:
    st.error(f"⚠️ No fue posible cargar datos: {e}")
    st.stop()

for _col in ['latitud', 'longitud', 'magnitud', 'profundidad', 'fecha_dt', 'fecha_local', 'referencia']:
    if _col not in df.columns:
        df[_col] = pd.NA

hasta = pd.Timestamp.now(tz="UTC")
desde = hasta - pd.Timedelta(days=int(dias))
dff = filter_sismos(df, mag_min=mag_sel, fecha_desde=desde, fecha_hasta=hasta, region_keyword=region_kw)
valid_map = dff.dropna(subset=['latitud', 'longitud']) if set(['latitud', 'longitud']).issubset(dff.columns) else dff.iloc[0:0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Eventos", len(dff))
if not dff.empty:
    c2.metric("Magnitud media", f"{dff['magnitud'].mean():.2f}")
    c3.metric("Profundidad media (km)", f"{dff['profundidad'].mean():.1f}")
    c4.metric("Máx. magnitud", f"{dff['magnitud'].max():.1f}")
else:
    c2.metric("Magnitud media", "—")
    c3.metric("Profundidad media (km)", "—")
    c4.metric("Máx. magnitud", "—")

st.subheader("🗺️ Mapa interactivo")
if not mostrar_mapa:
    st.info("Mapa oculto por el usuario.")
elif dff.empty:
    st.info("Sin resultados para los filtros aplicados.")
elif valid_map.empty:
    st.info("Hay datos, pero ninguno trae coordenadas para el mapa.")
else:
    center = [valid_map['latitud'].mean(), valid_map['longitud'].mean()]
    if not (np.isfinite(center[0]) and np.isfinite(center[1])):
        center = [-33.45, -70.66]
    m = folium.Map(location=center, zoom_start=4, tiles="OpenStreetMap")

    def color_for(r):
        if color_mode == "profundidad":
            v = r['profundidad']
            if v is None or pd.isna(v): return "#777777"
            if v < 35: return "#4CAF50"
            if v < 70: return "#FFC107"
            if v < 300: return "#FF9800"
            return "#E53935"
        else:
            mval = r['magnitud']
            if mval is None or pd.isna(mval): return "#777777"
            if mval < 3: return "#4CAF50"
            if mval < 5: return "#FF9800"
            return "#E53935"

    for _, r in valid_map.iterrows():
        popup = (
            f"<b>Mag:</b> {r.get('magnitud')} • <b>Prof:</b> {r.get('profundidad')} km<br>"
            f"<b>Fecha:</b> {r.get('fecha_local')}<br>"
            f"<b>Ref:</b> {r.get('referencia','')}"
        )
        CircleMarker(
            location=[r['latitud'], r['longitud']],
            radius=radius,
            color=color_for(r),
            fill=True,
            fill_color=color_for(r),
            fill_opacity=0.7
        ).add_child(folium.Popup(popup, max_width=350)).add_to(m)

    st_folium(m, height=520, use_container_width=True)

st.subheader("📈 Tendencias")
if not dff.empty:
    daily = dff.groupby('dia').agg(eventos=('magnitud','count'), mag_prom=('magnitud','mean')).reset_index()
    st.plotly_chart(px.bar(daily, x='dia', y='eventos', title="Eventos por día"), use_container_width=True)
    st.plotly_chart(px.scatter(dff, x='fecha_local', y='magnitud', trendline='lowess', title="Magnitud vs tiempo", hover_data=['referencia']), use_container_width=True)

st.subheader("🧮 Tabla de datos")
st.dataframe(dff[['fecha_local','magnitud','profundidad','latitud','longitud','referencia']])
st.download_button("⬇️ Descargar CSV filtrado", data=dff.to_csv(index=False).encode("utf-8"), file_name="sismos_filtrados.csv", mime="text/csv")

st.markdown("---")
st.caption("Proyecto Solemne II • Ingeniería USS • Hecho con Streamlit, Pandas, Folium y Plotly")
