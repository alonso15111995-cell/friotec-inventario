import streamlit as st
import pandas as pd
import time
import base64
import requests
import gspread
from datetime import datetime, timedelta, date
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Friotec Industrias - Sistema de Inventario", layout="wide")

# ==========================================
# SISTEMA DE SEGURIDAD (LOGIN)
# ==========================================
def check_password():
    def password_entered():
        clave_correcta = st.secrets.get("password_acceso", "12345")
        if st.session_state["password"] == clave_correcta:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("### 🔒 Área Restringida - Friotec Industrias")
        st.text_input("Por favor, introduce la contraseña de acceso:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔒 Área Restringida - Friotec Industrias")
        st.text_input("Por favor, introduce la contraseña de acceso:", type="password", on_change=password_entered, key="password")
        st.error("😕 Contraseña incorrecta. Intenta de nuevo.")
        return False
    return True

if not check_password():
    st.stop()


# ==========================================
# CÓDIGO PRINCIPAL DEL INVENTARIO
# ==========================================
IMGBB_API_KEY = "7f7fe7f1db90ef5142e419f559470c39"

@st.cache_resource
def conectar_nube():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        dict_credenciales = dict(st.secrets["gcp_service_account"])
        credenciales = Credentials.from_service_account_info(dict_credenciales, scopes=scopes)
    else:
        credenciales = Credentials.from_service_account_file('credenciales.json', scopes=scopes)
        
    cliente_sheets = gspread.authorize(credenciales)
    return cliente_sheets.open("INVENTARIO_PROTEC_LIMPIO")

@st.cache_data(ttl=5)
def cargar_datos():
    hoja = conectar_nube()
    df_prod = pd.DataFrame(hoja.worksheet('Productos').get_all_records())
    df_stock = pd.DataFrame(hoja.worksheet('Stock_Tiendas').get_all_records())
    df_mov = pd.DataFrame(hoja.worksheet('Movimientos').get_all_records())
    
    try:
        df_config = pd.DataFrame(hoja.worksheet('Configuracion').get_all_records())
    except:
        df_config = pd.DataFrame([
            {'Tienda': 'T1_Gina', 'Nombre_Visible': 'Tienda 01', 'Encargada': 'Gina'},
            {'Tienda': 'T2_Celianny', 'Nombre_Visible': 'Tienda 02', 'Encargada': 'Celianny'},
            {'Tienda': 'T3_San_Jose', 'Nombre_Visible': 'Tienda 03', 'Encargada': 'San Jose'},
        ])
        
    if not df_prod.empty:
        df_prod['ID_Producto'] = df_prod['ID_Producto'].astype(str)
    if not df_stock.empty:
        df_stock['ID_Producto'] = df_stock['ID_Producto'].astype(str)
    return df_prod, df_stock, df_mov, df_config

def subir_foto_imgbb(archivo_subido):
    if archivo_subido is None:
        return ""
    url = "https://api.imgbb.com/1/upload"
    imagen_b64 = base64.b64encode(archivo_subido.getvalue())
    payload = {"key": IMGBB_API_KEY, "image": imagen_b64}
    
    respuesta = requests.post(url, payload)
    if respuesta.status_code == 200:
        return respuesta.json()['data']['url']
    return ""

def sincronizar_nube_completa(df_prod, df_stock, df_mov):
    hoja = conectar_nube()
    df_prod = df_prod.fillna("")
    df_stock = df_stock.fillna("")
    df_mov = df_mov.fillna("")
    
    ws_prod = hoja.worksheet('Productos')
    ws_prod.clear()
    ws_prod.update([df_prod.columns.values.tolist()] + df_prod.values.tolist())
    
    ws_stock = hoja.worksheet('Stock_Tiendas')
    ws_stock.clear()
    ws_stock.update([df_stock.columns.values.tolist()] + df_stock.values.tolist())
    
    ws_mov = hoja.worksheet('Movimientos')
    ws_mov.clear()
    ws_mov.update([df_mov.columns.values.tolist()] + df_mov.values.tolist())
    
    st.cache_data.clear()

