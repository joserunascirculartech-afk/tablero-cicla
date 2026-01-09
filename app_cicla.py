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
from datetime import datetime

# ================= 1. CONFIGURACIÓN (Debe ir al principio) =================
st.set_page_config(page_title="Cicla 3D - Pedidos", page_icon="🚴", layout="wide")

# RUTA LOCAL (Solo se usa si falla la nube)
JSON_FILE_LOCAL = '/Users/jdg_music_/Desktop/Cicla Proyect/service_account.json'

# IDs de tu Google Sheet
SHEET_ID = '1oeN-Iqrlc2hUuRhYDdrqqd7eez9wwPgGNbgAGi9CUVs'
WORKSHEET_NAME = 'Respuestas de formulario 1'

# Credenciales de Login de la App
USER_LOGIN = "Cicla3D"
PASS_LOGIN = "Cicla:D"
REFRESH_SECONDS = 5

# ================= 2. CONEXIÓN INTELIGENTE (GOOGLE SHEETS) =================
@st.cache_resource
def connect_google():
    """Conecta usando Secrets (Nube) o Archivo (Local)"""
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = None

    # INTENTO 1: Buscar en Secrets de Streamlit (Nube)
    if "gcp_service_account" in st.secrets:
        try:
            # Convertimos los secrets a un diccionario normal
            creds_dict = dict(st.secrets["gcp_service_account"])

            # 🛠️ CORRECCIÓN VITAL: Arreglar saltos de línea en la clave privada
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        except Exception as e:
            st.error(f"⚠️ Error leyendo secrets: {e}")

    # INTENTO 2: Buscar archivo local (Tu Mac)
    if not creds and os.path.exists(JSON_FILE_LOCAL):
        try:
            creds = Credentials.from_service_account_file(JSON_FILE_LOCAL, scopes=scopes)
        except Exception as e:
            st.error(f"⚠️ Error leyendo archivo local: {e}")

    # Si fallan los dos intentos
    if not creds:
        st.error("❌ No se pudo conectar. Verifica los Secrets en Streamlit Cloud o el archivo json en local.")
        return None, None

    # Si tenemos credenciales, conectamos
    try:
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Error autenticando con Google: {e}")
        return None, None

# ================= 3. LÓGICA DE DATOS =================
@st.cache_data(ttl=REFRESH_SECONDS) 
def load_data(_gc):
    if _gc is None: return []
    try:
        sh = _gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
        all_values = ws.get_all_values()
        
        if not all_values: return []
        headers, rows = all_values[0], all_values[1:]

        def get_col_idx(keywords):
            for i, h in enumerate(headers):
                if any(k in str(h).lower().strip() for k in keywords): return i
            return -1

        def get_val(row, idx):
            return str(row[idx]).strip() if idx != -1 and idx < len(row) else ""

        # Mapeo de columnas
        idx_foto = get_col_idx(["foto visualizar", "imagen de referencia"])
        idx_dias = get_col_idx(["prioridad", "días restantes"])
        idx_f_env = get_col_idx(["fecha de envio"])
        idx_f_ent = get_col_idx(["fecha de entrega"])
        idx_cli_nom = get_col_idx(["nombre del cliente"])
        idx_cli_emp = get_col_idx(["nombre de la empresa"])
        idx_cli_rut = get_col_idx(["rut:"]) 
        idx_cli_tel = get_col_idx(["telefono:"])
        idx_desc = get_col_idx(["descripción"])
        idx_color = get_col_idx(["colores"])
        idx_tipo = get_col_idx(["tipo de entrega"])
        idx_req = get_col_idx(["requiere factura"])
        idx_razon = get_col_idx(["razón social"])
        idx_rut_fac = get_col_idx(["rut facturación"])
        idx_giro = get_col_idx(["giro"])
        idx_dir_fac = get_col_idx(["dirección facturación"])
        idx_env_dir = get_col_idx(["dirección de envio"])
        idx_env_com = get_col_idx(["comuna/ciudad"])
        idx_env_ref = get_col_idx(["referencia (opcional)", "referencia opcional"]) 
        idx_rec_nom = get_col_idx(["nombre de quien recibe"])
        idx_rec_tel = get_col_idx(["telefono de quien recibe"])

        processed = []
        for row in rows:
            if not any(row): continue
            
            d_raw = get_val(row, idx_dias)
            try: dias = int(float(d_raw)) if d_raw else 999
            except: dias = 999
            
            cli_txt = f"**{get_val(row, idx_cli_nom)}**\n\n🏢 {get_val(row, idx_cli_emp)}\n\n🆔 {get_val(row, idx_cli_rut)}\n\n📞 {get_val(row, idx_cli_tel)}"
            
            fact_txt = "❌ No"
            if "si" in get_val(row, idx_req).lower():
                fact_txt = f"✅ **SI**\n\nRaz: {get_val(row, idx_razon)}\n\nRUT: {get_val(row, idx_rut_fac)}\n\nGiro: {get_val(row, idx_giro)}\n\nDir: {get_val(row, idx_dir_fac)}"

            ref = get_val(row, idx_env_ref)
            if "http" in ref: ref = ""
            env_txt = f"📍 {get_val(row, idx_env_dir)}\n\nCity: {get_val(row, idx_env_com)}\n\nRef: {ref}\n\nRec: {get_val(row, idx_rec_nom)} ({get_val(row, idx_rec_tel)})"

            processed.append({
                "sort": dias, "url": get_val(row, idx_foto), "dias": dias,
                "f1": get_val(row, idx_f_env), "f2": get_val(row, idx_f_ent),
                "cli": cli_txt, "desc": get_val(row, idx_desc), "col": get_val(row, idx_color),
                "fact": fact_txt, "env": env_txt, "tipo": get_val(row, idx_tipo)
            })

        return sorted(processed, key=lambda x: x["sort"])
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return []

