import streamlit as st
import os

st.title("🕵️‍♂️ Detector de Secretos")

# 1. Verificamos si existe la sección principal
if "gcp_service_account" in st.secrets:
    st.success("✅ ¡La sección [gcp_service_account] EXISTE!")
    
    # 2. Verificamos si hay datos dentro
    creds = st.secrets["gcp_service_account"]
    if "project_id" in creds:
        st.write(f"🔹 Project ID leído: {creds['project_id']}")
    else:
        st.error("❌ La sección existe, pero no encuentro 'project_id' dentro.")
        
    if "private_key" in creds:
        if "-----BEGIN PRIVATE KEY-----" in creds["private_key"]:
             st.success("✅ ¡La Llave Privada se ve correcta!")
        else:
             st.error("⚠️ La llave privada no tiene el formato correcto.")
else:
    st.error("❌ ERROR CRÍTICO: No encuentro la sección [gcp_service_account].")
    st.info("Asegúrate de que en 'Secrets' la primera línea sea exactamente: [gcp_service_account]")