def guardar_configuracion_tiendas(df_config):
    hoja = conectar_nube()
    try:
        ws_config = hoja.worksheet('Configuracion')
    except:
        ws_config = hoja.add_worksheet(title='Configuracion', rows=10, cols=5)
    
    ws_config.clear()
    ws_config.update([df_config.columns.values.tolist()] + df_config.values.tolist())
    st.cache_data.clear()

def guardar_nuevo_producto(nombre, categoria, p_unitario, p_minimo, archivo_foto):
    df_prod, df_stock, df_mov, _ = cargar_datos()
    ids_actuales = df_prod['ID_Producto'].str.replace('PROD-', '').astype(int)
    nuevo_num = ids_actuales.max() + 1 if not ids_actuales.empty else 1
    nuevo_id = f"PROD-{str(nuevo_num).zfill(4)}"
    
    ruta_foto = subir_foto_imgbb(archivo_foto)
    
    nueva_fila_prod = {
        'ID_Producto': nuevo_id, 'Categoría': categoria.upper(), 'Nombre del Producto': nombre,
        'Precio Unitario': float(p_unitario), 'Precio Minimo': float(p_minimo), 'Foto': ruta_foto, 'Stock_Minimo': 2
    }
    df_prod = pd.concat([df_prod, pd.DataFrame([nueva_fila_prod])], ignore_index=True)
    
    nueva_fila_stock = {
        'ID_Producto': nuevo_id, 'Nombre del Producto': nombre,
        'T1_Gina': 0, 'T2_Celianny': 0, 'T3_San_Jose': 0, 'A1_Tupac': 0, 'A2_Collasuyo': 0
    }
    df_stock = pd.concat([df_stock, pd.DataFrame([nueva_fila_stock])], ignore_index=True)
    
    df_prod = df_prod.sort_values(by=['Categoría', 'Nombre del Producto'])
    sincronizar_nube_completa(df_prod, df_stock, df_mov)

def actualizar_producto(id_prod, nuevo_nombre, nueva_categoria, nuevo_p_unitario, nuevo_p_minimo, archivo_foto, foto_actual, eliminar_foto):
    df_prod, df_stock, df_mov, _ = cargar_datos()
    idx_prod = df_prod.index[df_prod['ID_Producto'] == id_prod].tolist()[0]
    
    if eliminar_foto:
        ruta_foto = ""
    elif archivo_foto is not None:
        ruta_foto = subir_foto_imgbb(archivo_foto)
    else:
        ruta_foto = foto_actual
    
    df_prod.at[idx_prod, 'Nombre del Producto'] = nuevo_nombre
    df_prod.at[idx_prod, 'Categoría'] = nueva_categoria.upper()
    df_prod.at[idx_prod, 'Precio Unitario'] = float(nuevo_p_unitario)
    df_prod.at[idx_prod, 'Precio Minimo'] = float(nuevo_p_minimo)
    df_prod.at[idx_prod, 'Foto'] = ruta_foto
    
    idx_stock = df_stock.index[df_stock['ID_Producto'] == id_prod].tolist()[0]
    df_stock.at[idx_stock, 'Nombre del Producto'] = nuevo_nombre
    
    df_prod = df_prod.sort_values(by=['Categoría', 'Nombre del Producto'])
    sincronizar_nube_completa(df_prod, df_stock, df_mov)

