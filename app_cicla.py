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

# ================= 1. CONFIGURACIÓN =================
st.set_page_config(page_title="Cicla 3D - Pedidos", layout="wide")

# --- SOPORTE IPHONE (HEIC) ---
HEIC_SUPPORT = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    pass

# RUTA LOCAL (Solo se usa si lo corres en tu Mac)
JSON_FILE_LOCAL = '/Users/jdg_music_/Desktop/Cicla Proyect/service_account.json'
SHEET_ID = '1oeN-Iqrlc2hUuRhYDdrqqd7eez9wwPgGNbgAGi9CUVs'
WORKSHEET_NAME = 'Respuestas de formulario 1'
COL_ESTADO_NUM = 26
COL_ESTADO_IDX = 25

USER_LOGIN = "Cicla3D"
PASS_LOGIN = "Cicla:D"
REFRESH_SECONDS = 5

# ================= 2. CONEXIÓN =================
@st.cache_resource
def connect_google():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = None
    
    # Intento 1: Secrets (Nube)
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception:
        pass

    # Intento 2: Local (Mac)
    if creds is None and os.path.exists(JSON_FILE_LOCAL):
        try: 
            creds = Credentials.from_service_account_file(JSON_FILE_LOCAL, scopes=scopes)
        except: 
            pass

    if not creds:
        st.error("❌ ERROR: No hay credenciales.")
        return None, None

    try:
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Error conexión: {e}")
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
        for i, row in enumerate(rows):
            if not any(row): continue
            
            # Recuperamos el estado
            estado_actual = get_val(row, COL_ESTADO_IDX).lower()

            d_raw = get_val(row, idx_dias)
            try:
                if d_raw: dias = int(float(d_raw))
                else: dias = 999
            except: dias = 999
            
            cli_txt = f"**{get_val(row, idx_cli_nom)}**\n\n🏢 {get_val(row, idx_cli_emp)}\n\n🆔 {get_val(row, idx_cli_rut)}\n\n📞 {get_val(row, idx_cli_tel)}"
            
            fact_txt = "❌ No"
            if "si" in get_val(row, idx_req).lower():
                fact_txt = f"✅ **SI**\n\nRaz: {get_val(row, idx_razon)}\n\nRUT: {get_val(row, idx_rut_fac)}\n\nGiro: {get_val(row, idx_giro)}\n\nDir: {get_val(row, idx_dir_fac)}"

            ref = get_val(row, idx_env_ref)
            if "http" in ref: ref = ""
            env_txt = f"📍 {get_val(row, idx_env_dir)}\n\nCity: {get_val(row, idx_env_com)}\n\nRef: {ref}\n\nRec: {get_val(row, idx_rec_nom)} ({get_val(row, idx_rec_tel)})"

            processed.append({
                "row_excel": i + 2,
                "estado": estado_actual,
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
        
        img = Image.open(fh)
        img = img.convert("RGB") 
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
                
    except Exception as e:
        return None

def cambiar_estado(gc, row_num, nuevo_estado):
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
        ws.update_cell(row_num, COL_ESTADO_NUM, nuevo_estado)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

# ================= 4. MAIN =================
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
                    st.error("Datos incorrectos.")
        return False
    return True

def render_row(r, ds, gc, es_finalizado=False):
    cols_width = [1.2, 0.6, 0.8, 0.8, 1.5, 1.5, 1.5, 1.5, 0.8, 0.6]
    cc = st.columns(cols_width)
    
    img_bytes = get_image(r['url'], ds)
    if img_bytes: cc[0].image(img_bytes, use_container_width=True)
    elif r['url']: cc[0].warning("⚠️ Error")
    else: cc[0].text("Sin foto")
    
    col_dias = "red" if r['dias'] <= 2 else "green"
    cc[1].markdown(f"<h2 style='color:{col_dias};margin:0;'>{r['dias']}</h2>", unsafe_allow_html=True)
    cc[2].write(r['f1'])
    cc[3].write(r['f2'])
    cc[4].markdown(r['cli'])
    cc[5].markdown(f"**Desc:** {r['desc']}\n\n🎨 {r['col']}")
    cc[6].markdown(r['env'])
    cc[7].markdown(r['fact'])
    
    if "Retiro" in r['tipo']: cc[8].success(r['tipo'])
    else: cc[8].warning(r['tipo'])

    if not es_finalizado:
        if cc[9].button("✅", key=f"fin_{r['row_excel']}", help="Finalizar"):
            with st.spinner("Finalizando..."):
                if cambiar_estado(gc, r['row_excel'], "Finalizado"):
                    st.success("!")
                    time.sleep(0.5)
                    st.rerun()
    else:
        if cc[9].button("↩️", key=f"rev_{r['row_excel']}", help="Recuperar"):
            with st.spinner("Recuperando..."):
                if cambiar_estado(gc, r['row_excel'], ""): 
                    st.success("!")
                    time.sleep(0.5)
                    st.rerun()
    
    st.markdown("---")

def main():
    if not check_login(): return

    with st.sidebar:
        st.write(f"Usuario: **{USER_LOGIN}**")
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.caption(f"Refresco: {REFRESH_SECONDS}s")
        if HEIC_SUPPORT: st.success("✅ Soporte iPhone")
        else: st.warning("⚠️ Sin soporte iPhone")

    st.title("Tablero Cicla 3D")
    
    gc, ds = connect_google()
    if not gc: return

    all_rows = load_data(gc)
    pendientes = [r for r in all_rows if "finalizado" not in r['estado']]
    finalizados = [r for r in all_rows if "finalizado" in r['estado']]
    
    tab1, tab2 = st.tabs([f"Pendientes ({len(pendientes)})", f"✅ Finalizados ({len(finalizados)})"])

    titulos = ["📸 FOTO", "DÍAS", "ENVÍO", "ENTREGA", "CLIENTE", "DETALLE", "ENVÍO", "FACTURA", "TIPO", "ACCIÓN"]
    cols_titulos = [1.2, 0.6, 0.8, 0.8, 1.5, 1.5, 1.5, 1.5, 0.8, 0.6]

    with tab1:
        st.markdown("---")
        for c, t in zip(st.columns(cols_titulos), titulos): c.markdown(f"**{t}**")
        st.markdown("---")
        for r in pendientes:
            render_row(r, ds, gc, es_finalizado=False)

    with tab2:
        st.info("Historial de pedidos entregados.")
        st.markdown("---")
        for c, t in zip(st.columns(cols_titulos), titulos): c.markdown(f"**{t}**")
        st.markdown("---")
        for r in finalizados:
            render_row(r, ds, gc, es_finalizado=True)

    time.sleep(REFRESH_SECONDS)
    st.rerun()

if __name__ == "__main__":
    main()
