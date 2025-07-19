# Proyecto: CRM de Comercios con Mapa y Registro de Gestiones
# Framework: Streamlit
# Funcionalidades:
# - Login por legajo
# - Vista de comercios asignados con filtros
# - Registro de gestiones con validaciones
# - Historial de gestiones con descarga
# - Mapa con comercios asignados y colores por estado
# - Planificación diaria con IA (10 visitas más cercanas y numeración)

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import pydeck as pdk
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

st.set_page_config(page_title="CRM de Comercios", layout="wide")

LEGAJOS_LIDERES = ["32126"]

# Estilo visual
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
html, body, [class*="css"]  {
    font-family: 'Montserrat', sans-serif;
    background-color: #F9F9F9;
    color: #3D0074;
}
h1, h2, h3, h4 {
    color: #3D0074;
    font-weight: 700;
}
.stButton>button {
    background-color: #FF6600;
    color: white;
    font-weight: bold;
    border: none;
    border-radius: 6px;
    padding: 0.5em 1em;
}
.stButton>button:hover {
    background-color: #e65300;
}
.stSelectbox label, .stTextInput label, .stRadio label {
    color: #3D0074;
    font-weight: 600;
}
.stTabs [data-baseweb="tab"] {
    font-weight: 600;
    color: #3D0074;
}
header, footer, #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Cargar base
df = pd.read_csv("proveedores_mvp.csv")
df['LEGAJO_ASESOR_NUM'] = pd.to_numeric(df['LEGAJO_ASESOR_NUM'], errors='coerce')
df = df[df['LEGAJO_ASESOR_NUM'].notna()].copy()
df['LEGAJO_ASESOR_NUM'] = df['LEGAJO_ASESOR_NUM'].astype('Int64').astype(str)

st.title("CRM de Comercios")
st.markdown("---")
legajo_input = st.text_input("Ingresá tu legajo (ej: 55032):")