def registrar_movimiento(tipo, producto_nombre, cantidad, origen, destino, nota, fecha_personalizada):
    df_prod, df_stock, df_mov, _ = cargar_datos()
    
    prod_row = df_prod[df_prod['Nombre del Producto'] == producto_nombre]
    if prod_row.empty:
        return False, "Producto no encontrado."
    
    id_prod = prod_row.iloc[0]['ID_Producto']
    idx_stock = df_stock.index[df_stock['ID_Producto'] == id_prod].tolist()[0]
    
    cantidad = int(cantidad)
    hora_actual = datetime.now().strftime("%H:%M:%S")
    fecha_final_str = f"{fecha_personalizada.strftime('%Y-%m-%d')} {hora_actual}"
    
    if tipo == "INGRESO":
        actual = int(df_stock.at[idx_stock, destino] or 0)
        df_stock.at[idx_stock, destino] = actual + cantidad
    elif tipo == "SALIDA":
        actual = int(df_stock.at[idx_stock, origen] or 0)
        if actual < cantidad:
            return False, f"Stock insuficiente en {origen}. Stock actual: {actual}"
        df_stock.at[idx_stock, origen] = actual - cantidad
    elif tipo == "TRASLADO":
        actual_origen = int(df_stock.at[idx_stock, origen] or 0)
        if actual_origen < cantidad:
            return False, f"Stock insuficiente en origen ({origen}). Stock actual: {actual_origen}"
        actual_destino = int(df_stock.at[idx_stock, destino] or 0)
        df_stock.at[idx_stock, origen] = actual_origen - cantidad
        df_stock.at[idx_stock, destino] = actual_destino + cantidad

    nueva_mov = {
        'Fecha': fecha_final_str,
        'Tipo': tipo,
        'ID_Producto': id_prod,
        'Producto': producto_nombre,
        'Cantidad': cantidad,
        'Origen': origen if tipo in ["SALIDA", "TRASLADO"] else "PROVEEDOR",
        'Destino': destino if tipo in ["INGRESO", "TRASLADO"] else "CLIENTE",
        'Nota': nota
    }
    df_mov = pd.concat([df_mov, pd.DataFrame([nueva_mov])], ignore_index=True)
    
    sincronizar_nube_completa(df_prod, df_stock, df_mov)
    return True, "¡Movimiento registrado con éxito!"

def anular_ultimo_movimiento():
    df_prod, df_stock, df_mov, _ = cargar_datos()
    if df_mov.empty:
        return False, "No hay movimientos para anular."
    
    ultimo = df_mov.iloc[-1]
    tipo = ultimo['Tipo']
    id_prod = str(ultimo['ID_Producto'])
    cantidad = int(ultimo['Cantidad'])
    origen = ultimo['Origen']
    destino = ultimo['Destino']
    
    idx_stock_list = df_stock.index[df_stock['ID_Producto'] == id_prod].tolist()
    if idx_stock_list:
        idx_stock = idx_stock_list[0]
        if tipo == "INGRESO":
            actual = int(df_stock.at[idx_stock, destino] or 0)
            df_stock.at[idx_stock, destino] = max(0, actual - cantidad)
        elif tipo == "SALIDA":
            actual = int(df_stock.at[idx_stock, origen] or 0)
            df_stock.at[idx_stock, origen] = actual + cantidad
        elif tipo == "TRASLADO":
            actual_origen = int(df_stock.at[idx_stock, origen] or 0)
            actual_destino = int(df_stock.at[idx_stock, destino] or 0)
            df_stock.at[idx_stock, origen] = actual_origen + cantidad
            df_stock.at[idx_stock, destino] = max(0, actual_destino - cantidad)
            
    df_mov = df_mov.iloc[:-1].reset_index(drop=True)
    sincronizar_nube_completa(df_prod, df_stock, df_mov)
    return True, "¡Último movimiento anulado y stock revertido con éxito!"


# --- CARGA DE DATOS Y CABECERA ---
try:
    df_productos, df_stock, df_movimientos, df_config = cargar_datos()
except Exception as e:
    st.error(f"Error conectando a la nube: {e}")
    st.stop()

col_logo, col_titulo = st.columns([1, 8])
with col_logo:
    try:
        st.image("logo_friotec.png", width=70)
    except:
        st.write("📦")
with col_titulo:
    st.title("FRIOTEC INDUSTRIAS")
    st.caption("Sistema Integral de Inventario y Control Multi-Tienda")

st.write("---")

tab_productos, tab_tiendas, tab_movimientos, tab_inventario = st.tabs([
    "📋 PRODUCTOS", "🏪 TIENDAS", "🔄 MOVIMIENTOS", "📊 INVENTARIO Y STOCK"
])

