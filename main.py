import flet as ft
import psycopg2
import os

# ==========================================
# 1. CONFIGURACIÓN DE BASE DE DATOS (NUBE)
# ==========================================
# Render inyectará esta variable automáticamente
DATABASE_URL = os.environ.get("DATABASE_URL")

def obtener_conexion():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def inicializar_db():
    with obtener_conexion() as conn:
        with conn.cursor() as cursor:
            # Tablas optimizadas para PostgreSQL
            cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT UNIQUE, pin TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS fuentes (
                id SERIAL PRIMARY KEY, usuario_id INTEGER, nombre TEXT, tipo TEXT, id_padre INTEGER, limite_credito REAL DEFAULT 0, activo BOOLEAN DEFAULT TRUE)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS categorias_usuario (
                id SERIAL PRIMARY KEY, usuario_id INTEGER, nombre TEXT)''')
            
            # Fecha como TIMESTAMP automático para Ciencia de Datos
            cursor.execute('''CREATE TABLE IF NOT EXISTS transacciones (
                id SERIAL PRIMARY KEY, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, monto REAL, id_fuente INTEGER, tipo TEXT, categoria TEXT, subcategoria TEXT, concepto TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS transferencias (
                id SERIAL PRIMARY KEY, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, monto REAL, id_origen INTEGER, id_destino INTEGER)''')
        conn.commit()

def ejecutar_query(query, params=()):
    with obtener_conexion() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if query.strip().upper().startswith("SELECT"):
                return cursor.fetchall()
        conn.commit()

def calcular_saldo(fuente_id, tipo):
    # Uso de COALESCE para evitar errores si no hay registros aún
    ingresos = ejecutar_query("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE id_fuente=%s AND tipo='Ingreso'", (fuente_id,))[0][0]
    gastos = ejecutar_query("SELECT COALESCE(SUM(monto), 0) FROM transacciones WHERE id_fuente=%s AND tipo='Gasto'", (fuente_id,))[0][0]
    t_in = ejecutar_query("SELECT COALESCE(SUM(monto), 0) FROM transferencias WHERE id_destino=%s", (fuente_id,))[0][0]
    t_out = ejecutar_query("SELECT COALESCE(SUM(monto), 0) FROM transferencias WHERE id_origen=%s", (fuente_id,))[0][0]
    
    if tipo == "Crédito":
        deuda = gastos - ingresos + t_out - t_in
        return deuda if deuda > 0 else 0
    else:
        return (ingresos + t_in) - (gastos + t_out)

# ==========================================
# 2. INTERFAZ GRÁFICA (APP)
# ==========================================
def main(page: ft.Page):
    page.title = "Finanzas Pro Nube"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0F111A" 
    
    id_usr = None
    nom_usr = None

    def mostrar_alerta(mensaje, color=ft.Colors.GREEN_700):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    # --- FLUJO 3: VISTA DE CUENTA ---
    def cargar_vista_cuenta(fuente):
        page.clean()
        f_id, _, nombre, tipo, _, limite, _ = fuente
        area_dinamica = ft.Container()

        def renderizar_detalles(e):
            saldo = calcular_saldo(f_id, tipo)
            # Obtenemos los últimos 5 movimientos ordenados por fecha
            historial = ejecutar_query("SELECT fecha, monto, tipo, categoria, subcategoria, concepto FROM transacciones WHERE id_fuente=%s ORDER BY fecha DESC LIMIT 5", (f_id,))
            
            color_bg = "#1E3A8A" if tipo == "Crédito" else ("#065F46" if tipo == "Débito" else "#78350F")
            tarjeta = ft.Container(padding=25, border_radius=25, bgcolor=color_bg, content=ft.Column([
                ft.Text(f"Saldo {'Disponible' if tipo != 'Crédito' else 'Gastado'}", size=14, color=ft.Colors.WHITE70),
                ft.Text(f"${abs(saldo):,.2f}", size=35, weight=ft.FontWeight.BOLD),
            ]))
            
            lista_movimientos = ft.Column([ft.Text("Últimos Movimientos", weight=ft.FontWeight.BOLD)], spacing=10)
            if not historial:
                lista_movimientos.controls.append(ft.Text("Aún no hay movimientos.", color=ft.Colors.GREY_500))
            else:
                for t in historial:
                    c = ft.Colors.RED_400 if t[2] == "Gasto" else ft.Colors.GREEN_400
                    sub = f" > {t[4]}" if t[4] else ""
                    # Formateamos el TIMESTAMP para que se vea bonito (Día/Mes Hora:Minuto)
                    fecha_str = t[0].strftime("%d/%m %H:%M")
                    lista_movimientos.controls.append(ft.Container(padding=15, border_radius=20, bgcolor="#1E2029", content=ft.Row([
                        ft.Column([
                            ft.Text(f"{t[3]}{sub}", weight=ft.FontWeight.BOLD), 
                            ft.Text(f"{fecha_str} | {t[5]}", size=12, color=ft.Colors.GREY_400)
                        ], expand=True),
                        ft.Text(f"${t[1]:.2f}", color=c, weight=ft.FontWeight.BOLD)
                    ])))
            
            area_dinamica.content = ft.Column([tarjeta, ft.Divider(height=20, color=ft.Colors.TRANSPARENT), lista_movimientos])
            page.update()

        def renderizar_movimientos(e):
            monto_input = ft.TextField(label="Monto ($)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=25, expand=True)
            tipo_mov_drop = ft.Dropdown(options=[ft.dropdown.Option("Gasto"), ft.dropdown.Option("Ingreso")], value="Gasto", width=120, border_radius=25)
            
            # Cargar SOLO categorías del usuario
            categorias_custom = ejecutar_query("SELECT nombre FROM categorias_usuario WHERE usuario_id=%s", (id_usr,))
            cat_drop = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(c[0]) for c in categorias_custom], border_radius=25, expand=True)
            
            def abrir_dialogo_categoria(e):
                input_nueva_cat = ft.TextField(label="Nombre de la nueva categoría", border_radius=15)
                def guardar_nueva_cat(e):
                    if input_nueva_cat.value:
