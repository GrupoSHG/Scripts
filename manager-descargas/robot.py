"""Robot: descarga los informes de Manager Time ERP y los carga a Supabase.

Flujo (calibrado sobre la pantalla real, viewport 1600x900):
  home.ramaflex.cl -> login -> botón "Manager Time ERP" (abre el escritorio remoto TSplus)
  -> panel Remote App -> "ERP Manager SQL Polchile" -> login Manager (usuario + clave)
  -> menú Manager -> Centro de Información -> informe -> Guardar (disquete)
  -> nombre + OK -> "¿Abrir con Excel?" Sí -> el navegador recibe el .xls
  -> Logoff del panel Remote App.

Cada paso espera a reconocer la pantalla comparando una franja con las imágenes de
referencias/. El escritorio remoto pierde teclas si llegan rápido: la lista de
informes se recorre de a una fila, confirmando el informe por la línea
"Descripción del Filtro".

  python robot.py              descarga y carga a Supabase
  python robot.py --sin-cargar solo descarga
  python robot.py --ver        con ventana visible (para depurar)
"""
import io
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

import cargar

BASE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(BASE, "referencias")
DESCARGAS = os.path.join(BASE, "descargas")
CAPTURAS = os.path.join(BASE, "capturas")
UMBRAL = 6          # diferencia media (0-255) bajo la cual una franja "calza" con su referencia
INTENTOS_SESION = 4

# Franjas de pantalla que identifican cada estado: (referencia, caja x0, y0, x1, y1)
PANTALLAS = {
    "panel_remote_app":   (5, 322, 190, 340),
    "login_manager":      (252, 313, 345, 355),   # etiquetas del login (no dependen del foco)
    "menu_principal":     (0, 25, 170, 42),
    "menu_desplegado":    (130, 395, 260, 410),   # opción "Centro de Información" del menú Manager
    "centro_informacion": (15, 127, 600, 142),   # encabezados de la lista de informes
    "visor_consultas":    (240, 88, 410, 102),    # "Generar Comprobante  Agrupar"
    "dialogo_exportar":   (40, 165, 148, 207),    # etiquetas Nombre / Formato
    "abrir_con_excel":    (700, 402, 930, 430),   # "¿Desea ahora abrir ... Excel?"
    "cierre_sesion":      (713, 446, 875, 460),   # "¿Quiere dejar su sesión ahora?"
}
CAJA_FILTRO = (15, 510, 420, 525)   # línea "Descripción del Filtro : <informe>"

INFORMES = [
    # (tabla Supabase, referencia de la línea de filtro, sufijo del nombre de archivo)
    ("ventas_full", "filtro_ventas_full", "vf"),
    ("notas_de_venta", "filtro_notas_de_venta", "nvs"),
]

# Coordenadas calibradas
PANEL_ERP_MANAGER = (80, 443)
LOGIN_USUARIO = (460, 369)
CAJA_USUARIO = (349, 364, 470, 376)  # texto del campo Usuario (referencia: usuario_manager.png)
LOGIN_CLAVE = (468, 417)
LOGIN_OK = (485, 440)
CAJA_CLAVE = (352, 410, 585, 425)  # campo Clave: se ven puntos cuando tiene texto
MENU_MANAGER = (138, 33)
MENU_CENTRO_INFO = (192, 402)
LISTA_PRIMERA_FILA = (300, 154)
VISOR_GUARDAR = (33, 95)
VISOR_CERRAR = (1573, 62)
EXPORT_NOMBRE = (380, 171)
EXPORT_OK = (155, 112)
EXCEL_SI = (760, 519)
TASKBAR_REMOTE_APP = (1535, 887)
PANEL_LOGOFF = (67, 524)
CIERRE_SESION_SI = (768, 502)


class FalloRobot(Exception):
    pass


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def diferencia(a, b):
    return ImageStat.Stat(ImageChops.difference(a.convert("L"), b.convert("L"))).mean[0]