@st.cache_data(show_spinner=False)
def get_image(url, _drive_service):
    if not url or "drive.google.com" not in str(url): return None
    match = re.search(r'(?:id=|/d/)([a-zA-Z0-9_-]+)', str(url))
    if not match: return None
    try:
        req = _drive_service.files().get_media(fileId=match.group(1))
        fh = io.BytesIO()
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done: _, done = dl.next_chunk()
        return Image.open(fh)
    except: return None

# ================= 4. INTERFAZ =================
def check_login():
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

def main():
    if not check_login(): return

    with st.sidebar:
        st.write(f"Usuario: **{USER_LOGIN}**")
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.caption(f"Refresco: {REFRESH_SECONDS}s")

    c1, c2, c3 = st.columns([3, 1, 1])
    c1.title("🚴 Tablero Cicla 3D")
    
    # Conectamos
    gc, ds = connect_google()
    
    # Si la conexión falla, paramos aquí
    if not gc:
        st.warning("No se pudo establecer conexión con Google Sheets.")
        return

    rows = load_data(gc)
    c2.metric("Pedidos", len(rows))
    c3.metric("Última Act.", datetime.now().strftime('%H:%M:%S'))
    st.markdown("---")

    cols = [1.2, 0.6, 0.8, 0.8, 1.5, 1.5, 1.5, 1.5, 0.8]
    titulos = ["📸 FOTO", "DÍAS", "ENVÍO", "ENTREGA", "CLIENTE", "DETALLE", "ENVÍO", "FACTURA", "TIPO"]
    for c, t in zip(st.columns(cols), titulos): c.markdown(f"**{t}**")
    st.markdown("---")

    for r in rows:
        with st.container():
            cc = st.columns(cols)
            img = get_image(r['url'], ds)
            if img: cc[0].image(img, use_container_width=True)
            else: cc[0].text("Sin foto")
            
            col = "red" if r['dias'] <= 2 else "green"
            cc[1].markdown(f"<h2 style='color:{col};margin:0;'>{r['dias']}</h2>", unsafe_allow_html=True)
            cc[2].write(r['f1'])
            cc[3].write(r['f2'])
            cc[4].markdown(r['cli'])
            cc[5].markdown(f"**Desc:** {r['desc']}\n\n🎨 {r['col']}")
            cc[6].markdown(r['env'])
            cc[7].markdown(r['fact'])
            if "Retiro" in r['tipo']: cc[8].success(r['tipo'])
            else: cc[8].warning(r['tipo'])
            st.markdown("---")

    time.sleep(REFRESH_SECONDS)
    st.rerun()

if __name__ == "__main__":
    main()
