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

# ================= 1. CONFIGURACIÓN =================
st.set_page_config(
    page_title="Cicla 3D - Tablero",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- SOPORTE IPHONE (HEIC) ---
HEIC_SUPPORT = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    pass

# RUTA LOCAL (Ajusta si cambias de PC)
JSON_FILE_LOCAL = '/Users/jdg_music_/Desktop/Cicla Proyect/service_account.json'

# IDs de Google Sheets
SHEET_ID = '1oeN-Iqrlc2hUuRhYDdrqqd7eez9wwPgGNbgAGi9CUVs'
WORKSHEET_NAME = 'Respuestas de formulario 1'
COL_ESTADO_NUM = 26
COL_ESTADO_IDX = 25

# Credenciales
USER_LOGIN = "Cicla3D"
PASS_LOGIN = "Cicla:D"
REFRESH_SECONDS = 15


# ================= 2. CONEXIÓN =================
@st.cache_resource
def connect_google():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = None

    # Intento 1: Secrets (Streamlit Cloud)
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except Exception:
        pass

    # Intento 2: Archivo Local
    if creds is None and os.path.exists(JSON_FILE_LOCAL):
        try:
            creds = Credentials.from_service_account_file(JSON_FILE_LOCAL, scopes=scopes)
        except:
            pass

    if not creds:
        st.error("❌ ERROR: No se encontraron las credenciales.")
        return None, None

    try:
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None, None


# ================= 3. LÓGICA DE DATOS =================
@st.cache_data(ttl=REFRESH_SECONDS)
def load_data(_gc):
    if _gc is None:
        return []
    try:
        sh = _gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
        all_values = ws.get_all_values()

        if not all_values:
            return []
        headers, rows = all_values[0], all_values[1:]

        def get_col_idx(keywords):
            for i, h in enumerate(headers):
                h_norm = str(h).lower().strip()
                if any(k in h_norm for k in keywords):
                    return i
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
        idx_dir_fac = get_col_idx(["dirección facturación"])
        idx_env_dir = get_col_idx(["dirección de envio"])
        idx_env_com = get_col_idx(["comuna/ciudad"])
        idx_rec_nom = get_col_idx(["nombre de quien recibe"])
        idx_rec_tel = get_col_idx(["telefono de quien recibe"])

        processed = []
        for i, row in enumerate(rows):
            if not any(row):
                continue

            estado_actual = get_val(row, COL_ESTADO_IDX).lower()

            d_raw = get_val(row, idx_dias)
            try:
                dias = int(float(d_raw)) if d_raw else 999
            except:
                dias = 999

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
                "cli_rut": get_val(row, idx_cli_rut),
                "cli_tel": get_val(row, idx_cli_tel),
                "desc": get_val(row, idx_desc),
                "colores": get_val(row, idx_color),
                "req_fact": "si" in get_val(row, idx_req).lower(),
                "fact_det": (
                    f"Raz: {get_val(row, idx_razon)}\n"
                    f"RUT: {get_val(row, idx_rut_fac)}\n"
                    f"Dir: {get_val(row, idx_dir_fac)}"
                ),
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
    """Descarga y normaliza el tamaño de la imagen (Crop 400x250)"""
    if not url or "drive.google.com" not in str(url):
        return None

    match = re.search(r'(?:id=|/d/)([a-zA-Z0-9_-]+)', str(url))
    if not match:
        return None

    try:
        req = _drive_service.files().get_media(fileId=match.group(1))
        fh = io.BytesIO()
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()

        img = Image.open(fh).convert("RGB")

        TARGET_SIZE = (400, 250)
        img = ImageOps.fit(img, TARGET_SIZE, method=Image.Resampling.LANCZOS)

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        return img_byte_arr.getvalue()
    except Exception:
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


# ================= 4. INTERFAZ GRÁFICA =================
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
                    st.error("Datos incorrectos.")
        return False
    return True


def render_card(r, ds, gc, es_finalizado=False):
    with st.container(border=True):

        # --- CABECERA ---
        c1, c2 = st.columns([1, 1])
        if not es_finalizado:
            color = "red" if r['dias'] <= 2 else "orange" if r['dias'] <= 5 else "green"
            c1.markdown(f"<h4 style='color:{color}; margin:0;'>📅 {r['dias']} días</h4>", unsafe_allow_html=True)
        else:
            c1.markdown("✅ **LISTO**")

        tipo_icon = "🏃" if "retiro" in r['tipo'].lower() else "🚚"
        c2.write(f"{tipo_icon} {r['tipo'][:8]}")

        st.markdown("---")

        # --- IMAGEN NORMALIZADA ---
        img_bytes = get_image(r['url'], ds)
        if img_bytes:
            st.image(img_bytes, use_container_width=True)
        else:
            # IMPORTANTE: mismo alto que la imagen (250px) para que todas calcen
            st.markdown(
                "<div style='height: 250px; background-color: #f0f2f6; display:flex; align-items:center; justify-content:center; color:#888; border-radius:5px;'>Sin Imagen</div>",
                unsafe_allow_html=True
            )

        # --- INFORMACIÓN ---
        cliente_corto = r['cli_nom'][:20] + "..." if len(r['cli_nom']) > 20 else r['cli_nom']
        st.caption(f"👤 {cliente_corto}")

        desc_text = r['desc']
        if len(desc_text) > 40:
            desc_text = desc_text[:37] + "..."
        st.markdown(f"**Pedido:** {desc_text}")

        colores_corto = r['colores'][:25] + "..." if len(r['colores']) > 25 else r['colores']
        st.markdown(f"🎨 {colores_corto}")

        # --- FECHAS ---
        st.divider()
        fc1, fc2 = st.columns(2)
        fc1.caption(f"Envío:\n**{r['f_envio']}**")
        fc2.caption(f"Entrega:\n**{r['f_entrega']}**")

        # --- PESTAÑAS ---
        with st.expander("📍 Ver Dirección"):
            st.caption(f"{r['env_dir']}\n{r['env_com']}\nRec: {r['env_rec']}")

        with st.expander("🧾 Datos Facturación"):
            if r['req_fact']:
                st.caption(r['fact_det'])
            else:
                st.caption("❌ No solicitada / Boleta")

        st.write("")

        # --- BOTÓN DE ACCIÓN ---
        if not es_finalizado:
            if st.button("✅ Finalizar", key=f"btn_fin_{r['row_excel']}", use_container_width=True, type="primary"):
                with st.spinner("..."):
                    if cambiar_estado(gc, r['row_excel'], "Finalizado"):
                        time.sleep(1)
                        st.rerun()
        else:
            if st.button("↩️ Recuperar", key=f"btn_rec_{r['row_excel']}", use_container_width=True):
                with st.spinner("..."):
                    if cambiar_estado(gc, r['row_excel'], ""):
                        st.rerun()


def main():
    if not check_login():
        return

    # ✅ CSS global: fuerza que todas las cards con border tengan el mismo alto
    # Ajusta 720px según tu necesidad (650 / 700 / 780, etc.)
    st.markdown("""
    <style>
      /* Cada st.container(border=True) usa este wrapper */
      div[data-testid="stVerticalBlockBorderWrapper"]{
        min-height: 720px;
      }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.header(f"Hola, {USER_LOGIN}")
        if st.button("Cerrar Sesión"):
            st.session_state['logged_in'] = False
            st.rerun()
        st.caption(f"Refresh: {REFRESH_SECONDS}s")
        if HEIC_SUPPORT:
            st.success("iPhone: ON")

    st.title("Tablero de Pedidos")

    gc, ds = connect_google()
    if not gc:
        return

    all_rows = load_data(gc)

    pendientes = [r for r in all_rows if "finalizado" not in r['estado']]
    finalizados = [r for r in all_rows if "finalizado" in r['estado']]

    tab1, tab2 = st.tabs([f"📌 Pendientes ({len(pendientes)})", f"✅ Historial ({len(finalizados)})"])

    COLS_POR_FILA = 4

    with tab1:
        if not pendientes:
            st.success("🎉 ¡Todo al día! No hay pedidos pendientes.")
        else:
            cols = st.columns(COLS_POR_FILA)
            for i, r in enumerate(pendientes):
                with cols[i % COLS_POR_FILA]:
                    render_card(r, ds, gc, es_finalizado=False)

    with tab2:
        if not finalizados:
            st.info("No hay historial.")
        else:
            cols = st.columns(COLS_POR_FILA)
            for i, r in enumerate(finalizados):
                with cols[i % COLS_POR_FILA]:
                    render_card(r, ds, gc, es_finalizado=True)

    time.sleep(REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