class Sesion:
    def __init__(self, pagina):
        self.m = pagina
        self.refs = {os.path.splitext(f)[0]: Image.open(os.path.join(REFS, f))
                     for f in os.listdir(REFS) if f.endswith(".png")}
        self.descargas = []
        pagina.on("download", self._descarga)

    def _descarga(self, d):
        destino = os.path.join(DESCARGAS, d.suggested_filename)
        d.save_as(destino)
        self.descargas.append(destino)
        log(f"descargado {d.suggested_filename}")

    def captura(self, nombre=None):
        # Con el escritorio remoto dibujando, una captura puede demorar: reintentar.
        for intento in range(3):
            try:
                datos = self.m.screenshot(timeout=45000)
                break
            except PlaywrightTimeout:
                if intento == 2 or self.m.is_closed():
                    raise FalloRobot("la pantalla no responde (captura sin respuesta)")
                self.m.wait_for_timeout(3000)
        img = Image.open(io.BytesIO(datos))
        if nombre:
            img.save(os.path.join(CAPTURAS, f"{nombre}.png"))
        return img

    def calza(self, ref, caja, img=None):
        img = img or self.captura()
        return diferencia(self.refs[ref], img.crop(caja)) < UMBRAL

    def esperar(self, pantalla, timeout=60):
        caja = PANTALLAS[pantalla]
        limite = time.time() + timeout
        while time.time() < limite:
            if self.m.is_closed():
                raise FalloRobot(f"la sesión remota se cerró esperando '{pantalla}'")
            if self.calza(pantalla, caja):
                return
            self.m.wait_for_timeout(1000)
        self.captura(f"error_{pantalla}")
        raise FalloRobot(f"no apareció la pantalla '{pantalla}' en {timeout}s")

    def click(self, xy, pausa=0.8):
        self.m.mouse.click(*xy)
        self.m.wait_for_timeout(pausa * 1000)

    def tecla(self, tecla, pausa=0.6):
        self.m.keyboard.press(tecla)
        self.m.wait_for_timeout(pausa * 1000)

    def escribir(self, texto):
        for c in texto:
            self.m.keyboard.type(c)
            self.m.wait_for_timeout(200)

    # ── Pasos ──

    def elegir_usuario(self, usuario):
        """El login recuerda el último usuario que entró desde el escritorio remoto
        (hay varios). Se escribe el nombre en el combo y se confirma contra la
        referencia antes de escribir la clave, para no usarla en otro usuario."""
        for _ in range(3):
            self.click(LOGIN_USUARIO)
            self.tecla("Home", 0.5)
            self.tecla("Shift+End", 0.5)
            self.escribir(usuario)
            self.tecla("Tab", 2.5)                   # Manager valida el nombre y carga el email
            if self.calza("usuario_manager", CAJA_USUARIO):
                return
        self.captura("error_usuario")
        raise FalloRobot(f"no se pudo seleccionar el usuario '{usuario}' en el login de Manager "
                         "(si cambió MANAGER_USUARIO, hay que recapturar referencias/usuario_manager.png)")

    def login_manager(self, usuario, clave):
        self.esperar("panel_remote_app", 90)
        self.click(PANEL_ERP_MANAGER)
        self.esperar("login_manager", 90)
        self.m.wait_for_timeout(1500)
        self.elegir_usuario(usuario)
        # El diálogo puede aparecer sin foco: clic en Clave y confirmar que el texto llegó.
        for intento in range(3):
            self.click(LOGIN_CLAVE)
            if intento:                              # reintento: vaciar lo que haya quedado a medias
                self.tecla("End", 0.3)
                for _ in range(25):
                    self.tecla("Backspace", 0.1)
            self.escribir(clave)
            self.m.wait_for_timeout(2500)            # el escritorio remoto tarda en dibujar
            puntos = sum(self.captura().crop(CAJA_CLAVE).convert("L").histogram()[:80])
            if puntos > 40:
                break
        else:
            self.captura("error_clave")
            raise FalloRobot("no se pudo escribir la clave de Manager")
        self.click(LOGIN_OK, 2)
        self.esperar("menu_principal", 60)
        self.m.wait_for_timeout(2000)

    def abrir_centro_informacion(self):
        for _ in range(4):
            self.click(MENU_MANAGER, 2)
            if not self.calza("menu_desplegado", PANTALLAS["menu_desplegado"]):
                self.tecla("Escape", 1)
                continue
            self.click(MENU_CENTRO_INFO, 2)
            try:
                self.esperar("centro_informacion", 30)
                self.m.wait_for_timeout(1500)
                return
            except FalloRobot:
                pass
        self.captura("error_menu")
        raise FalloRobot("no se pudo abrir el Centro de Información")

    def seleccionar_informe(self, ref_filtro):
        # Ir al inicio de la lista y bajar de a una fila hasta que la línea de filtro calce.
        self.click(LISTA_PRIMERA_FILA)           # foco en la lista
        for _ in range(12):
            self.tecla("PageUp", 0.3)
        self.tecla("Home", 1)
        for _ in range(80):
            if self.calza(ref_filtro, CAJA_FILTRO):
                return
            self.tecla("ArrowDown", 0.7)
        self.captura(f"error_{ref_filtro}")
        raise FalloRobot(f"no se encontró el informe '{ref_filtro}' en la lista")

    def fila_seleccionada(self):
        """Centro vertical de la franja azul de selección en la lista de informes."""
        img = self.captura().convert("RGB")
        racha = []
        for y in range(148, 505):
            r, g, b = img.getpixel((450, y))
            if r < 40 and 90 < g < 150 and b > 180:
                racha.append(y)
            elif len(racha) >= 8:
                break
            else:
                racha = []
        if len(racha) < 8:
            raise FalloRobot("no se encontró la fila seleccionada en la lista de informes")
        return racha[len(racha) // 2]

    def exportar(self, sufijo):
        antes = len(self.descargas)
        self.m.mouse.dblclick(300, self.fila_seleccionada())   # abre el informe seleccionado
        self.esperar("visor_consultas", 180)
        self.m.wait_for_timeout(4000)            # que termine de cargar la grilla
        self.click(VISOR_GUARDAR, 2)
        self.esperar("dialogo_exportar", 30)
        self.click(EXPORT_NOMBRE)
        self.tecla("End")
        self.escribir(sufijo)
        self.click(EXPORT_OK, 2)
        self.esperar("abrir_con_excel", 120)
        self.click(EXCEL_SI)
        limite = time.time() + 180
        while len(self.descargas) == antes:
            if time.time() > limite or self.m.is_closed():
                self.captura(f"error_descarga_{sufijo}")
                raise FalloRobot(f"no llegó la descarga del informe '{sufijo}'")
            self.m.wait_for_timeout(1000)
        # Manager queda ocupado abriendo Excel en el servidor: reintentar el cierre del visor.
        limite = time.time() + 120
        while not self.calza("centro_informacion", PANTALLAS["centro_informacion"]):
            if time.time() > limite or self.m.is_closed():
                self.captura("error_cerrar_visor")
                raise FalloRobot("no se pudo cerrar el visor de consultas")
            self.click(VISOR_CERRAR, 4)
        self.m.wait_for_timeout(1500)
        return self.descargas[-1]

    def logoff(self):
        try:
            self.click(TASKBAR_REMOTE_APP, 2)
            self.click(PANEL_LOGOFF, 2)
            self.esperar("cierre_sesion", 15)
            self.click(CIERRE_SESION_SI, 3)
        except Exception as e:
            if self.m.is_closed():               # tras el "Sí" la pestaña se cierra sola
                log("logoff OK")
            else:
                log(f"logoff: {e}")


def abrir_manager(ctx, correo, clave_ramaflex):
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://home.ramaflex.cl", timeout=60000)
    pg.wait_for_timeout(5000)
    if pg.locator("input[name=password]").count():
        log("login Ramaflex")
        pg.fill("input[name=username]", correo)
        pg.fill("input[name=password]", clave_ramaflex)
        pg.click("button[name=action]")
        pg.wait_for_timeout(8000)
    boton = pg.get_by_role("button", name="Manager Time ERP")
    if pg.get_by_role("button", name="Entendido").count():
        pg.get_by_role("button", name="Entendido").click()
        pg.wait_for_timeout(1000)
    if not boton.count():
        raise FalloRobot("no aparece el botón 'Manager Time ERP' (¿falló el login de Ramaflex?)")
    with ctx.expect_page(timeout=20000) as nueva:
        boton.click()
    return nueva.value


def descargar(visible=False):
    os.makedirs(DESCARGAS, exist_ok=True)
    os.makedirs(CAPTURAS, exist_ok=True)
    env = os.environ
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(BASE, ".perfil"), headless=not visible,
            viewport={"width": 1600, "height": 900}, accept_downloads=True)
        try:
            for intento in range(1, INTENTOS_SESION + 1):
                log(f"abriendo Manager (intento {intento})")
                s = Sesion(abrir_manager(ctx, env["RAMAFLEX_CORREO"], env["RAMAFLEX_CLAVE"]))
                try:
                    s.login_manager(env["MANAGER_USUARIO"], env["MANAGER_CLAVE"])
                    break
                except Exception as e:
                    # La sesión remota a veces se corta al conectar (otra sesión del mismo
                    # usuario, o una anterior que el servidor está cerrando).
                    log(f"intento {intento} falló: {e}")
                    if not s.m.is_closed():
                        s.logoff()       # cerrar limpio: una sesión colgada corta la siguiente
                    if not s.m.is_closed():
                        s.m.close()
                    if intento == INTENTOS_SESION:
                        raise
                    time.sleep(45)
            log("sesión de Manager iniciada")
            archivos = {}
            try:
                s.abrir_centro_informacion()
                for tabla, ref_filtro, sufijo in INFORMES:
                    log(f"exportando {tabla}")
                    s.seleccionar_informe(ref_filtro)
                    archivos[tabla] = s.exportar(sufijo)
            finally:
                s.captura("ultimo_estado")
                s.logoff()
            return archivos
        finally:
            ctx.close()


def limpiar_descargas(conservar=40):
    archivos = sorted((os.path.join(DESCARGAS, f) for f in os.listdir(DESCARGAS)), key=os.path.getmtime)
    for f in archivos[:-conservar]:
        os.remove(f)


def main():
    load_dotenv(os.path.join(BASE, ".env"))
    inicio = time.time()
    try:
        archivos = descargar(visible="--ver" in sys.argv)
        if "--sin-cargar" not in sys.argv:
            for tabla, ruta in archivos.items():
                cargar.cargar(tabla, ruta)
        limpiar_descargas()
        log(f"OK en {time.time() - inicio:.0f}s")
    except Exception as e:
        log(f"FALLÓ: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
