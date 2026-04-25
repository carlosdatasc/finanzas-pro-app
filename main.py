import flet as ft
import psycopg2
import os
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN DE BASE DE DATOS (NUBE)
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://tu_usuario:tu_contraseña@ep-tu-servidor.us-east-2.aws.neon.tech/finanzas_v4_pro?sslmode=require")

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
        page.snack_bar = ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=color, duration=3000)
        page.snack_bar.open = True
        page.update()

    # --- VISTA DE CUENTA ---
    def cargar_vista_cuenta(fuente):
        page.clean()
        f_id, _, nombre, tipo, _, limite, _ = fuente
        area_dinamica = ft.Container()

        def confirmar_borrado_item(titulo, mensaje, on_confirm):
            def cerrar(e):
                dlg.open = False
                page.update()

            def ejecutar_y_cerrar(e):
                on_confirm()
                dlg.open = False
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text(titulo),
                content=ft.Text(mensaje),
                actions=[
                    ft.TextButton("Cancelar", on_click=cerrar),
                    ft.TextButton("Eliminar", on_click=ejecutar_y_cerrar, style=ft.ButtonStyle(color=ft.Colors.RED)),
                ],
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        def obtener_historial_completo():
            movs = ejecutar_query("SELECT id, fecha, monto, tipo, categoria, subcategoria, concepto FROM transacciones WHERE id_fuente=%s", (f_id,))
            historial = []
            for m in movs:
                historial.append({'id': m[0], 'fecha': m[1], 'monto': m[2], 'tipo': m[3], 'cat': m[4], 'sub': m[5], 'con': m[6], 'is_trans': False})
            
            t_out = ejecutar_query("SELECT t.fecha, t.monto, 'Gasto', 'Transferencia', '', 'A: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_destino = f.id WHERE t.id_origen=%s", (f_id,))
            for t in t_out:
                historial.append({'fecha': t[0], 'monto': t[1], 'tipo': t[2], 'cat': t[3], 'sub': t[4], 'con': t[5], 'is_trans': True})
            
            t_in = ejecutar_query("SELECT t.fecha, t.monto, 'Ingreso', 'Transferencia', '', 'De: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_origen = f.id WHERE t.id_destino=%s", (f_id,))
            for t in t_in:
                historial.append({'fecha': t[0], 'monto': t[1], 'tipo': t[2], 'cat': t[3], 'sub': t[4], 'con': t[5], 'is_trans': True})

            historial.sort(key=lambda x: x['fecha'], reverse=True)
            return historial

        # ==========================================
        # PESTAÑA 1: DETALLES
        # ==========================================
        def renderizar_detalles(e):
            saldo_o_deuda = calcular_saldo(f_id, tipo)
            historial_completo = obtener_historial_completo()
            
            color_bg = "#1E3A8A" if tipo == "Crédito" else ("#065F46" if tipo == "Débito" else "#78350F")
            tarjeta_info = ft.Container(padding=25, border_radius=25, bgcolor=color_bg, content=ft.Column([
                ft.Text(f"Saldo {'Disponible' if tipo != 'Crédito' else 'Gastado'}", size=14, color=ft.Colors.WHITE70),
                ft.Text(f"${abs(saldo_o_deuda):,.2f}", size=35, weight=ft.FontWeight.BOLD),
            ]))

            contenido_extra = ft.Column(spacing=15)
            
            if historial_completo:
                contenido_extra.controls.append(ft.Text("Últimos Movimientos", weight=ft.FontWeight.BOLD))
                for t in historial_completo[:10]: 
                    c = ft.Colors.RED_400 if t['tipo'] == "Gasto" else ft.Colors.GREEN_400
                    sub_txt = f" > {t['sub']}" if t['sub'] else ""
                    fecha_str = str(t['fecha'])[:16]

                    def borrar_t(tid=t.get('id')):
                        ejecutar_query("DELETE FROM transacciones WHERE id=%s", (tid,))
                        mostrar_alerta("Registro eliminado correctamente", ft.Colors.RED_700)
                        renderizar_detalles(None)

                    btn_borrar = ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color="grey", 
                                             on_click=lambda e, tid=t.get('id'): confirmar_borrado_item("¿Borrar Registro?", "Esta acción no se puede deshacer.", lambda: borrar_t(tid))) if not t['is_trans'] else ft.Container()

                    contenido_extra.controls.append(ft.Container(padding=15, border_radius=20, bgcolor="#1E2029", content=ft.Row([
                        ft.Column([
                            ft.Text(f"{t['cat']}{sub_txt}", size=14, weight=ft.FontWeight.BOLD), 
                            ft.Text(f"{fecha_str} | {t['con']}", size=12, color=ft.Colors.GREY_400) 
                        ], expand=True, spacing=2), 
                        ft.Column([ft.Text(f"${t['monto']:.2f}", color=c, weight=ft.FontWeight.BOLD), btn_borrar], horizontal_alignment="end")
                    ])))

            if tipo == "Débito":
                def abrir_dialogo_apartado(e_click):
                    input_nombre_ap = ft.TextField(label="Nombre del apartado (Ej. Viaje)", border_radius=15)
                    def guardar_ap(e_interno):
                        if input_nombre_ap.value:
                            nombre_apartado = input_nombre_ap.value
                            ejecutar_query("INSERT INTO fuentes (usuario_id, nombre, tipo, id_padre, limite_credito) VALUES (%s, %s, 'Débito', %s, 0)", 
                                           (id_usr, nombre_apartado, f_id))
                            dlg_ap.open = False
                            renderizar_detalles(None)
                            mostrar_alerta(f"Apartado '{nombre_apartado}' creado correctamente")
                        else:
                            mostrar_alerta("Debes escribir un nombre", ft.Colors.RED_700)

                    dlg_ap = ft.AlertDialog(title=ft.Text("Crear Apartado"), content=input_nombre_ap, actions=[ft.TextButton("Guardar", on_click=guardar_ap)])
                    page.overlay.append(dlg_ap)
                    dlg_ap.open = True
                    page.update()

                def eliminar_ap(ap_id, ap_nom):
                    ejecutar_query("UPDATE fuentes SET activo=FALSE WHERE id=%s", (ap_id,))
                    mostrar_alerta(f"Apartado '{ap_nom}' eliminado", ft.Colors.RED_700)
                    renderizar_detalles(None)

                header_apartados = ft.Row([
                    ft.Text("Tus Apartados", weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE_400, on_click=abrir_dialogo_apartado, tooltip="Crear Apartado")
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                
                contenido_extra.controls.append(header_apartados)

                apartados = ejecutar_query("SELECT id, nombre FROM fuentes WHERE id_padre = %s AND activo = TRUE", (f_id,))
                if apartados:
                    for ap in apartados:
                        saldo_ap = calcular_saldo(ap[0], "Débito")
                        contenido_extra.controls.append(ft.Container(padding=15, border_radius=25, bgcolor="#1E2029", content=ft.Row([
                            ft.Icon(ft.Icons.SAVINGS, color=ft.Colors.BLUE_300), 
                            ft.Container(ft.Text(ap[1]), expand=True, on_click=lambda e, a=(ap[0], None, ap[1], "Débito", f_id, 0, True): cargar_vista_cuenta(a)), 
                            ft.Text(f"${saldo_ap:,.2f}", weight=ft.FontWeight.BOLD),
                            ft.IconButton(ft.Icons.DELETE_SWEEP_OUTLINED, icon_color="red400", on_click=lambda e, i=ap[0], n=ap[1]: confirmar_borrado_item("¿Eliminar Apartado?", f"Se ocultará '{n}'. Los registros se conservarán.", lambda: eliminar_ap(i, n)))
                        ])))
                else:
                    contenido_extra.controls.append(ft.Text("Aún no tienes apartados en esta cuenta.", color=ft.Colors.GREY_500, size=12))

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
                        nombre_cat = input_nueva_cat.value
                        ejecutar_query("INSERT INTO categorias_usuario (usuario_id, nombre) VALUES (%s, %s)", (id_usr, nombre_cat))
                        dlg.open = False
                        renderizar_movimientos(None) 
                        mostrar_alerta(f"Categoría '{nombre_cat}' agregada a tu lista")
                    else:
                        mostrar_alerta("El nombre no puede estar vacío", ft.Colors.RED_700)
                
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
                    valor_monto = float(monto_input.value)
                    ejecutar_query("INSERT INTO transacciones (monto, id_fuente, tipo, categoria, subcategoria, concepto) VALUES (%s, %s, %s, %s, %s, %s)",
                                   (valor_monto, f_id, tipo_mov_drop.value, cat_drop.value, subcategoria_input.value, concepto_input.value))
                    renderizar_detalles(None) 
                    mostrar_alerta(f"Movimiento de ${valor_monto:,.2f} registrado correctamente")
                except ValueError:
                    mostrar_alerta("El monto debe ser un número válido", ft.Colors.RED_700)

            formulario = ft.Container(padding=25, border_radius=25, bgcolor="#1E2029", content=ft.Column([
                ft.Text("Registrar Nuevo Movimiento", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([tipo_mov_drop, monto_input]),
                ft.Row([cat_drop, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE_400, on_click=abrir_dialogo_categoria)]),
                subcategoria_input, concepto_input,
                ft.ElevatedButton("Guardar Movimiento", on_click=btn_guardar, width=500, height=50, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=25)))
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
                    mostrar_alerta("Completa los campos para traspasar", ft.Colors.RED_700); return
                try:
                    monto = float(monto_input.value)
                    if tipo in ["Débito", "Efectivo"] and monto > calcular_saldo(f_id, tipo):
                        mostrar_alerta("Fondos insuficientes para el traspaso", ft.Colors.RED_700); return
                    
                    ejecutar_query("INSERT INTO transferencias (monto, id_origen, id_destino) VALUES (%s, %s, %s)", (monto, f_id, int(destino_drop.value)))
                    renderizar_detalles(None)
                    mostrar_alerta(f"¡Traspaso de ${monto:,.2f} enviado con éxito!")
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

        def eliminar_cuenta_maestra():
            ejecutar_query("UPDATE fuentes SET activo=FALSE WHERE id=%s OR id_padre=%s", (f_id, f_id))
            mostrar_alerta(f"Cuenta '{nombre}' eliminada permanentemente", ft.Colors.RED_700)
            cargar_dashboard()

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([
                ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: cargar_dashboard()), ft.Text(nombre, size=24, weight=ft.FontWeight.BOLD)]),
                ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color="red", tooltip="Eliminar Cuenta", on_click=lambda _: confirmar_borrado_item("¿Eliminar Cuenta?", "Se borrará esta cuenta y TODOS sus apartados en cascada.", eliminar_cuenta_maestra))
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
                nombre_cuenta = input_nombre.value
                ejecutar_query("INSERT INTO fuentes (usuario_id, nombre, tipo, limite_credito) VALUES (%s, %s, %s, %s)", (id_usr, nombre_cuenta, input_tipo.value, 0))
                cargar_dashboard() 
                mostrar_alerta(f"{input_tipo.value} '{nombre_cuenta}' creada correctamente")
            else:
                mostrar_alerta("Ingresa un nombre y selecciona un tipo", ft.Colors.RED_700)

        fuentes = ejecutar_query("SELECT * FROM fuentes WHERE usuario_id=%s AND id_padre IS NULL AND activo=TRUE", (id_usr,))
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

        def btn_logout(e):
            mostrar_alerta("Sesión cerrada correctamente", ft.Colors.BLUE_GREY_700)
            cargar_login()

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([ft.Text(f"Hola, {nom_usr}", size=24, weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.LOGOUT, on_click=btn_logout, tooltip="Cerrar Sesión")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
                mostrar_alerta(f"¡Bienvenido de vuelta, {nom_usr}!")
            else: 
                mostrar_alerta("Datos incorrectos o usuario no existe", ft.Colors.RED_700)
            
        def btn_registrar(e):
            if usr_input.value and pin_input.value:
                try: 
                    ejecutar_query("INSERT INTO usuarios (nombre, pin) VALUES (%s, %s)", (usr_input.value, pin_input.value))
                    mostrar_alerta("¡Cuenta creada exitosamente! Ahora Inicia Sesión", ft.Colors.GREEN_700)
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
