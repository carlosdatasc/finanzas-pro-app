import flet as ft
import psycopg2
import os
from datetime import datetime

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
    
    id_usr, nom_usr = None, None

    def mostrar_alerta(mensaje, color=ft.Colors.GREEN_700):
        page.snack_bar = ft.SnackBar(ft.Text(mensaje, color=ft.Colors.WHITE, weight="bold"), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    # --- VISTA DE CUENTA ---
    def cargar_vista_cuenta(fuente):
        page.clean()
        f_id, _, nombre, tipo, _, limite, _ = fuente

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

        area_dinamica = ft.Container()

        def obtener_historial_completo():
            # Traemos el ID de la transacción también para poder borrarla
            movs = ejecutar_query("SELECT id, fecha, monto, tipo, categoria, subcategoria, concepto FROM transacciones WHERE id_fuente=%s", (f_id,))
            historial = []
            for m in movs:
                historial.append({'id': m[0], 'fecha': m[1], 'monto': m[2], 'tipo': m[3], 'cat': m[4], 'sub': m[5], 'con': m[6], 'is_trans': False})
            
            # Transferencias (No borrables por ahora por complejidad de doble saldo)
            t_out = ejecutar_query("SELECT t.fecha, t.monto, 'Gasto', 'Transferencia', '', 'A: ' || f.nombre FROM transferencias t JOIN fuentes f ON t.id_destino = f.id WHERE t.id_origen=%s", (f_id,))
            for t in t_out:
                historial.append({'fecha': t[0], 'monto': t[1], 'tipo': t[2], 'cat': t[3], 'sub': t[4], 'con': t[5], 'is_trans': True})
            
            historial.sort(key=lambda x: x['fecha'], reverse=True)
            return historial

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

                    # Icono de basura solo para transacciones normales
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
                def eliminar_ap(ap_id, ap_nom):
                    ejecutar_query("UPDATE fuentes SET activo=FALSE WHERE id=%s", (ap_id,))
                    mostrar_alerta(f"Apartado '{ap_nom}' eliminado", ft.Colors.RED_700)
                    renderizar_detalles(None)

                header_apartados = ft.Row([ft.Text("Tus Apartados", weight="bold"), ft.IconButton(ft.Icons.ADD_CIRCLE, on_click=lambda _: None)], alignment="spaceBetween")
                contenido_extra.controls.append(header_apartados)

                apartados = ejecutar_query("SELECT id, nombre FROM fuentes WHERE id_padre = %s AND activo = TRUE", (f_id,))
                for ap in apartados:
                    saldo_ap = calcular_saldo(ap[0], "Débito")
                    contenido_extra.controls.append(ft.Container(padding=15, border_radius=25, bgcolor="#1E2029", content=ft.Row([
                        ft.Icon(ft.Icons.SAVINGS, color=ft.Colors.BLUE_300), 
                        ft.Text(ap[1], expand=True), 
                        ft.Text(f"${saldo_ap:,.2f}", weight="bold"),
                        ft.IconButton(ft.Icons.DELETE_SWEEP_OUTLINED, icon_color="red400", on_click=lambda e, i=ap[0], n=ap[1]: confirmar_borrado_item("¿Eliminar Apartado?", f"Se ocultará '{n}'. Los registros no se borrarán.", lambda: eliminar_ap(i, n)))
                    ])))

            area_dinamica.content = ft.Column([tarjeta_info, ft.Divider(color=ft.Colors.TRANSPARENT), contenido_extra])
            page.update()

        # ... (Resto de funciones: renderizar_movimientos y renderizar_transferencias se mantienen igual) ...
        # (Asegúrate de copiar el código completo de las versiones anteriores para esas funciones)

        def eliminar_cuenta_maestra():
            # Borrado lógico en cascada
            ejecutar_query("UPDATE fuentes SET activo=FALSE WHERE id=%s OR id_padre=%s", (f_id, f_id))
            mostrar_alerta(f"Cuenta '{nombre}' y sus apartados eliminados", ft.Colors.RED_700)
            cargar_dashboard()

        panel = ft.Container(width=500, padding=20, content=ft.Column([
            ft.Row([
                ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: cargar_dashboard()), ft.Text(nombre, size=24, weight="bold")]),
                ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color="red", on_click=lambda _: confirmar_borrado_item("¿Eliminar Cuenta?", "Se borrará esta cuenta y TODOS sus apartados.", eliminar_cuenta_maestra))
            ], alignment="spaceBetween"),
            ft.Row([ft.ElevatedButton("Detalles", on_click=renderizar_detalles, expand=True)]), # Simplificado para el ejemplo
            area_dinamica 
        ], scroll="auto"))
        page.add(ft.Container(content=panel, alignment=ft.alignment.top_center, expand=True))
        renderizar_detalles(None)

    # --- DASHBOARD ---
    def cargar_dashboard():
        page.clean()
        # ... (Lógica de dashboard igual, asegurando el filtro id_padre IS NULL) ...
        # (Añadir SnackBar al crear cuenta nueva como hiciste anteriormente)
        page.update()

    inicializar_db()
    cargar_login()

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("PORT", 8080)))
