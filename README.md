# Solemne II — Análisis de Sismos en Chile (Streamlit)

**Autor:** Claudio Navarrete Jara  
**Fecha:** 2025-09-08

Aplicación web (Streamlit) que consume una API REST pública de sismos, procesa y analiza los datos con Python (pandas) y los presenta en una interfaz interactiva con mapas, filtros y gráficos.

## 🧩 Características
- Consumo de API REST pública (sin API key) para últimos sismos en Chile.
- Filtros por magnitud, ventana de días y palabra clave en la referencia geográfica.
- Mapa interactivo (Folium) con color por profundidad o magnitud.
- KPIs y gráficos de tendencias (Plotly).
- Descarga de CSV con los datos filtrados.
- Código modular y documentado (ver `src/api.py`).

## 📦 Estructura del proyecto
```
solemne2_proyecto_sismos/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .streamlit/
│  └─ config.toml
├─ src/
│  └─ api.py
├─ docs/
│  ├─ INFORME_Solemne_II_Claudio_Navarrete_Jara.pdf
│  └─ POSTER_Solemne_II_Claudio_Navarrete_Jara.pdf
└─ assets/
```

## 🚀 Cómo ejecutar localmente
1. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Ejecutar:
   ```bash
   streamlit run app.py
   ```

## ☁️ Despliegue en Streamlit Cloud
1. Sube esta carpeta a GitHub.
2. En Streamlit Community Cloud, crea una app apuntando a `app.py`.
3. No requiere API keys.

## 🗂️ Fuente de datos y referencias
- Portal de datos públicos del Gobierno de Chile: https://datos.gob.cl/group  
- Ejemplo de API de sismos (material de clase).

## 📝 Rúbrica y requisitos
- Interacción con API REST (`requests`), manejo de JSON.
- Análisis con `pandas`, visualizaciones con `Streamlit`, `Folium`, `Plotly`.
- Interactividad (filtros, mapa, descarga) y documentación (README, Informe, Poster).
