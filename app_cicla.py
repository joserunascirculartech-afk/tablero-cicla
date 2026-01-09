import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from PIL import Image
import re
import time
import os
from datetime import datetime  # <--- ¡ESTA ERA LA LÍNEA QUE FALTABA!

# ================= CONFIGURACIÓN =================
st.set_page_config(page_title="Cicla 3D - Pedidos", page_icon="🚴", layout="wide")

# CREDENCIALES (Ruta validada)
JSON_FILE = r'/Users/jdg_music_/Desktop/Cicla Proyect/service_account.json'
SHEET_ID = '1oeN-Iqrlc2hUuRhYDdrqqd7eez9wwPgGNbgAGi9CUVs'
WORKSHEET_NAME = 'Respuestas de formulario 1'

# LOGIN
USER_LOGIN = "Cicla3D"
PASS_LOGIN = "Cicla:D"

# AUTO-REFRESCO (Segundos)
REFRESH_SECONDS = 5

# ================= LOGIN =================
def check_login():
    """Sistema simple de autenticación"""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Acceso Cicla 3D")
            st.markdown("---")
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Iniciar Sesión", type="primary"):
                if username == USER_LOGIN and password == PASS_LOGIN:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        return False
    return True

# ================= CONEXIONES =================
@st.cache_resource
def connect_google():
    """Conecta a Google APIs (Se mantiene en memoria)"""
    if not os.path.exists(JSON_FILE):
        st.error(f"❌ No se encuentra: {JSON_FILE}")
        return None, None

    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(JSON_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None, None

@st.cache_data(ttl=REFRESH_SECONDS) 
def load_data(_gc):
    """Descarga y procesa datos del Sheet (Cacheado por 5s)"""
    if _gc is None: return []
    try:
        sh = _gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
        all_values = ws.get_all_values()
        
        if not all_values: return []

        headers = all_values[0]
        rows = all_values[1:]

        # Helpers
        def get_col_idx(keywords):
            for i, h in enumerate(headers):
                h_clean = str(h).lower().strip()
                for k in keywords:
                    if k in h_clean: return i
            return -1

        def get_val(row, idx):
            if idx != -1 and idx < len(row): return str(row[idx]).strip()
            return ""

        # Mapeo de Columnas
        idx_foto = get_col_idx(["foto visualizar", "imagen de referencia"])
        idx_dias = get_col_idx(["prioridad", "días restantes"])
        idx_f_envio = get_col_idx(["fecha de envio"])
        idx_f_entrega = get_col_idx(["fecha de entrega"])
        
        # Cliente
        idx_cli_nom = get_col_idx(["nombre del cliente"])
        idx_cli_emp = get_col_idx(["nombre de la empresa"])
        idx_cli_rut = get_col_idx(["rut:"]) 
        idx_cli_tel = get_col_idx(["telefono:"])
        
        # Detalles
        idx_desc = get_col_idx(["descripción"])
        idx_color = get_col_idx(["colores"])
        idx_tipo = get_col_idx(["tipo de entrega"])
        
        # Factura
        idx_req_fact = get_col_idx(["requiere factura"])
        idx_razon = get_col_idx(["razón social"])
        idx_rut_fac = get_col_idx(["rut facturación"])
        idx_giro = get_col_idx(["giro"])
        idx_dir_fac = get_col_idx(["dirección facturación"])
        idx_com_fac = get_col_idx(["comuna:\n"]) 
        
        # Envio
        idx_env_dir = get_col_idx(["dirección de envio"])
        idx_env_com = get_col_idx(["comuna/ciudad"])
        idx_env_ref = get_col_idx(["referencia (opcional)", "referencia opcional"]) 
        idx_recibe_nom = get_col_idx(["nombre de quien recibe"])
        idx_recibe_tel = get_col_idx(["telefono de quien recibe"])

        processed_rows = []

        for row in rows:
            if not any(row): continue

            # Días
            dias_raw = get_val(row, idx_dias)
            try: dias_num = int(float(dias_raw)) if dias_raw else 999
            except: dias_num = 999
            
            # Cliente
            cliente_info = f"**{get_val(row, idx_cli_nom)}**\n\n🏢 {get_val(row, idx_cli_emp)}\n\n🆔 {get_val(row, idx_cli_rut)}\n\n📞 {get_val(row, idx_cli_tel)}"
            
            # Factura
            req = get_val(row, idx_req_fact).lower()
            if "si" in req:
                fact_info = f"✅ **SI**\n\nRaz: {get_val(row, idx_razon)}\n\nRUT: {get_val(row, idx_rut_fac)}\n\nGiro: {get_val(row, idx_giro)}\n\nDir: {get_val(row, idx_dir_fac)}"
            else:
                fact_info = "❌ No requiere"
            
            # Envío
            ref_txt = get_val(row, idx_env_ref)
            if "http" in ref_txt: ref_txt = "" 
            envio_info = f"📍 {get_val(row, idx_env_dir)}\n\nCity: {get_val(row, idx_env_com)}\n\nRef: {ref_txt}\n\nRecibe: {get_val(row, idx_recibe_nom)} ({get_val(row, idx_recibe_tel)})"

            processed_rows.append({
                "sort": dias_num,
                "url": get_val(row, idx_foto),
                "dias": dias_num,
                "f_envio": get_val(row, idx_f_envio),
                "f_entrega": get_val(row, idx_f_entrega),
                "cliente": cliente_info,
                "desc": get_val(row, idx_desc),
                "colores": get_val(row, idx_color),
                "factura": fact_info,
                "envio": envio_info,
                "tipo": get_val(row, idx_tipo)
            })

        processed_rows.sort(key=lambda x: x["sort"])
        return processed_rows

    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return []

@st.cache_data(show_spinner=False)
def get_image(url, _drive_service):
    """Descarga imagen de Drive (Cacheada)"""
    if not url or "drive.google.com" not in str(url): return None
    
    match = re.search(r'id=([a-zA-Z0-9_-]+)', str(url))
    if not match: match = re.search(r'/d/([a-zA-Z0-9_-]+)', str(url))
    if not match: return None
    file_id = match.group(1)

    try:
        request = _drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        fh.seek(0)
        return Image.open(fh)
    except Exception:
        return None

# ================= APP MAIN =================
def main():
    if not check_login():
        return

    # Sidebar
    with st.sidebar:
        st.write(f"Usuario: **{USER_LOGIN}**")
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.success("🟢 Sistema Activo")
        st.caption(f"Refresco: {REFRESH_SECONDS}s")

    # Header
    c_head1, c_head2, c_head3 = st.columns([3, 1, 1])
    c_head1.title("🚴 Tablero Cicla 3D")
    
    # Conexión
    gc, drive_service = connect_google()
    if not gc: return

    # Carga Datos
    rows = load_data(gc)
    
    # Métricas
    c_head2.metric("Pedidos Pendientes", len(rows))
    
    # Hora de actualización
    hora_actual = datetime.now().strftime('%H:%M:%S')
    c_head3.metric("Última Actualización", hora_actual)

    st.markdown("---")

    # Encabezados Tabla
    cols_config = [1.2, 0.6, 0.8, 0.8, 1.5, 1.5, 1.5, 1.5, 0.8]
    titulos = ["📸 FOTO", "DÍAS", "ENVÍO", "ENTREGA", "CLIENTE", "DETALLE", "ENVÍO", "FACTURA", "TIPO"]
    
    h_cols = st.columns(cols_config)
    for c, t in zip(h_cols, titulos):
        c.markdown(f"**{t}**")
    
    st.markdown("---")

    # Renderizado de filas
    if not rows:
        st.info("No hay pedidos activos por ahora. ¡Buen trabajo!")

    for row in rows:
        with st.container():
            c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(cols_config)
            
            # Foto
            img = get_image(row['url'], drive_service)
            if img:
                c1.image(img, use_container_width=True)
            else:
                c1.text("Sin foto")
            
            # Días
            color = "red" if row['dias'] <= 2 else "green"
            c2.markdown(f"<h2 style='color: {color}; margin:0; padding:0;'>{row['dias']}</h2>", unsafe_allow_html=True)
            
            # Resto
            c3.write(row['f_envio'])
            c4.write(row['f_entrega'])
            c5.markdown(row['cliente'])
            
            c6.markdown(f"**Desc:** {row['desc']}")
            c6.info(f"🎨 {row['colores']}")
            
            c7.markdown(row['envio'])
            c8.markdown(row['factura'])
            
            if "Retiro" in row['tipo']:
                c9.success(row['tipo'])
            else:
                c9.warning(row['tipo'])
            
            st.markdown("---")

    # Bucle de refresco
    time.sleep(REFRESH_SECONDS)
    st.rerun()

if __name__ == "__main__":
    main()