# ==========================================
# PESTAÑA 1: PRODUCTOS
# ==========================================
with tab_productos:
    col_add, col_edit = st.columns(2)
    categorias_lista = list(df_productos['Categoría'].dropna().unique())
    
    with col_add:
        with st.expander("➕ Agregar Nuevo Producto"):
            with st.form("form_nuevo"):
                n_nombre = st.text_input("Nombre del Producto")
                opciones_cat = categorias_lista + ["➕ Crear nueva categoría..."]
                cat_sel = st.selectbox("Categoría", opciones_cat)
                n_cat_nueva = st.text_input("Escribe la nueva categoría:") if cat_sel == "➕ Crear nueva categoría..." else ""
                n_cat_final = n_cat_nueva if cat_sel == "➕ Crear nueva categoría..." else cat_sel
                
                c_p1, c_p2 = st.columns(2)
                with c_p1: n_p_uni = st.number_input("Precio Unitario (S/.)", min_value=0.0, step=1.0)
                with c_p2: n_p_min = st.number_input("Precio Mínimo (S/.)", min_value=0.0, step=1.0)
                
                n_foto = st.file_uploader("Tomar o subir foto", type=['png', 'jpg', 'jpeg'])
                
                if st.form_submit_button("Guardar en la Nube"):
                    if not n_nombre.strip() or not n_cat_final.strip():
                        st.error("Nombre y Categoría son obligatorios.")
                    else:
                        st.info("Subiendo imagen y datos... ⏳")
                        guardar_nuevo_producto(n_nombre, n_cat_final, n_p_uni, n_p_min, n_foto)
                        st.success("¡Producto guardado!")
                        time.sleep(1)
                        st.rerun()

    with col_edit:
        with st.expander("✏️ Editar Producto / Cambiar o Quitar Foto"):
            prod_buscar = st.selectbox("Selecciona un producto para editar:", ["(Elige uno)"] + df_productos['Nombre del Producto'].tolist())
            if prod_buscar != "(Elige uno)":
                d_prod = df_productos[df_productos['Nombre del Producto'] == prod_buscar].iloc[0]
                with st.form("form_editar"):
                    e_nombre = st.text_input("Nombre", value=d_prod['Nombre del Producto'])
                    idx_cat = categorias_lista.index(d_prod['Categoría']) if d_prod['Categoría'] in categorias_lista else 0
                    e_cat_sel = st.selectbox("Categoría", opciones_cat, index=idx_cat)
                    e_cat_nueva = st.text_input("Escribe la nueva categoría:") if e_cat_sel == "➕ Crear nueva categoría..." else ""
                    e_cat_final = e_cat_nueva if e_cat_sel == "➕ Crear nueva categoría..." else e_cat_sel
                    
                    ce1, ce2 = st.columns(2)
                    with ce1: e_p_uni = st.number_input("Precio Unitario (S/.)", value=float(d_prod['Precio Unitario'] or 0), min_value=0.0, step=1.0)
                    with ce2: e_p_min = st.number_input("Precio Mínimo (S/.)", value=float(d_prod['Precio Minimo'] or 0), min_value=0.0, step=1.0)
                    
                    tiene_foto = pd.notna(d_prod['Foto']) and str(d_prod['Foto']).startswith("http")
                    if tiene_foto:
                        st.image(d_prod['Foto'], width=150, caption="Foto actual")
                    
                    eliminar_foto = st.checkbox("🗑️ Eliminar foto actual (dejar sin imagen)")
                    e_foto = st.file_uploader("Tomar o cambiar foto nueva", type=['png', 'jpg', 'jpeg'])
                    
                    if st.form_submit_button("💾 Actualizar Nube"):
                        st.info("Sincronizando cambios... ⏳")
                        actualizar_producto(d_prod['ID_Producto'], e_nombre, e_cat_final, e_p_uni, e_p_min, e_foto, d_prod['Foto'], eliminar_foto)
                        st.success("¡Actualizado con éxito!")
                        time.sleep(1)
                        st.rerun()

    st.write("---")
    
    col1, col2 = st.columns(2)
    with col1: buscar = st.text_input("🔍 Buscar producto:")
    with col2: filtro_cat = st.selectbox("📂 Filtrar por Categoría:", ["TODAS"] + categorias_lista)
        
    df_filtrado = df_productos.copy()
    if buscar: df_filtrado = df_filtrado[df_filtrado['Nombre del Producto'].str.contains(buscar, case=False, na=False)]
    if filtro_cat != "TODAS": df_filtrado = df_filtrado[df_filtrado['Categoría'] == filtro_cat]
        
    categorias_a_mostrar = df_filtrado['Categoría'].dropna().unique()
    for cat in categorias_a_mostrar:
        st.markdown(f"### 🏷️ {cat}")
        df_cat = df_filtrado[df_filtrado['Categoría'] == cat].reset_index(drop=True)
        df_mostrar = df_cat.drop(columns=['ID_Producto', 'Categoría', 'Stock_Minimo']).copy()
        
        df_mostrar['Precio Unitario'] = df_mostrar['Precio Unitario'].apply(lambda x: f"S/. {float(x or 0):,.2f}")
        df_mostrar['Precio Minimo'] = df_mostrar['Precio Minimo'].apply(lambda x: f"S/. {float(x or 0):,.2f}")
        df_mostrar['Foto'] = df_mostrar['Foto'].apply(lambda x: x if pd.notna(x) and str(x).startswith("http") else None)
        
        st.dataframe(
            df_mostrar, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Foto": st.column_config.ImageColumn("📸 Imagen")
            }
        )