if legajo_input.isdigit():
    legajo = legajo_input
    if legajo in LEGAJOS_LIDERES:
        st.success(f"Sesión iniciada como líder {legajo}")
        conn = sqlite3.connect("gestiones.db")
        df_gestiones = pd.read_sql_query("SELECT * FROM gestiones", conn)
        conn.close()
        if df_gestiones.empty:
            st.info("No hay gestiones registradas todavía.")
        else:
            df_gestiones['fecha_registro'] = pd.to_datetime(df_gestiones['fecha_registro']).dt.date
            tab1, tab2 = st.tabs(["📈 Resumen diario", "📄 Todas las gestiones"])
            with tab1:
                resumen = df_gestiones.groupby(['fecha_registro', 'legajo'])['id'].count().reset_index()
                resumen.columns = ['fecha_registro', 'legajo', 'cantidad_gestiones']
                st.dataframe(resumen)
                st.download_button("📥 Descargar resumen", resumen.to_csv(index=False), file_name="resumen.csv")
            with tab2:
                st.dataframe(df_gestiones)
                st.download_button("📥 Descargar detalle", df_gestiones.to_csv(index=False), file_name="gestiones.csv")
        st.stop()
    else:
        st.success(f"Sesión iniciada como colaborador {legajo}")
        df_user = df[df['LEGAJO_ASESOR_NUM'] == legajo]
        if df_user.empty:
            st.warning("No tenés comercios asignados.")
        else:
            tab1, tab2, tab3 = st.tabs(["📋 Comercios", "📖 Gestiones registradas", "📌 Planificación diaria"])

            with tab1:
                st.subheader("📋 Tus comercios asignados")
                filtro_cuit = st.text_input("🔍 Buscar por CUIT")
                filtro_rubro = st.selectbox("📂 Filtrar por rubro", ["Todos"] + sorted(df_user['RUBRO_MERCHANT_DESC'].dropna().unique()))
                df_filtrado = df_user.copy()
                if filtro_cuit:
                    df_filtrado = df_filtrado[df_filtrado['DOCUMENTO_FISCAL_NUM'].astype(str).str.contains(filtro_cuit)]
                if filtro_rubro != "Todos":
                    df_filtrado = df_filtrado[df_filtrado['RUBRO_MERCHANT_DESC'] == filtro_rubro]
                conn = sqlite3.connect("gestiones.db")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS gestiones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        legajo TEXT,
                        comercio TEXT,
                        contacto TEXT,
                        contacto_exitoso TEXT,
                        respuesta TEXT,
                        nueva_fecha TEXT,
                        fecha_registro TEXT
                    )""")
                gestiones = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
                conn.close()
                def estado_gestion(comercio):
                    registros = gestiones[gestiones['comercio'] == comercio]
                    if registros.empty: return "🔴 No gestionado"
                    if registros['respuesta'].str.contains("cerrada definitiva", case=False, na=False).any(): return "⚫ Cerrado"
                    if registros['contacto_exitoso'].str.contains("Sí", na=False).any(): return "🟢 Contactado"
                    if registros['nueva_fecha'].notna().any(): return "🟠 Reprogramado"
                    return "🔴 No gestionado"
                df_filtrado['Estado'] = df_filtrado['MERCHANT_NAME'].apply(estado_gestion)
                st.dataframe(df_filtrado[['MERCHANT_NAME','DOCUMENTO_FISCAL_NUM','DOMICILIO_FORMATEADO_TXT','RUBRO_MERCHANT_DESC','Estado']])
                st.divider()
                st.subheader("🗺️ Mapa")
                df_map = df_filtrado.rename(columns={'LATITUD': 'latitude','LONGITUD': 'longitude'})
                df_map['color'] = df_filtrado['Estado'].map(lambda x: [0,200,0] if '🟢' in x else [255,165,0] if '🟠' in x else [0,0,0] if '⚫' in x else [255,0,0])
                df_map['merchant_name'] = df_filtrado['MERCHANT_NAME']
                df_map['Estado'] = df_filtrado['Estado']
                st.pydeck_chart(pdk.Deck(
                    map_style='mapbox://styles/mapbox/streets-v11',
                    initial_view_state=pdk.ViewState(latitude=df_map['latitude'].mean(), longitude=df_map['longitude'].mean(), zoom=12),
                    layers=[pdk.Layer("ScatterplotLayer", data=df_map, get_position='[longitude, latitude]', get_color='color', get_radius=50)]))
                st.divider()
                st.subheader("📝 Registrar gestión")
                selected = st.selectbox("Comercio", df_filtrado['MERCHANT_NAME'].unique())
                tipo_contacto = st.radio("Tipo de contacto", ["Presencial", "Teléfono", "Mixto"])
                pudo_contactar = st.radio("¿Pudo contactar?", ["Sí", "No", "Comercio inexistente o cerrada definitiva"])
                respuesta = st.text_input("Respuesta del comercio")
                nueva_fecha = st.date_input("Reprogramar visita", disabled=(pudo_contactar != "No")) if pudo_contactar == "No" else None
                if st.button("Guardar gestión"):
                    if not respuesta:
                        st.warning("Por favor completá la respuesta.")
                    else:
                        conn = sqlite3.connect("gestiones.db")
                        check = conn.execute("SELECT COUNT(*) FROM gestiones WHERE legajo = ? AND comercio = ? AND DATE(fecha_registro) = DATE('now')", (legajo, selected)).fetchone()[0]
                        if check > 0:
                            st.warning("Ya registraste una gestión hoy.")
                        else:
                            conn.execute("INSERT INTO gestiones (legajo, comercio, contacto, contacto_exitoso, respuesta, nueva_fecha, fecha_registro) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (legajo, selected, tipo_contacto, pudo_contactar, respuesta, str(nueva_fecha) if nueva_fecha else None, str(datetime.now())))
                            conn.commit()
                            conn.close()
                            st.success("Gestión registrada exitosamente.")

            with tab2:
                st.subheader("📖 Historial de gestiones")
                conn = sqlite3.connect("gestiones.db")
                df_historial = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
                conn.close()
                st.dataframe(df_historial)
                st.download_button("📥 Descargar CSV", df_historial.to_csv(index=False), file_name="historial.csv")

            with tab3:
                st.subheader("📌 Planificación diaria")
                direccion_usuario = st.text_input("📍 Ingresá tu dirección actual (ej: Av. Santa Fe 1234, CABA)")
                if direccion_usuario:
                    geolocator = Nominatim(user_agent="crm_app")
                    ubicacion = geolocator.geocode(direccion_usuario)
                    if ubicacion:
                        ubicacion_usuario = (ubicacion.latitude, ubicacion.longitude)
                        conn = sqlite3.connect("gestiones.db")
                        gestiones = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
                        conn.close()
                        gestiones['fecha_registro'] = pd.to_datetime(gestiones['fecha_registro'])
                        def dias_sin_contacto(comercio):
                            registros = gestiones[gestiones['comercio'] == comercio]
                            return 999 if registros.empty else (datetime.now() - registros['fecha_registro'].max()).days
                        def estado_gestion(comercio):
                            registros = gestiones[gestiones['comercio'] == comercio]
                            if registros.empty: return "No gestionado"
                            if registros['contacto_exitoso'].str.contains("Sí", na=False).any(): return "Contactado"
                            if registros['nueva_fecha'].notna().any(): return "Reprogramado"
                            return "No gestionado"
                        df_plan = df_user.copy()
                        df_plan['Estado'] = df_plan['MERCHANT_NAME'].apply(estado_gestion)
                        df_plan['Días sin contacto'] = df_plan['MERCHANT_NAME'].apply(dias_sin_contacto)
                        df_plan = df_plan[df_plan['Estado'].isin(["No gestionado", "Reprogramado"])]
                        df_plan['Distancia (km)'] = df_plan.apply(lambda row: geodesic(ubicacion_usuario, (row['LATITUD'], row['LONGITUD'])).km, axis=1)
                        df_plan = df_plan.sort_values(by=['Días sin contacto','Distancia (km)'], ascending=[False,True]).head(10).reset_index(drop=True)
                        df_plan['Orden'] = df_plan.index + 1
                        df_plan['latitude'] = df_plan['LATITUD']
                        df_plan['longitude'] = df_plan['LONGITUD']
                        df_plan['color'] = [[0, 150, 255]] * len(df_plan)
                        df_plan['text'] = df_plan['Orden'].astype(str)
                        st.dataframe(df_plan[['Orden','MERCHANT_NAME','DOMICILIO_FORMATEADO_TXT','Estado','Días sin contacto','Distancia (km)']])
                        st.pydeck_chart(pdk.Deck(
                            map_style='mapbox://styles/mapbox/streets-v11',
                            initial_view_state=pdk.ViewState(latitude=ubicacion_usuario[0], longitude=ubicacion_usuario[1], zoom=12),
                            layers=[
                                pdk.Layer("ScatterplotLayer", data=df_plan, get_position='[longitude, latitude]', get_color='color', get_radius=60, pickable=True, auto_highlight=True),
                                pdk.Layer("TextLayer", data=df_plan, get_position='[longitude, latitude]', get_text='text', get_size=16, get_color=[255,255,255], get_alignment_baseline="center")
                            ],
                            tooltip={"html": "<b>{MERCHANT_NAME}</b><br/>Orden: {Orden}<br/>Distancia: {Distancia (km)} km"}
                        ))
                    else:
                        st.warning("Dirección no encontrada. Verificá e intentá de nuevo.")
