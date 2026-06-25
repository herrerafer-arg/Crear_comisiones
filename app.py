import streamlit as st
import pandas as pd
from crear_comisiones_v14 import procesar_comisiones

st.set_page_config(page_title="Asignador de Comisiones", layout="wide", page_icon="🏫")

st.title("🏫 Gestor e Interfaz de Asignación de Comisiones")
st.write("Agrega materias dinámicamente, define sus comisiones, sube sus listas y procesa los resultados.")

# --- INICIALIZACIÓN DE ESTADOS ---
if "lista_materias" not in st.session_state:
    st.session_state["lista_materias"] = []

if "resultados_procesamiento" not in st.session_state:
    st.session_state["resultados_procesamiento"] = None

# --- BOTÓN DE REINICIO GENERAL ---
if st.session_state["resultados_procesamiento"] is not None:
    if st.button("🔄 Reiniciar Aplicación / Cargar Nuevas Materias", type="secondary"):
        st.session_state["lista_materias"] = []
        st.session_state["resultados_procesamiento"] = None
        st.rerun()

# --- SECCIÓN: Configuración de Materias ---
st.header("1. Configuración de Materias")

if st.session_state["resultados_procesamiento"] is None:
    with st.form(key="formulario_materia", clear_on_submit=True):
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            nueva_materia = st.text_input("Nombre de la nueva materia:", placeholder="Ej. Fisicoquímica, Física I... (Presiona Enter para agregar)")
        with col_btn:
            st.write("##") 
            boton_agregar = st.form_submit_button("➕ Agregar Materia")

        if boton_agregar and nueva_materia:
            materia_limpia = nueva_materia.strip()
            if materia_limpia and materia_limpia not in st.session_state["lista_materias"]:
                st.session_state["lista_materias"].append(materia_limpia)
                st.rerun()

# Contenedores dinámicos de datos para enviar al backend
materias_info = {}
uploaded_files = {}

st.markdown("---")
st.subheader("Materias activas y sus archivos:")

if not st.session_state["lista_materias"]:
    st.info("💡 No hay materias cargadas. Escribe el nombre de una materia arriba y presiona ENTER.")

# Renderizar bloques de materias dinámicas
for mat in st.session_state["lista_materias"]:
    with st.expander(f"📚 {mat}", expanded=(st.session_state["resultados_procesamiento"] is None)):
        col1, col2, col3 = st.columns([3, 4, 1])
        with col1:
            n_comisiones = st.number_input(f"Número de comisiones ({mat}):", min_value=1, value=8, key=f"num_{mat}", disabled=(st.session_state["resultados_procesamiento"] is not None))
            
            # Control de cupo opcional por comisión
            activar_limite = st.checkbox(f"Definir alumnos máximos por comisión ({mat})", key=f"chk_limit_{mat}", disabled=(st.session_state["resultados_procesamiento"] is not None))
            
            if activar_limite:
                max_alumnos = st.number_input(f"Máximo de alumnos por comisión ({mat}):", min_value=1, value=30, key=f"max_al_{mat}", disabled=(st.session_state["resultados_procesamiento"] is not None))
            else:
                max_alumnos = None
                
            # Guardamos la sub-estructura de diccionarios para el backend
            materias_info[mat] = {
                "n_comisiones": n_comisiones,
                "max_alumnos": max_alumnos
            }
        with col2:
            archivos = st.file_uploader(f"Subir archivos XLS para {mat}:", accept_multiple_files=True, key=f"file_{mat}", type=["xls", "xlsx"], disabled=(st.session_state["resultados_procesamiento"] is not None))
            uploaded_files[mat] = archivos
        with col3:
            st.write("##")
            if st.button("🗑️ Quitar", key=f"del_{mat}", disabled=(st.session_state["resultados_procesamiento"] is not None)):
                st.session_state["lista_materias"].remove(mat)
                st.rerun()

st.markdown("---")
st.header("2. Configuraciones Opcionales")
file_forzados = st.file_uploader("Subir archivo de comisiones forzadas (comisiones_forzadas.xls):", type=["xls", "xlsx"], disabled=(st.session_state["resultados_procesamiento"] is not None))

# --- SECCIÓN: Procesamiento ---
st.markdown("---")
st.header("3. Procesar y Descargar")

boton_procesar = st.button("🚀 Ejecutar Algoritmo de Asignación", type="primary", disabled=(st.session_state["resultados_procesamiento"] is not None))

if boton_procesar:
    error_validacion = False
    for mat in st.session_state["lista_materias"]:
        if not uploaded_files[mat]:
            st.error(f"Falta adjuntar archivos para la materia: **{mat}**")
            error_validacion = True
            
    if not st.session_state["lista_materias"]:
        st.error("Debes tener al menos una materia configurada.")
        error_validacion = True

    if not error_validacion:
        with st.spinner("Procesando asignaciones y aplicando coherencia..."):
            try:
                df_forzados = pd.read_excel(file_forzados) if file_forzados is not None else None
                
                # Ejecución de lógica
                archivos_salida, log_text, df_coh = procesar_comisiones(materias_info, uploaded_files, df_forzados)
                
                if archivos_salida:
                    st.session_state["resultados_procesamiento"] = {
                        "archivos_salida": archivos_salida,
                        "log_text": log_text,
                        "df_coh": df_coh
                    }
                    st.rerun()
                            
            except Exception as e:
                st.error(f"Ocurrió un error inesperado al procesar los datos: {e}")

# --- SECCIÓN DE RESULTADOS ---
if st.session_state["resultados_procesamiento"] is not None:
    res = st.session_state["resultados_procesamiento"]
    
    st.success("¡Asignación completada con éxito! Los resultados están bloqueados abajo. Puedes descargar los archivos individualmente sin perder los datos.")
    
    st.subheader("📄 Salida del Sistema")
    st.text_area("Log de Consola", res["log_text"], height=300)
    
    st.subheader("📥 Descargar Resultados")
    col_dl, col_dr = st.columns(2)
    
    with col_dl:
        st.markdown("**Excels por Materia:**")
        for nombre_archivo, data_bytes in res["archivos_salida"].items():
            if nombre_archivo != "reporte_coherencia_comisiones.xlsx":
                st.download_button(
                    label=f"💾 Descargar {nombre_archivo}",
                    data=data_bytes,
                    file_name=nombre_archivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_{nombre_archivo}"
                )
    with col_dr:
        st.markdown("**Reporte Global:**")
        st.download_button(
            label="📊 Descargar reporte_coherencia_comisiones.xlsx",
            data=res["archivos_salida"]["reporte_coherencia_comisiones.xlsx"],
            file_name="reporte_coherencia_comisiones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
        with st.expander("Ver vista previa del reporte de coherencia"):
            st.dataframe(res["df_coh"])

