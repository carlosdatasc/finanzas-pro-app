import flet as ft
import psycopg2
import os

# ==========================================
# 1. CONFIGURACIÓN DE BASE DE DATOS (NUBE)
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")

def obtener_conexion():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def inicializar_db():
    with obtener_conexion() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, nombre TEXT UNIQUE, pin TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS fuentes (
                id SERIAL PRIMARY KEY, usuario_id INTEGER, nombre TEXT, tipo TEXT, id_padre INTEGER, limite_credito REAL DEFAULT 0, activo BOOLEAN DEFAULT TRUE)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS categorias_usuario (
                id SERIAL PRIMARY KEY, usuario_id INTEGER, nombre TEXT)''')
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

    # --- VISTA DE CUENTA ---
    def cargar_vista_cuenta(fuente):
        page.clean()
        f_id, _, nombre, tipo, _, limite, _ = fuente
        area_dinamica = ft.Container()

        def obtener_historial_completo():
            movs = ejecutar_query("SELECT fecha, monto, tipo, categoria, subcategoria, concepto FROM transacciones WHERE id_fuente=%s", (f_id,))
            trans_out = ejecutar_query("SELECT t.fecha, t.monto, 'Gasto', 'Transferencia', '', 'A: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_destino = f.id WHERE t.id_origen=%s", (f_id,))
            trans_in = ejecutar_query("SELECT t.fecha, t.monto, 'Ingreso', 'Transferencia', '', 'De: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_origen = f.id WHERE t.id_destino=%s", (f_id,))
            historial = movs + trans_out + trans_in
            historial.sort(key=lambda x: x[0], reverse=True)
            return historial

        # ==========================================
        # PESTAÑA 1: DETALLES (Diseño Original Restaurado)
        # ==========================================
        def renderizar_detalles(e):
            saldo_o_deuda = calcular_saldo(f_id, tipo)
            historial_completo = obtener_historial_completo()
            
            texto_ultima = "Sin movimientos recientes"
            if historial_completo:
                ultima = historial_completo[0]
                signo = "+" if ultima[2] == "Ingreso" else "-"
                sub_txt = f" > {ultima[4]}" if ultima[4] else ""
                texto_ultima = f"{ultima[3]}{sub_txt} - {ultima[5]} ({signo}${ultima[1]:.2f})"

            if tipo == "Crédito":
                disponible = limite - saldo_o_deuda
                tarjeta_info = ft.Container(padding=25, border_radius=25, bgcolor="#1E3A8A", content=ft.Column([
                    ft.Text("Estado de Crédito", color=ft.Colors.BLUE_200, size=14),
                    ft.Divider(color=ft.Colors.BLUE_400),
                    ft.Text("Saldo Disponible", size=14, color=ft.Colors.GREEN_200),
                    ft.Text(f"${disponible:,.2f}", size=32, weight=ft.FontWeight.BOLD),
                    ft.Text("Saldo Gastado", size=14, color=ft.Colors.RED_200),
                    ft.Text(f"${saldo_o_deuda:,.2f}", size=24, weight=ft.FontWeight.W_500),
                ]))
            else: 
                color_bg = "#065F46" if tipo == "Débito" else "#78350F"
                tarjeta_info = ft.Container(padding=25, border_radius=25, bgcolor=color_bg, content=ft.Column([
                    ft.Text("Estado de Cuenta", color=ft.Colors.WHITE70, size=14),
                    ft.Divider(color=ft.Colors.WHITE30),
                    ft.Text("Saldo Disponible", size=14, color=ft.Colors.WHITE70),
                    ft.Text(f"${saldo_o_deuda:,.2f}", size=35, weight=ft.FontWeight.BOLD),
                    ft.Container(padding=10, border_radius=15, bgcolor=ft.Colors.BLACK26, content=ft.Row([
                        ft.Icon(ft.Icons.RECEIPT_LONG, size=16, color=ft.Colors.WHITE70),
                        ft.Text(f"Último: {texto_ultima}", size=12, color=ft.Colors.WHITE)
                    ]))
                ]))

            contenido_extra = ft.Column(spacing=15)
            
            if historial_completo:
                contenido_extra.controls.append(ft.Text("Últimos Movimientos", weight=ft.FontWeight.BOLD))
                for t in historial_completo[:5]: 
                    c = ft.Colors.RED_400 if t[2] == "Gasto" else ft.Colors.GREEN_400
                    sub_txt = f" > {t[4]}" if t[4] else ""
                    # Adaptación de Postgres a tu formato visual
                    fecha_str = str(t[0])[:16] 
                    contenido_extra.controls.append(ft.Container(padding=15, border_radius=20, bgcolor="#1E2029", content=ft.Row([
                        ft.Column([
                            ft.Text(f"{t[3]}{sub_txt}", size=14, weight=ft.FontWeight.BOLD), 
                            ft.Text(f"{fecha_str} | {t[5]}", size=12, color=ft.Colors.GREY_400) 
                        ], expand=True, spacing=2), 
                        ft.Text(f"${t[1]:.2f}", color=c, weight=ft.FontWeight.BOLD)
                    ])))

            if tipo == "Débito":
                apartados = ejecutar_query("SELECT * FROM fuentes WHERE id_padre = %s AND activo = TRUE", (f_id,))
                if apartados:
                    contenido_extra.controls.append(ft.Text("Tus Apartados", weight=ft.FontWeight.BOLD))
                    for ap in apartados:
                        saldo_ap = calcular_saldo(ap[0], "Débito")
                        contenido_extra.controls.append(ft.Container(padding=15, border_radius=25, bgcolor="#1E2029", ink=True, on_click=lambda e, a=ap: cargar_vista_cuenta(a), content=ft.Row([
                            ft.Icon(ft.Icons.SAVINGS, color=ft.Colors.BLUE_300), ft.Text(ap[2], expand=True), ft.Text(f"${saldo_ap:,.2f}", weight=ft.FontWeight.BOLD)
                        ])))

            area_dinamica.content = ft.Column([tarjeta_info, ft.Divider(color=ft.Colors.TRANSPARENT), contenido_extra])
            page.update()

        # ==========================================
        # PESTAÑA 2: MOVIMIENTOS
        # ==========================================
        def renderizar_movimientos(e):
            monto_input = ft.TextField(label="Monto ($)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=25, expand=True)
            tipo_mov_drop = ft.Dropdown(options=[ft.dropdown.Option("Gasto"), ft.dropdown.Option("Ingreso")], value="Gasto", width=120, border_radius=25)
            
            categorias_custom = ejecutar_query("SELECT nombre FROM categorias_usuario WHERE usuario_id=%s", (id_usr,))
            cat_drop = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(c[0]) for c in categorias_custom], border_radius=25, expand=True)
            
            def abrir_dialogo_categoria(e):
                input_nueva_cat = ft.TextField(label="Nombre de la nueva categoría", border_radius=15)
                def guardar_nueva_cat(e_interno):
                    if input_nueva_cat.value:
                        ejecutar_query("INSERT INTO categorias_usuario (usuario_id, nombre) VALUES (%s, %s)", (id_usr, input_nueva_cat.value))
                        dlg.open = False
                        mostrar_alerta("Categoría creada")
                        renderizar_movimientos(None) 
                
                dlg = ft.AlertDialog(title=ft.Text("Nueva Categoría"), content=input_nueva_cat, actions=[ft.TextButton("Guardar", on_click=guardar_nueva_cat)])
                page.overlay.append(dlg)
                dlg.open = True
                page.update()

            subcategoria_input = ft.TextField(label="Sub-categoría (Opcional)", border_radius=25)
            concepto_input = ft.TextField(label="Concepto", border_radius=25)

            def btn_guardar(e):
                if not monto_input.value or not cat_drop.value or not concepto_input.value:
                    mostrar_alerta("Monto, Categoría y Concepto son obligatorios", ft.Colors.RED_700)
                    return
                try:
                    ejecutar_query("INSERT INTO transacciones (monto, id_fuente, tipo, categoria, subcategoria, concepto) VALUES (%s, %s, %s, %s, %s, %s)",
                                   (float(monto_input.value), f_id, tipo_mov_drop.value, cat_drop.value, subcategoria_input.value, concepto_input.value))
                    mostrar_alerta("Movimiento guardado")
                    renderizar_detalles(None) 
                except ValueError:
                    mostrar_alerta("El monto debe ser numérico", ft.Colors.RED_700)

            formulario = ft.Container(padding=25, border_radius=25, bgcolor="#1E2029", content=ft.Column([
                ft.Text("Registrar Nuevo Movimiento", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([tipo_mov_drop, monto_input]),
                ft.Row([cat_drop, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE_400, on_click=abrir_dialogo_categoria)]),
                subcategoria_input, concepto_input,
                ft.ElevatedButton("Guardar", on_click=btn_guardar, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25)))
            ], spacing=15))
            area_dinamica.content = formulario
            page.update()

        # ==========================================
        # PESTAÑA 3: TRANSFERENCIAS
        # ==========================================
        def renderizar_transferencias(e):
            otras_cuentas = ejecutar_query("SELECT id, nombre, tipo FROM fuentes WHERE usuario_id=%s AND id != %s AND activo=TRUE", (id_usr, f_id))
            
            if not otras_cuentas:
                area_dinamica.content = ft.Container(padding=20, content=ft.Text("No tienes otras cuentas registradas para recibir dinero.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER))
                page.update(); return

            monto_input = ft.TextField(label="Monto a Traspasar ($)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=25)
            destino_drop = ft.Dropdown(label="Selecciona la cuenta destino", border_radius=25, options=[ft.dropdown.Option(key=str(c[0]), text=f"{c[1]} ({c[2]})") for c in otras_cuentas])

            def btn_enviar(e):
                if not monto_input.value or not destino_drop.value:
                    mostrar_alerta("Completa los campos", ft.Colors.RED_700); return
                try:
                    monto = float(monto_input.value)
                    if tipo in ["Débito", "Efectivo"] and monto > calcular_saldo(f_id, tipo):
                        mostrar_alerta("Fondos insuficientes", ft.Colors.RED_700); return
                    ejecutar_query("INSERT INTO transferencias (monto, id_origen, id_destino) VALUES (%s, %s, %s)", (monto, f_id, int(destino_drop.value)))
                    mostrar_alerta("¡Transferencia enviada con éxito!")
                    renderizar_detalles(None)
                except ValueError:
                    mostrar_alerta("El monto debe ser numérico", ft.Colors.RED_700)

            formulario = ft.Container(padding=25, border_radius=25, bgcolor="#1E2029", content=ft.Column([
                ft.Text("Traspasar Dinero", size=18, weight=ft.FontWeight.BOLD),
                ft.Text("Mueve saldo entre tus propias cuentas sin registrarlo como un gasto real.", color=ft.Colors.GREY_400, size=12),
                ft.Divider(color=ft.Colors.TRANSPARENT),
                monto_input, destino_drop,
                ft.ElevatedButton("Enviar Dinero", on_click=btn_enviar, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25)))
            ]))
            area_dinamica.content = formulario
            page.update()

        botones_menu = ft.Row([
            ft.ElevatedButton("Detalles", icon=ft.Icons.INFO_OUTLINE, expand=True, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_detalles),
            ft.ElevatedButton("Movimientos", icon=ft.Icons.ADD_CARD, expand=True, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_movimientos),
            ft.ElevatedButton("Traspasar", icon=ft.Icons.SWAP_HORIZ, expand=True, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_transferencias),
        ], spacing=5)

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: cargar_dashboard()), ft.Text(nombre, size=24, weight=ft.FontWeight.BOLD)]), 
            botones_menu, ft.Divider(height=10, color=ft.Colors.TRANSPARENT), area_dinamica 
        ], scroll=ft.ScrollMode.AUTO))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, -1), expand=True))
        renderizar_detalles(None)

    # --- DASHBOARD ---
    def cargar_dashboard():
        page.clean()
        input_nombre = ft.TextField(label="Nombre (Ej. BBVA)", height=50, expand=True, border_radius=25)
        input_tipo = ft.Dropdown(options=[ft.dropdown.Option("Débito"), ft.dropdown.Option("Crédito"), ft.dropdown.Option("Efectivo")], width=120, height=50, border_radius=25)
        
        def btn_guardar_cuenta(e):
            if input_nombre.value and input_tipo.value:
                ejecutar_query("INSERT INTO fuentes (usuario_id, nombre, tipo, limite_credito) VALUES (%s, %s, %s, %s)", (id_usr, input_nombre.value, input_tipo.value, 0))
                cargar_dashboard() 

        fuentes = ejecutar_query("SELECT * FROM fuentes WHERE usuario_id=%s AND activo=TRUE", (id_usr,))
        lista_cuentas = ft.Column(spacing=15)
        
        if not fuentes: 
            lista_cuentas.controls.append(ft.Text("No tienes cuentas. Crea una abajo.", color=ft.Colors.GREY_500))
        else:
            for f in fuentes:
                saldo = calcular_saldo(f[0], f[3])
                texto_saldo = f"Deuda: ${saldo:,.2f}" if f[3] == "Crédito" else f"Saldo: ${saldo:,.2f}"
                color_icono = ft.Colors.BLUE_400 if f[3] == "Crédito" else (ft.Colors.GREEN_400 if f[3] == "Débito" else ft.Colors.ORANGE_400)
                lista_cuentas.controls.append(
                    ft.Container(padding=20, border_radius=25, bgcolor="#1E2029", ink=True, on_click=lambda e, f_comp=f: cargar_vista_cuenta(f_comp), content=ft.Row([
                        ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=color_icono, size=30),
                        ft.Column([ft.Text(f[2], size=18, weight=ft.FontWeight.BOLD), ft.Text(texto_saldo, size=12, color=ft.Colors.GREY_400)], spacing=2),
                        ft.Container(expand=True), ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.GREY_500)
                    ]))
                )

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([ft.Text(f"Hola, {nom_usr}", size=24, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.LOGOUT, on_click=lambda _: cargar_login())], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(color=ft.Colors.GREY_800), ft.Text("Mis Cuentas", size=18, color=ft.Colors.GREY_300), lista_cuentas,
            ft.Divider(color=ft.Colors.GREY_800, height=30), ft.Text("Añadir Nueva Cuenta", size=18, color=ft.Colors.GREY_300),
            ft.Row([input_nombre, input_tipo]),
            ft.ElevatedButton("Guardar Cuenta", on_click=btn_guardar_cuenta, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25))),
        ], scroll=ft.ScrollMode.AUTO))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, -1), expand=True))
        page.update()

    # --- LOGIN ---
    def cargar_login():
        page.clean()
        usr_input = ft.TextField(label="Usuario", width=300, border_radius=25)
        pin_input = ft.TextField(label="PIN", password=True, can_reveal_password=True, width=300, border_radius=25)
        
        def btn_entrar(e):
            nonlocal id_usr, nom_usr
            if not usr_input.value or not pin_input.value: 
                mostrar_alerta("Llena ambos campos", ft.Colors.RED_700)
                return
                
            res = ejecutar_query("SELECT id FROM usuarios WHERE nombre=%s AND pin=%s", (usr_input.value, pin_input.value))
            if res: 
                id_usr = res[0][0]
                nom_usr = usr_input.value
                cargar_dashboard()
            else: 
                mostrar_alerta("Datos incorrectos o usuario no existe", ft.Colors.RED_700)
            
        def btn_registrar(e):
            if usr_input.value and pin_input.value:
                try: 
                    ejecutar_query("INSERT INTO usuarios (nombre, pin) VALUES (%s, %s)", (usr_input.value, pin_input.value))
                    mostrar_alerta("Cuenta creada exitosamente. ¡Inicia sesión!", ft.Colors.GREEN_700)
                except Exception: 
                    mostrar_alerta("Ese nombre de usuario ya está en uso", ft.Colors.RED_700)
            else: 
                mostrar_alerta("Escribe un usuario y PIN para crear la cuenta", ft.Colors.RED_700)

        panel = ft.Container(width=400, padding=40, border_radius=25, bgcolor="#1E2029", content=ft.Column([
            ft.Icon(ft.Icons.LOCK_OUTLINE, size=60, color=ft.Colors.BLUE_400), 
            ft.Text("Bienvenido", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Ingresa tus datos o crea una cuenta nueva", size=14, color=ft.Colors.GREY_400),
            ft.Divider(color=ft.Colors.TRANSPARENT, height=10),
            usr_input, pin_input, 
            ft.ElevatedButton("Entrar", on_click=btn_entrar, width=300, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25))),
            ft.TextButton("Crear Cuenta Nueva", on_click=btn_registrar)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, 0), expand=True))
        page.update()

    inicializar_db()
    cargar_login()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port)
