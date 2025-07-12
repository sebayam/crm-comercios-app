# Proyecto: CRM de Comercios con Mapa y Registro de Gestiones
# Framework: Streamlit
# Funcionalidades:
# - Login por legajo
# - Vista de comercios asignados con filtros
# - Registro de gestiones con validaciones
# - Historial de gestiones con descarga
# - Mapa con comercios asignados y colores por estado

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import pydeck as pdk
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def guardar_en_google_sheets(datos):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales_sheets.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("CRM_gestiones").worksheet("Gestiones")
    fila = list(datos.values())
    sheet.append_row(fila, value_input_option="USER_ENTERED")

st.set_page_config(page_title="CRM de Comercios", layout="wide")

# 🔤 Estilo personalizado Montserrat + colores corporativos
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

# Cargar base de datos de comercios
df = pd.read_csv("proveedores_mvp.csv")
df['LEGAJO_ASESOR_NUM'] = pd.to_numeric(df['LEGAJO_ASESOR_NUM'], errors='coerce').fillna(0).astype(int).astype(str)

st.title("CRM de Comercios")
st.markdown("---")

# Validar sesión
if "legajo" not in st.session_state:
    legajo_input = st.text_input("Ingresá tu legajo (ej: 55032)", key="input_legajo")
    if st.button("Iniciar sesión"):
        if legajo_input.isdigit():
            st.session_state["legajo"] = legajo_input
            st.experimental_rerun()
        else:
            st.warning("Ingresá un legajo válido.")
    st.stop()

legajo = st.session_state.get("legajo")
if not legajo:
    st.warning("Tenés que iniciar sesión con tu legajo.")
    st.stop()

st.success(f"Sesión iniciada como colaborador {legajo}")

df_user = df[df['LEGAJO_ASESOR_NUM'] == legajo]
if df_user.empty:
    st.warning("No tenés comercios asignados.")
else:
    tab1, tab2 = st.tabs(["📋 Comercios", "📖 Gestiones registradas"])

    with tab1:
        st.subheader("📋 Tus comercios asignados")
        filtro_cuit = st.text_input("🔍 Buscar por número de CUIT")
        filtro_rubro = st.selectbox("📂 Filtrar por rubro", options=["Todos"] + sorted(df_user['RUBRO_MERCHANT_DESC'].dropna().unique().tolist()))

        df_filtrado = df_user.copy()
        if filtro_cuit:
            df_filtrado = df_filtrado[df_filtrado['DOCUMENTO_FISCAL_NUM'].astype(str) == filtro_cuit]
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
            )
        """)
        gestiones = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
        conn.close()

        def estado_gestion(comercio):
            registros = gestiones[gestiones['comercio'] == comercio]
            if registros.empty:
                return "🔴 No gestionado"
            if registros['respuesta'].str.contains("cerrada definitiva", case=False, na=False).any():
                return "⚫ Cerrado"
            if registros['contacto_exitoso'].str.contains("Sí").any():
                return "🟢 Contactado"
            if registros['nueva_fecha'].notna().any():
                return "🟠 Reprogramado"
            return "🔴 No gestionado"

        df_filtrado['Estado'] = df_filtrado['MERCHANT_NAME'].apply(estado_gestion)

        st.dataframe(df_filtrado[['MERCHANT_NAME', 'DOCUMENTO_FISCAL_NUM', 'TELEFONO_CARACTERISTICA_TXT', 'DOMICILIO_FORMATEADO_TXT', 'RUBRO_MERCHANT_DESC', 'Estado']])

        st.divider()
        st.subheader("🗺️ Mapa de comercios")
        df_user_mapa = df_filtrado.rename(columns={'LATITUD': 'latitude', 'LONGITUD': 'longitude'})
        df_user_mapa = df_user_mapa[(df_user_mapa['latitude'].between(-90, 90)) & (df_user_mapa['longitude'].between(-180, 180))]

        def color_estado(estado):
            if "🟢" in estado:
                return [0, 200, 0]
            elif "🟠" in estado:
                return [255, 165, 0]
            elif "⚫" in estado:
                return [0, 0, 0]
            else:
                return [255, 0, 0]

        df_user_mapa['color'] = df_filtrado['Estado'].apply(color_estado)
        df_user_mapa['merchant_name'] = df_filtrado['MERCHANT_NAME']
        df_user_mapa['Estado'] = df_filtrado['Estado']

        st.pydeck_chart(pdk.Deck(
            map_style='mapbox://styles/mapbox/streets-v11',
            initial_view_state=pdk.ViewState(
                latitude=df_user_mapa['latitude'].mean(),
                longitude=df_user_mapa['longitude'].mean(),
                zoom=11,
                pitch=0,
            ),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=df_user_mapa,
                    get_position='[longitude, latitude]',
                    get_color='color',
                    get_radius=20,
                    radius_min_pixels=3,
                    radius_max_pixels=100,
                    radius_scale=1,
                    pickable=True,
                    auto_highlight=True
                )
            ],
            tooltip={
                "html": "<b>Comercio:</b> {merchant_name}<br/><b>Estado:</b> {Estado}",
                "style": {"backgroundColor": "white", "color": "black"}
            }
        ))

        st.divider()
        st.subheader("📝 Registrar gestión")
        selected = st.selectbox("Seleccioná un comercio", df_filtrado['MERCHANT_NAME'].unique())
        tipo_contacto = st.radio("Tipo de contacto", ["Presencial", "Teléfono", "Mixto (Telefónico y Visita)"])
        pudo_contactar = st.radio("¿Pudo contactar?", ["Sí", "No", "Comercio inexistente o cerrada definitiva"])
        respuesta = st.text_input("Respuesta del comercio")
        nueva_fecha = st.date_input("Reprogramar visita") if pudo_contactar == "No" else None

        if st.button("Guardar gestión"):
            if not respuesta:
                st.warning("Por favor, completá la respuesta del comercio.")
            else:
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
                    )
                """)
                conn.commit()

                check = conn.execute(
                    "SELECT COUNT(*) FROM gestiones WHERE legajo = ? AND comercio = ? AND DATE(fecha_registro) = DATE('now')",
                    (legajo, selected)
                ).fetchone()[0]

                if check > 0:
                    st.warning("Ya registraste una gestión para este comercio hoy.")
                else:
                    conn.execute("""
                        INSERT INTO gestiones (legajo, comercio, contacto, contacto_exitoso, respuesta, nueva_fecha, fecha_registro)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        legajo,
                        selected,
                        tipo_contacto,
                        pudo_contactar,
                        respuesta,
                        str(nueva_fecha) if nueva_fecha else None,
                        str(datetime.now())
                    ))
                    conn.commit()

                    gestion_dict = {
                        "legajo": legajo,
                        "comercio": selected,
                        "contacto": tipo_contacto,
                        "contacto_exitoso": pudo_contactar,
                        "respuesta": respuesta,
                        "nueva_fecha": str(nueva_fecha) if nueva_fecha else "",
                        "fecha_registro": str(datetime.now())
                    }

                    guardar_en_google_sheets(gestion_dict)
                    st.success("Gestión registrada exitosamente.")
                conn.close()

    with tab2:
        st.subheader("📖 Historial de gestiones")
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
            )
        """)
        df_historial = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
        conn.close()

        if df_historial.empty:
            st.info("Todavía no registraste ninguna gestión.")
        else:
            st.dataframe(df_historial)
            st.download_button("📥 Descargar historial como CSV", data=df_historial.to_csv(index=False), file_name="gestiones_colaborador.csv")