# ==========================================
# PESTAÑA 2: TIENDAS Y ALMACENES (INTERFAZ ORIGINAL + STOCK AGRUPADO)
# ==========================================
with tab_tiendas:
    st.markdown("### 🏪 Gestión y Visor de Ubicaciones")
    
    def get_encargada(codigo):
        fila = df_config[df_config['Tienda'] == codigo]
        if not fila.empty:
            return fila.iloc[0]['Encargada']
        return ""

    if 'visor_tienda' not in st.session_state:
        st.session_state['visor_tienda'] = None

    # --- 1. BLOQUE VISUAL (LOS 5 RECUADROS) ---
    col_v1, col_v2, col_v3 = st.columns(3)
    
    with col_v1:
        st.info("📍 **Tienda 01**")
        st.caption(f"Encargada: {get_encargada('T1_Gina')}")
        if st.button("📦 Ver Stock Tienda 01", use_container_width=True):
            st.session_state['visor_tienda'] = 'T1_Gina'
            
    with col_v2:
        st.info("📍 **Tienda 02**")
        st.caption(f"Encargada: {get_encargada('T2_Celianny')}")
        if st.button("📦 Ver Stock Tienda 02", use_container_width=True):
            st.session_state['visor_tienda'] = 'T2_Celianny'
            
    with col_v3:
        st.info("📍 **Tienda 03**")
        st.caption(f"Encargada: {get_encargada('T3_San_Jose')}")
        if st.button("📦 Ver Stock Tienda 03", use_container_width=True):
            st.session_state['visor_tienda'] = 'T3_San_Jose'
            
    st.write("---")
    
    col_v4, col_v5 = st.columns(2)
    with col_v4:
        st.warning("📦 **Almacén 01 - Túpac**")
        st.caption("Depósito Central")
        if st.button("📦 Ver Stock Túpac", use_container_width=True):
            st.session_state['visor_tienda'] = 'A1_Tupac'
            
    with col_v5:
        st.warning("📦 **Almacén 02 - Collasuyo**")
        st.caption("Depósito Secundario")
        if st.button("📦 Ver Stock Collasuyo", use_container_width=True):
            st.session_state['visor_tienda'] = 'A2_Collasuyo'

    # --- 2. TABLA DE STOCK CON FILTROS Y CATEGORÍAS ---
    if st.session_state['visor_tienda']:
        st.write("---")
        nombres_amigables = {
            'T1_Gina': 'Tienda 01 (Gina)',
            'T2_Celianny': 'Tienda 02 (Celianny)',
            'T3_San_Jose': 'Tienda 03 (San Jose)',
            'A1_Tupac': 'Almacén 01 - Túpac',
            'A2_Collasuyo': 'Almacén 02 - Collasuyo'
        }
        ubi_seleccionada = st.session_state['visor_tienda']
        st.markdown(f"#### 📊 Inventario Actual en: {nombres_amigables[ubi_seleccionada]}")
        
        if not df_productos.empty and not df_stock.empty:
            df_visor = pd.merge(
                df_productos[['ID_Producto', 'Nombre del Producto', 'Categoría', 'Precio Unitario', 'Precio Minimo']], 
                df_stock[['ID_Producto', ubi_seleccionada]], 
                on='ID_Producto', 
                how='inner'
            )
            df_visor[ubi_seleccionada] = pd.to_numeric(df_visor[ubi_seleccionada], errors='coerce').fillna(0).astype(int)
            df_visor['Precio Unitario'] = df_visor['Precio Unitario'].apply(lambda x: f"S/. {float(x or 0):,.2f}")
            df_visor['Precio Minimo'] = df_visor['Precio Minimo'].apply(lambda x: f"S/. {float(x or 0):,.2f}")
            
            df_visor = df_visor.rename(columns={
                'Nombre del Producto': 'Producto', 
                ubi_seleccionada: 'Stock Actual'
            })
            
            # Filtros para esta tienda
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                buscar_tienda = st.text_input("🔍 Buscar producto en esta ubicación:", key="buscar_tienda")
            with col_b2:
                categorias_lista_tienda = list(df_visor['Categoría'].dropna().unique())
                filtro_cat_tienda = st.selectbox("📂 Filtrar por Categoría:", ["TODAS"] + categorias_lista_tienda, key="filtro_cat_tienda")
                
            df_filtrado_tienda = df_visor.copy()
            if buscar_tienda:
                df_filtrado_tienda = df_filtrado_tienda[df_filtrado_tienda['Producto'].str.contains(buscar_tienda, case=False, na=False)]
            if filtro_cat_tienda != "TODAS":
                df_filtrado_tienda = df_filtrado_tienda[df_filtrado_tienda['Categoría'] == filtro_cat_tienda]
                
            categorias_a_mostrar_tienda = df_filtrado_tienda['Categoría'].dropna().unique()
            
            if len(categorias_a_mostrar_tienda) == 0:
                st.warning("⚠️ No se encontraron productos con esos filtros en esta ubicación.")
                
            for cat in categorias_a_mostrar_tienda:
                st.markdown(f"### 🏷️ {cat}")
                df_cat_tienda = df_filtrado_tienda[df_filtrado_tienda['Categoría'] == cat].reset_index(drop=True)
                df_mostrar_tienda = df_cat_tienda[['Producto', 'Precio Unitario', 'Precio Minimo', 'Stock Actual']]
                st.dataframe(df_mostrar_tienda, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay suficientes datos registrados.")

    # --- 3. FORMULARIO PARA EDITAR NOMBRES ---
    st.write("---")
    with st.expander("✏️ Editar Nombres de Encargadas"):
        with st.form("form_tiendas"):
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                enc_1 = st.text_input("Tienda 01 - Encargada:", value=get_encargada('T1_Gina'))
            with col_f2:
                enc_2 = st.text_input("Tienda 02 - Encargada:", value=get_encargada('T2_Celianny'))
            with col_f3:
                enc_3 = st.text_input("Tienda 03 - Encargada:", value=get_encargada('T3_San_Jose'))
                
            if st.form_submit_button("💾 Guardar Cambios de Personal"):
                nuevo_data = [
                    {'Tienda': 'T1_Gina', 'Nombre_Visible': 'Tienda 01', 'Encargada': enc_1},
                    {'Tienda': 'T2_Celianny', 'Nombre_Visible': 'Tienda 02', 'Encargada': enc_2},
                    {'Tienda': 'T3_San_Jose', 'Nombre_Visible': 'Tienda 03', 'Encargada': enc_3},
                ]
                df_nuevo_config = pd.DataFrame(nuevo_data)
                guardar_configuracion_tiendas(df_nuevo_config)
                st.success("¡Personal actualizado correctamente en la nube!")
                time.sleep(1)
                st.rerun()

# ==========================================
# PESTAÑA 3: MOVIMIENTOS
# ==========================================
with tab_movimientos:
    st.markdown("### 🔄 Registro de Movimientos (Ingresos, Salidas y Traslados)")
    st.write("Registra las operaciones diarias para actualizar el stock automáticamente en la nube.")
    
    ubicaciones_map = {
        'Tienda 01 (Gina)': 'T1_Gina',
        'Tienda 02 (Celianny)': 'T2_Celianny',
        'Tienda 03 (San Jose)': 'T3_San_Jose',
        'Almacén 01 - Túpac': 'A1_Tupac',
        'Almacén 02 - Collasuyo': 'A2_Collasuyo'
    }
    
    tipo_mov = st.radio("Tipo de Movimiento", ["INGRESO (Compra / Entrada)", "SALIDA (Venta)", "TRASLADO (Entre Tiendas/Almacenes)"], horizontal=True)
    
    with st.form("form_movimiento"):
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            fecha_mov = st.date_input("📅 Fecha del Movimiento", value=date.today())
            lista_productos = df_productos['Nombre del Producto'].tolist() if not df_productos.empty else []
            prod_sel = st.selectbox("Seleccionar Producto", lista_productos if lista_productos else ["No hay productos"])
            cantidad = st.number_input("Cantidad", min_value=1, step=1, value=1)
            
        with col_m2:
            opciones_ubi = list(ubicaciones_map.keys())
            origen_sel = ""
            destino_sel = ""
            nota_final = ""
            
            if "INGRESO" in tipo_mov:
                st.info("📥 El producto ingresa desde un proveedor.")
                destino_amable = st.selectbox("Ubicación de Destino (¿A dónde llega?)", opciones_ubi)
                destino_sel = ubicaciones_map[destino_amable]
                
                proveedor = st.text_input("🏢 Proveedor / Procedencia (Opcional)", placeholder="Ej. Distribuidora Lima o Factura F001")
                nota_adic = st.text_input("Nota / Motivo (Opcional)", placeholder="Ej. Compra de reposición")
                
                if proveedor and nota_adic:
                    nota_final = f"Prov: {proveedor} | Nota: {nota_adic}"
                elif proveedor:
                    nota_final = f"Prov: {proveedor}"
                else:
                    nota_final = nota_adic
                    
            elif "SALIDA" in tipo_mov:
                st.warning("📤 El producto sale por una venta a cliente.")
                origen_amable = st.selectbox("Ubicación de Origen (¿De dónde sale?)", opciones_ubi)
                origen_sel = ubicaciones_map[origen_amable]
                nota_final = st.text_input("Nota / Motivo / Boleta (Opcional)", placeholder="Ej. Venta con boleta B001-123")
                
            else:
                st.success("🔄 Traslado interno entre almacenes o tiendas.")
                origen_amable = st.selectbox("Ubicación de Origen (Sale de...)", opciones_ubi)
                destino_amable = st.selectbox("Ubicación de Destino (Llega a...)", opciones_ubi)
                
                origen_sel = ubicaciones_map[origen_amable]
                destino_sel = ubicaciones_map[destino_amable]
                nota_final = st.text_input("Nota / Motivo (Opcional)", placeholder="Ej. Reubicación por espacio")
                
        if st.form_submit_button("🚀 Registrar Movimiento"):
            if not lista_productos:
                st.error("Primero debes registrar al menos un producto en la pestaña Productos.")
            elif "TRASLADO" in tipo_mov and origen_sel == destino_sel:
                st.error("⚠️ Error: La ubicación de origen y destino no pueden ser la misma.")
            else:
                tipo_limpio = "INGRESO" if "INGRESO" in tipo_mov else ("SALIDA" if "SALIDA" in tipo_mov else "TRASLADO")
                exito, mensaje = registrar_movimiento(tipo_limpio, prod_sel, cantidad, origen_sel, destino_sel, nota_final, fecha_mov)
                if exito:
                    st.success(mensaje)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(mensaje)

    st.write("---")
    
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.markdown("### 📜 Historial Organizado por Semanas")
    with col_h2:
        if st.button("⚠️ Anular Último Movimiento", type="secondary"):
            exito, mensaje = anular_ultimo_movimiento()
            if exito:
                st.success(mensaje)
                time.sleep(1)
                st.rerun()
            else:
                st.warning(mensaje)

    if not df_movimientos.empty:
        df_movimientos['Fecha_dt'] = pd.to_datetime(df_movimientos['Fecha'], errors='coerce')
        
        def obtener_rango_semana(fecha):
            if pd.isna(fecha):
                return "Sin Fecha"
            inicio = fecha - timedelta(days=fecha.weekday())
            fin = inicio + timedelta(days=6)
            return f"Semana del {inicio.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}"

        df_movimientos['Semana_Grupo'] = df_movimientos['Fecha_dt'].apply(obtener_rango_semana)
        df_movimientos = df_movimientos.sort_values(by='Fecha_dt', ascending=False)
        semanas_unicas = df_movimientos['Semana_Grupo'].dropna().unique()
        
        for idx, semana in enumerate(semanas_unicas):
            df_semana = df_movimientos[df_movimientos['Semana_Grupo'] == semana].drop(columns=['Fecha_dt', 'Semana_Grupo'])
            abierto_por_defecto = (idx == 0)
            
            with st.expander(f"📅 {semana} ({len(df_semana)} movimientos)", expanded=abierto_por_defecto):
                st.dataframe(df_semana, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay movimientos registrados.")

# ==========================================
# PESTAÑA 4: INVENTARIO Y STOCK
# ==========================================
with tab_inventario:
    st.markdown("### 📊 Inventario Consolidado y Estado de Stock")
    st.write("Vista general del stock por ubicación. Las alertas rojas indican stock crítico (≤ 2) y las verdes indican stock saludable (≥ 3).")
    
    st.write("---")
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        buscar_inv = st.text_input("🔍 Buscar por nombre (ej. Balanza):", key="buscar_inv")
    with col_b2:
        categorias_lista_inv = list(df_productos['Categoría'].dropna().unique()) if not df_productos.empty else []
        filtro_cat_inv = st.selectbox("📂 Filtrar por Categoría:", ["TODAS"] + categorias_lista_inv, key="filtro_cat_inv")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        solo_criticos = st.checkbox("🚨 Ver solo stock crítico (Rojos 🔴)")
    with col_f2:
        solo_saludables = st.checkbox("✅ Ver solo stock OK (Verdes 🟢)")
    st.write("---")
    
    if not df_productos.empty and not df_stock.empty:
        df_completo = pd.merge(df_productos[['ID_Producto', 'Nombre del Producto', 'Categoría']], df_stock, on=['ID_Producto', 'Nombre del Producto'], how='inner')
        
        cols_ubicaciones = ['T1_Gina', 'T2_Celianny', 'T3_San_Jose', 'A1_Tupac', 'A2_Collasuyo']
        
        for col in cols_ubicaciones:
            if col in df_completo.columns:
                df_completo[col] = pd.to_numeric(df_completo[col], errors='coerce').fillna(0).astype(int)
        
        df_completo['Stock Total'] = df_completo[cols_ubicaciones].sum(axis=1)
        
        def obtener_semaforo(stock):
            if stock <= 2:
                return "🔴 Crítico (≤2)"
            else:
                return "🟢 Stock OK"
                
        df_completo['Estado'] = df_completo['Stock Total'].apply(obtener_semaforo)
        
        if buscar_inv:
            df_completo = df_completo[df_completo['Nombre del Producto'].str.contains(buscar_inv, case=False, na=False)]
        
        if filtro_cat_inv != "TODAS":
            df_completo = df_completo[df_completo['Categoría'] == filtro_cat_inv]
        
        if solo_criticos and not solo_saludables:
            df_completo = df_completo[df_completo['Stock Total'] <= 2]
        elif solo_saludables and not solo_criticos:
            df_completo = df_completo[df_completo['Stock Total'] >= 3]
        elif solo_criticos and solo_saludables:
            pass
        
        renombres_columnas = {
            'Nombre del Producto': 'Producto',
            'T1_Gina': 'Tienda 01 (Gina)',
            'T2_Celianny': 'Tienda 02 (Celianny)',
            'T3_San_Jose': 'Tienda 03 (San Jose)',
            'A1_Tupac': 'Alm. Túpac',
            'A2_Collasuyo': 'Alm. Collasuyo'
        }
        df_completo = df_completo.rename(columns=renombres_columnas)
        
        categorias_stock = df_completo['Categoría'].dropna().unique()
        
        if len(categorias_stock) == 0:
            st.warning("⚠️ No hay productos que cumplan con los filtros seleccionados.")
        
        for cat in categorias_stock:
            st.markdown(f"### 🏷️ {cat}")
            df_cat_stock = df_completo[df_completo['Categoría'] == cat].reset_index(drop=True)
            
            cols_mostrar = ['Producto', 'Estado', 'Stock Total', 'Tienda 01 (Gina)', 'Tienda 02 (Celianny)', 'Tienda 03 (San Jose)', 'Alm. Túpac', 'Alm. Collasuyo']
            df_final_mostrar = df_cat_stock[[c for c in cols_mostrar if c in df_cat_stock.columns]]
            
            st.dataframe(df_final_mostrar, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay suficiente información para consolidar el inventario.")
