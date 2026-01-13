import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from PIL import Image, ImageOps
import re
import time
import os
from datetime import datetime

# ================= 1. CONFIGURACIÓN DE PÁGINA =================
st.set_page_config(
    page_title="Cicla 3D - Tablero", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- CSS PARA PANTALLA COMPLETA (MODO KIOSK/TV) ---
st.markdown("""
    <style>
        /* Ocultar menú hamburguesa y botón Deploy */
        #MainMenu {visibility: hidden;}
        .stDeployButton {display:none;}
        
        /* Ocultar pie de página */
        footer {visibility: hidden;}
        
        /* Ocultar franja superior de colores */
        header {visibility: hidden;}
        
        /* Ajustar márgenes para usar toda la pantalla */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- SOPORTE IPHONE (HEIC) ---
HEIC_SUPPORT = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    pass

# ================= 2. CONSTANTES Y CREDENCIALES =================

# RUTA LOCAL (Para tu Mac)
JSON_FILE_LOCAL = '/Users/jdg_music_/Desktop/Cicla Proyect/service_account.json'

# IDs de Google Sheets
SHEET_ID = '1oeN-Iqrlc2hUuRhYDdrqqd7eez9wwPgGNbgAGi9CUVs'
WORKSHEET_NAME = 'Respuestas de formulario 1'
COL_ESTADO_NUM = 26
COL_ESTADO_IDX = 25

# Login de la App
USER_LOGIN = "Cicla3D"
PASS_LOGIN = "Cicla:D"
REFRESH_SECONDS = 15

# ================= 3. CONEXIÓN GOOGLE =================
@st.cache_resource
def connect_google():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = None
    
    # Opción A: Buscar en Streamlit Secrets (Nube)
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            # Corregir formato de saltos de línea en la clave privada
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception:
        pass

    # Opción B: Buscar Archivo Local (Mac/PC)
    if creds is None and os.path.exists(JSON_FILE_LOCAL):
        try: 
            creds = Credentials.from_service_account_file(JSON_FILE_LOCAL, scopes=scopes)
        except: 
            pass

    if not creds:
        st.error("❌ ERROR CRÍTICO: No se encontraron las credenciales (ni en Secrets ni local).")
        return None, None

    try:
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Error conectando con Google: {e}")
        return None, None

# ================= 4. LÓGICA DE DATOS =================
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

        # Mapeo de columnas (Busca por palabras clave para ser robusto)
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
            
            estado_actual = get_val(row, COL_ESTADO_IDX).lower()
            
            # Procesar días (manejo de errores si está vacío)
            d_raw = get_val(row, idx_dias)
            try:
                if d_raw: dias = int(float(d_raw))
                else: dias = 999
            except: dias = 999
            
            processed.append({
                "row_excel": i + 2,
                "estado": estado_actual,
                "sort": dias, 
                "url": get_val(row, idx_foto), 
                "dias": dias,
                "f_envio": get_val(row, idx_f_env), 
                "f_entrega": get_val(row, idx_f_ent),
                "cli_nom": get_val(row, idx_cli_nom),
                "cli_emp": get_val(row, idx_cli_emp),
                "desc": get_val(row, idx_desc), 
                "colores": get_val(row, idx_color),
                "req_fact": "si" in get_val(row, idx_req).lower(),
                "fact_det": f"Raz: {get_val(row, idx_razon)}\nRUT: {get_val(row, idx_rut_fac)}\nDir: {get_val(row, idx_dir_fac)}",
                "env_dir": get_val(row, idx_env_dir),
                "env_com": get_val(row, idx_env_com),
                "env_rec": f"{get_val(row, idx_rec_nom)} ({get_val(row, idx_rec_tel)})",
                "tipo": get_val(row, idx_tipo)
            })

        return sorted(processed, key=lambda x: x["sort"])
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return []

@st.cache_data(show_spinner=False)
def get_image(url, _drive_service):
    """Descarga y recorta la imagen a un tamaño exacto (400x250)"""
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

        # --- RECORTE MÁGICO ---
        TARGET_SIZE = (400, 250) # Ancho, Alto
        img = ImageOps.fit(img, TARGET_SIZE, method=Image.Resampling.LANCZOS)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
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
        st.error(f"Error guardando cambios: {e}")
        return False

# ================= 5. RENDERIZADO DE TARJETAS =================

def check_login():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔐 Login Cicla 3D")
            st.markdown("---")
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Ingresar", type="primary"):
                if username == USER_LOGIN and password == PASS_LOGIN:
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")
        return False
    return True

def render_card(r, ds, gc, es_finalizado=False):
    with st.container(border=True):
        # --- 1. CABECERA (Días y Tipo) ---
        c1, c2 = st.columns([1, 1])
        if not es_finalizado:
            color = "red" if r['dias'] <= 2 else "orange" if r['dias'] <= 5 else "green"
            c1.markdown(f"<h4 style='color:{color}; margin:0;'>📅 {r['dias']} días</h4>", unsafe_allow_html=True)
        else:
            c1.markdown("✅ **LISTO**")
        
        tipo_icon = "🏃" if "retiro" in r['tipo'].lower() else "🚚"
        c2.write(f"{tipo_icon} {r['tipo'][:8]}") # Truncar si es muy largo

        st.markdown("---")
        
        # --- 2. IMAGEN UNIFICADA ---
        img_bytes = get_image(r['url'], ds)
        if img_bytes:
            st.image(img_bytes, use_container_width=True)
        else:
            # Placeholder gris exacto de 400x250 (proporcional)
            st.markdown(
                "<div style='height: 150px; background-color: #f0f2f6; display: flex; align-items: center; justify-content: center; color: #888; border-radius: 5px; margin-bottom: 10px;'>Sin Imagen</div>", 
                unsafe_allow_html=True
            )

        # --- 3. INFORMACIÓN DEL PEDIDO ---
        # Cliente (Cortado para que no descuadre)
        cliente_corto = r['cli_nom'][:22] + "..." if len(r['cli_nom']) > 22 else r['cli_nom']
        st.caption(f"👤 {cliente_corto}")
        
        # Descripción (Máximo 40 caracteres)
        desc_text = r['desc']
        if len(desc_text) > 40:
            desc_text = desc_text[:37] + "..."
        st.markdown(f"**Pedido:** {desc_text}")
        
        # Colores (Máximo 25 caracteres)
        colores_corto = r['colores'][:25] + "..." if len(r['colores']) > 25 else r['colores']
        st.markdown(f"🎨 {colores_corto}")
        
        # --- 4. FECHAS CLAVE ---
        st.divider()
        fc1, fc2 = st.columns(2)
        fc1.caption(f"Envío:\n**{r['f_envio']}**")
        fc2.caption(f"Entrega:\n**{r['f_entrega']}**")

        # --- 5. DETALLES (ESTRUCTURA FIJA) ---
        # Dirección siempre visible (aunque vacía)
        with st.expander("📍 Dirección Envío"):
            st.caption(f"{r['env_dir']}\n{r['env_com']}\nRec: {r['env_rec']}")

        # Factura SIEMPRE visible para alinear altura
        with st.expander("🧾 Datos Facturación"):
            if r['req_fact']:
                st.caption(r['fact_det'])
            else:
                st.caption("❌ No solicitada / Boleta")
        
        st.write("") # Pequeño espaciador
        
        # --- 6. BOTÓN DE ACCIÓN ---
        if not es_finalizado:
            # Botón Primario para finalizar
            if st.button("✅ Finalizar", key=f"btn_fin_{r['row_excel']}", use_container_width=True, type="primary"):
                with st.spinner("Actualizando..."):
                    if cambiar_estado(gc, r['row_excel'], "Finalizado"):
                        time.sleep(0.5)
                        st.rerun()
        else:
            # Botón Secundario para recuperar
            if st.button("↩️ Recuperar", key=f"btn_rec_{r['row_excel']}", use_container_width=True):
                with st.spinner("Recuperando..."):
                    if cambiar_estado(gc, r['row_excel'], ""):
                        st.rerun()

# ================= 6. FUNCIÓN PRINCIPAL =================
def main():
    if not check_login(): return

    # Sidebar minimalista
    with st.sidebar:
        st.header(f"Hola, {USER_LOGIN}")
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.caption(f"Auto-refresco: {REFRESH_SECONDS}s")
        if HEIC_SUPPORT: st.success("iPhone: ON")

    st.title("🚴 Tablero de Pedidos")
    
    gc, ds = connect_google()
    if not gc: return

    all_rows = load_data(gc)
    
    # Separar pendientes de finalizados
    pendientes = [r for r in all_rows if "finalizado" not in r['estado']]
    finalizados = [r for r in all_rows if "finalizado" in r['estado']]
    
    tab1, tab2 = st.tabs([f"📌 Pendientes ({len(pendientes)})", f"✅ Historial ({len(finalizados)})"])

    # CONFIGURACIÓN DE GRILLA
    COLS_POR_FILA = 4 

    # --- PESTAÑA 1: PENDIENTES ---
    with tab1:
        if not pendientes:
            st.success("🎉 ¡Todo limpio! No hay pedidos pendientes.")
        else:
            cols = st.columns(COLS_POR_FILA)
            for i, r in enumerate(pendientes):
                col_actual = cols[i % COLS_POR_FILA]
                with col_actual:
                    render_card(r, ds, gc, es_finalizado=False)

    # --- PESTAÑA 2: FINALIZADOS ---
    with tab2:
        if not finalizados:
            st.info("No hay historial disponible.")
        else:
            cols = st.columns(COLS_POR_FILA)
            for i, r in enumerate(finalizados):
                col_actual = cols[i % COLS_POR_FILA]
                with col_actual:
                    render_card(r, ds, gc, es_finalizado=True)

    time.sleep(REFRESH_SECONDS)
    st.rerun()

if __name__ == "__main__":
    main()
