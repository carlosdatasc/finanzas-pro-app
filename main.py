import flet as ft
import sqlite3
from datetime import datetime

DB_NAME = "finanzas_v3_pro.db"

# ==========================================
# 1. BASE DE DATOS E INFRAESTRUCTURA
# ==========================================
def inicializar_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, pin TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS fuentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, nombre TEXT, tipo TEXT, id_padre INTEGER, limite_credito REAL DEFAULT 0, activo BOOLEAN DEFAULT 1, 
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id), FOREIGN KEY (id_padre) REFERENCES fuentes(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, monto REAL, id_fuente INTEGER, tipo TEXT, categoria TEXT, concepto TEXT, 
            FOREIGN KEY (id_fuente) REFERENCES fuentes(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS transferencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, monto REAL, id_origen INTEGER, id_destino INTEGER, 
            FOREIGN KEY (id_origen) REFERENCES fuentes(id), FOREIGN KEY (id_destino) REFERENCES fuentes(id))''')
        conn.commit()

def ejecutar_query(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor

def calcular_saldo(fuente_id, tipo):
    ingresos = ejecutar_query("SELECT SUM(monto) FROM transacciones WHERE id_fuente=? AND tipo='Ingreso'", (fuente_id,)).fetchone()[0] or 0
    gastos = ejecutar_query("SELECT SUM(monto) FROM transacciones WHERE id_fuente=? AND tipo='Gasto'", (fuente_id,)).fetchone()[0] or 0
    trans_in = ejecutar_query("SELECT SUM(monto) FROM transferencias WHERE id_destino=?", (fuente_id,)).fetchone()[0] or 0
    trans_out = ejecutar_query("SELECT SUM(monto) FROM transferencias WHERE id_origen=?", (fuente_id,)).fetchone()[0] or 0
    
    if tipo == "Crédito":
        deuda = gastos - ingresos + trans_out - trans_in
        return deuda if deuda > 0 else 0
    else:
        return (ingresos + trans_in) - (gastos + trans_out)

def eliminar_fuente(fuente_id):
    ejecutar_query("UPDATE fuentes SET activo = 0 WHERE id = ?", (fuente_id,))
    ejecutar_query("UPDATE fuentes SET activo = 0 WHERE id_padre = ?", (fuente_id,))

# ==========================================
# 2. INTERFAZ GRÁFICA MAESTRO-DETALLE
# ==========================================
def main(page: ft.Page):
    page.title = "Finanzas Pro V3"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0F111A" 
    
    id_usr = None
    nom_usr = None

    def mostrar_alerta(mensaje, color=ft.Colors.GREEN_700):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    # --- FLUJO 3: VISTA DE CUENTA (PESTAÑAS DINÁMICAS) ---
    def cargar_vista_cuenta(fuente):
        page.clean()
        f_id, _, nombre, tipo, _, limite, _ = fuente
        area_dinamica = ft.Container()

        def confirmar_eliminar(e):
            dlg = ft.AlertDialog(title=ft.Text("¿Eliminar Cuenta?"), content=ft.Text(f"Se ocultará '{nombre}' de tu lista. Los registros pasados se conservan por seguridad."))
            def btn_si_eliminar(e2):
                dlg.open = False; page.update(); eliminar_fuente(f_id); mostrar_alerta(f"{nombre} eliminada", ft.Colors.RED_700); cargar_dashboard()
            def btn_cancelar(e2): dlg.open = False; page.update()
            dlg.actions = [ft.TextButton("Cancelar", on_click=btn_cancelar), ft.TextButton("Eliminar", on_click=btn_si_eliminar, style=ft.ButtonStyle(color=ft.Colors.RED))]
            page.overlay.append(dlg); dlg.open = True; page.update()

        # Algoritmo para obtener historial combinando Compras y Transferencias
        def obtener_historial_completo():
            movs = ejecutar_query("SELECT fecha, monto, tipo, categoria, concepto FROM transacciones WHERE id_fuente = ?", (f_id,)).fetchall()
            trans_out = ejecutar_query("SELECT t.fecha, t.monto, 'Gasto', 'Transferencia', 'A: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_destino = f.id WHERE t.id_origen = ?", (f_id,)).fetchall()
            trans_in = ejecutar_query("SELECT t.fecha, t.monto, 'Ingreso', 'Transferencia', 'De: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_origen = f.id WHERE t.id_destino = ?", (f_id,)).fetchall()
            
            historial = movs + trans_out + trans_in
            historial.sort(key=lambda x: x[0], reverse=True) # Ordena del más reciente al más antiguo
            return historial

        # ==========================================
        # PESTAÑA 1: DETALLES (Saldos + Historial)
        # ==========================================
        def renderizar_detalles(e):
            saldo_o_deuda = calcular_saldo(f_id, tipo)
            historial_completo = obtener_historial_completo()
            
            texto_ultima = "Sin movimientos recientes"
            if historial_completo:
                ultima = historial_completo[0]
                signo = "+" if ultima[2] == "Ingreso" else "-"
                texto_ultima = f"{ultima[3]} - {ultima[4]} ({signo}${ultima[1]:.2f})"

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
                for t in historial_completo[:5]: # Solo mostramos los 5 más recientes
                    c = ft.Colors.RED_400 if t[2] == "Gasto" else ft.Colors.GREEN_400
                    contenido_extra.controls.append(ft.Container(padding=15, border_radius=20, bgcolor="#1E2029", content=ft.Row([
                        ft.Column([
                            ft.Text(f"{t[3]}", size=14, weight=ft.FontWeight.BOLD), 
                            ft.Text(f"{t[0][:16]} | {t[4]}", size=12, color=ft.Colors.GREY_400) 
                        ], expand=True, spacing=2), 
                        ft.Text(f"${t[1]:.2f}", color=c, weight=ft.FontWeight.BOLD)
                    ])))

            if tipo == "Débito":
                apartados = ejecutar_query("SELECT * FROM fuentes WHERE id_padre = ? AND activo = 1", (f_id,)).fetchall()
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
            categorias_lista = ["Comida", "Transporte", "Vivienda", "Ocio", "Salud", "Educación", "Compras", "Servicios", "Ingresos", "Otros"]
            categoria_drop = ft.Dropdown(label="Categoría", options=[ft.dropdown.Option(c) for c in categorias_lista], border_radius=25, expand=True)
            concepto_input = ft.TextField(label="Concepto (Opcional)", expand=True, border_radius=25)

            def btn_guardar(e):
                if not monto_input.value or not categoria_drop.value:
                    mostrar_alerta("Ingresa monto y categoría", ft.Colors.RED_700); return
                try:
                    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ejecutar_query("INSERT INTO transacciones (fecha, monto, id_fuente, tipo, categoria, concepto) VALUES (?, ?, ?, ?, ?, ?)",
                                   (fecha, float(monto_input.value), f_id, tipo_mov_drop.value, categoria_drop.value, concepto_input.value))
                    mostrar_alerta("Movimiento guardado")
                    renderizar_detalles(None) 
                except ValueError:
                    mostrar_alerta("El monto debe ser numérico", ft.Colors.RED_700)

            formulario = ft.Container(padding=25, border_radius=25, bgcolor="#1E2029", content=ft.Column([
                ft.Text("Registrar Nuevo Movimiento", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([tipo_mov_drop, monto_input]),
                ft.Row([categoria_drop]), ft.Row([concepto_input]),
                ft.ElevatedButton("Guardar", on_click=btn_guardar, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25)))
            ]))
            area_dinamica.content = formulario
            page.update()

        # ==========================================
        # PESTAÑA 3: TRANSFERENCIAS (NUEVA)
        # ==========================================
        def renderizar_transferencias(e):
            # Obtiene todas las cuentas y apartados del usuario excepto en la que estamos parados
            otras_cuentas = ejecutar_query("SELECT id, nombre, tipo FROM fuentes WHERE usuario_id = ? AND id != ? AND activo = 1", (id_usr, f_id)).fetchall()
            
            if not otras_cuentas:
                area_dinamica.content = ft.Container(padding=20, content=ft.Text("No tienes otras cuentas registradas para recibir dinero.", color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER))
                page.update()
                return

            monto_input = ft.TextField(label="Monto a Traspasar ($)", keyboard_type=ft.KeyboardType.NUMBER, border_radius=25)
            destino_drop = ft.Dropdown(label="Selecciona la cuenta destino", border_radius=25, options=[
                ft.dropdown.Option(key=str(c[0]), text=f"{c[1]} ({c[2]})") for c in otras_cuentas
            ])

            def btn_enviar(e):
                if not monto_input.value or not destino_drop.value:
                    mostrar_alerta("Completa los campos", ft.Colors.RED_700); return
                try:
                    monto = float(monto_input.value)
                    # Validación opcional: No dejar que transfieran más de lo que tienen (si es débito/efectivo)
                    if tipo in ["Débito", "Efectivo"] and monto > calcular_saldo(f_id, tipo):
                        mostrar_alerta("Fondos insuficientes", ft.Colors.RED_700); return

                    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ejecutar_query("INSERT INTO transferencias (fecha, monto, id_origen, id_destino) VALUES (?, ?, ?, ?)",
                                   (fecha, monto, f_id, int(destino_drop.value)))
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

        # Botones Principales actualizados (Añadido 'Traspasar')
        botones_menu = ft.Row([
            ft.ElevatedButton("Detalles", icon=ft.Icons.INFO_OUTLINE, expand=True, height=50, 
                              style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_detalles),
            ft.ElevatedButton("Mover", icon=ft.Icons.ADD_CARD, expand=True, height=50,
                              style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_movimientos),
            ft.ElevatedButton("Traspasar", icon=ft.Icons.SWAP_HORIZ, expand=True, height=50,
                              style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25), padding=5), on_click=renderizar_transferencias)
        ], spacing=10)

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: cargar_dashboard()), ft.Text(nombre, size=24, weight=ft.FontWeight.BOLD)]),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, on_click=confirmar_eliminar)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), 
            botones_menu, 
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            area_dinamica 
        ], scroll=ft.ScrollMode.AUTO))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, -1), expand=True))
        
        # Carga Detalles por defecto al entrar
        renderizar_detalles(None)

    # --- FLUJO 2: DASHBOARD (MAESTRO) ---
    def cargar_dashboard():
        page.clean()
        input_nombre = ft.TextField(label="Nombre (Ej. BBVA)", height=50, expand=True, border_radius=25)
        input_tipo = ft.Dropdown(options=[ft.dropdown.Option("Débito"), ft.dropdown.Option("Crédito"), ft.dropdown.Option("Efectivo")], width=120, height=50, border_radius=25)
        input_limite = ft.TextField(label="Límite (Crédito)", width=150, height=50, border_radius=25, keyboard_type=ft.KeyboardType.NUMBER)
        
        def btn_guardar_cuenta(e):
            if input_nombre.value and input_tipo.value:
                limite = float(input_limite.value) if input_limite.value else 0
                ejecutar_query("INSERT INTO fuentes (usuario_id, nombre, tipo, limite_credito) VALUES (?, ?, ?, ?)", (id_usr, input_nombre.value, input_tipo.value, limite))
                cargar_dashboard() 

        fuentes = ejecutar_query("SELECT * FROM fuentes WHERE usuario_id = ? AND id_padre IS NULL AND activo = 1", (id_usr,)).fetchall()
        lista_cuentas = ft.Column(spacing=15)
        if not fuentes: lista_cuentas.controls.append(ft.Text("No tienes cuentas.", color=ft.Colors.GREY_500))
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
            ft.Row([input_nombre, input_tipo]), input_limite,
            ft.ElevatedButton("Guardar Cuenta", on_click=btn_guardar_cuenta, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25))),
        ], scroll=ft.ScrollMode.AUTO))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, -1), expand=True))
        page.update()

    # --- FLUJO 1: LOGIN ---
    def cargar_login():
        page.clean()
        usr_input = ft.TextField(label="Usuario", width=300, border_radius=25); pin_input = ft.TextField(label="PIN", password=True, can_reveal_password=True, width=300, border_radius=25)
        def btn_entrar(e):
            nonlocal id_usr, nom_usr
            if not usr_input.value or not pin_input.value: mostrar_alerta("Llena campos", ft.Colors.RED_700); return
            user_id = ejecutar_query("SELECT id FROM usuarios WHERE nombre = ? AND pin = ?", (usr_input.value, pin_input.value)).fetchone()
            if user_id: id_usr = user_id[0]; nom_usr = usr_input.value; cargar_dashboard()
            else: mostrar_alerta("Datos incorrectos", ft.Colors.RED_700)
        def btn_registrar(e):
            if usr_input.value and pin_input.value:
                try: ejecutar_query("INSERT INTO usuarios (nombre, pin) VALUES (?, ?)", (usr_input.value, pin_input.value)); mostrar_alerta("¡Perfil Creado!")
                except sqlite3.IntegrityError: mostrar_alerta("Usuario ya existe", ft.Colors.RED_700)
            else: mostrar_alerta("Llena campos", ft.Colors.RED_700)

        panel = ft.Container(width=400, padding=40, border_radius=25, bgcolor="#1E2029", content=ft.Column([
            ft.Icon(ft.Icons.LOCK, size=60, color=ft.Colors.BLUE_400), ft.Text("Bienvenido", size=28, weight=ft.FontWeight.BOLD),
            usr_input, pin_input, ft.ElevatedButton("Entrar", on_click=btn_entrar, width=300, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25))),
            ft.TextButton("Crear Perfil", on_click=btn_registrar)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        page.add(ft.Container(content=panel, alignment=ft.Alignment(0, 0), expand=True))
        page.update()

    inicializar_db()
    cargar_login()

if __name__ == "__main__":
    import os
    inicializar_db()
    # Ajuste para servidores web (Render, Railway, etc.)
    port = int(os.environ.get("PORT", 8080))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port)
