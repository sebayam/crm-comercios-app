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

st.set_page_config(page_title="CRM de Comercios", layout="wide")

# Cargar base de datos de comercios
df = pd.read_csv("proveedores_mvp.csv")

st.title("CRM de Comercios")
st.markdown("---")
legajo = st.text_input("Ingresá tu legajo (ej: 55032):")

if legajo:
    st.success(f"Sesión iniciada como colaborador {legajo}")
    df_user = df[df['LEGAJO_ASESOR_NUM'].astype(str) == legajo]

    if df_user.empty:
        st.warning("No tenés comercios asignados.")
    else:
        tab1, tab2 = st.tabs(["📋 Comercios", "📖 Gestiones registradas"])

        with tab1:
            st.subheader("📋 Tus comercios asignados")

            # Filtros
            filtro_nombre = st.text_input("🔍 Buscar por nombre de comercio")
            filtro_rubro = st.selectbox("📂 Filtrar por rubro", options=["Todos"] + sorted(df_user['RUBRO_MERCHANT_DESC'].dropna().unique().tolist()))

            df_filtrado = df_user.copy()
            if filtro_nombre:
                df_filtrado = df_filtrado[df_filtrado['MERCHANT_NAME'].str.contains(filtro_nombre, case=False, na=False)]
            if filtro_rubro != "Todos":
                df_filtrado = df_filtrado[df_filtrado['RUBRO_MERCHANT_DESC'] == filtro_rubro]

            # Cargar gestiones para determinar estado de cada comercio
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
            """
            )
            gestiones = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
            conn.close()

            def estado_gestion(comercio):
                registros = gestiones[gestiones['comercio'] == comercio]
                if registros.empty:
                    return "🔴 No gestionado"
                if registros['contacto_exitoso'].str.contains("Sí").any():
                    return "🟢 Contactado"
                if registros['nueva_fecha'].notna().any():
                    return "🟠 Reprogramado"
                return "🔴 No gestionado"

            df_filtrado['Estado'] = df_filtrado['MERCHANT_NAME'].apply(estado_gestion)

            st.dataframe(df_filtrado[['MERCHANT_NAME', 'DOCUMENTO_FISCAL_NUM',
                                      'TELEFONO_CARACTERISTICA_TXT', 'DOMICILIO_FORMATEADO_TXT',
                                      'RUBRO_MERCHANT_DESC', 'Estado']])

            st.divider()
            st.subheader("🗺️ Mapa de comercios")
            df_user_mapa = df_filtrado.rename(columns={'LATITUD': 'latitude', 'LONGITUD': 'longitude'})
            df_user_mapa = df_user_mapa[
                (df_user_mapa['latitude'].between(-90, 90)) &
                (df_user_mapa['longitude'].between(-180, 180))
            ]

            def color_estado(estado):
                if "🟢" in estado:
                    return [0, 200, 0]  # verde
                elif "🟠" in estado:
                    return [255, 165, 0]  # naranja
                else:
                    return [255, 0, 0]  # rojo

            df_user_mapa['color'] = df_filtrado['Estado'].apply(color_estado)

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
                        'ScatterplotLayer',
                        data=df_user_mapa,
                        get_position='[longitude, latitude]',
                        get_color='color',
                        get_radius=80,
                    )
                ]
            ))

            st.divider()
            st.subheader("📝 Registrar gestión")
            selected = st.selectbox("Seleccioná un comercio", df_filtrado['MERCHANT_NAME'].unique())

            tipo_contacto = st.radio("Tipo de contacto", ["Presencial", "Teléfono"])
            pudo_contactar = st.radio("¿Pudo contactar?", ["Sí", "No"])
            respuesta = st.text_input("Respuesta del comercio")
            nueva_fecha = None
            if pudo_contactar == "No":
                nueva_fecha = st.date_input("Reprogramar visita")

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
                    """
                    )
                    check = conn.execute("SELECT COUNT(*) FROM gestiones WHERE legajo = ? AND comercio = ? AND DATE(fecha_registro) = DATE('now')", (legajo, selected)).fetchone()[0]
                    if check > 0:
                        st.warning("Ya registraste una gestión para este comercio hoy.")
                    else:
                        conn.execute("INSERT INTO gestiones (legajo, comercio, contacto, contacto_exitoso, respuesta, nueva_fecha, fecha_registro) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (legajo, selected, tipo_contacto, pudo_contactar, respuesta, str(nueva_fecha) if nueva_fecha else None, str(datetime.now())))
                        conn.commit()
                        conn.close()
                        st.success("Gestión registrada exitosamente.")

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
            """
            )
            df_historial = pd.read_sql_query("SELECT * FROM gestiones WHERE legajo = ?", conn, params=(legajo,))
            conn.close()

            if df_historial.empty:
                st.info("Todavía no registraste ninguna gestión.")
            else:
                st.dataframe(df_historial)
                st.download_button("📥 Descargar historial como CSV", data=df_historial.to_csv(index=False), file_name="gestiones_colaborador.csv")
