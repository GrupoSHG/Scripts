"""
descargar_backup_manager.py
============================
Descarga automáticamente el archivo .bak más reciente desde Manager.
Usa Selenium para login y obtener la presigned URL, luego descarga con requests.

Requiere: pip install selenium webdriver-manager requests
"""

import os
import time
import shutil
import logging
import requests
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
MANAGER_URL     = "https://prodkernel.manager.cl"
EMPRESA_CD      = "prodkernel"
USUARIO         = "respaldos_poliuretano"
CONTRASENA      = "puCvufRrcjXemsU5jLY4V9uz"
CARPETA_DESTINO = r"C:\Backups\Manager"
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("backup_manager.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def preparar_carpetas():
    destino = Path(CARPETA_DESTINO)
    destino.mkdir(parents=True, exist_ok=True)
    tmp = Path(os.environ["TEMP"]) / "manager_dl"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.bak"):
        f.unlink(missing_ok=True)
    return destino, tmp


def crear_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def hacer_login(driver: webdriver.Chrome, wait: WebDriverWait) -> str:
    log.info(f"Abriendo login: {MANAGER_URL}/index.html")
    driver.get(f"{MANAGER_URL}/index.html")

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input")))
    time.sleep(1)

    inputs = [i for i in driver.find_elements(By.CSS_SELECTOR, "input") if i.is_displayed()]
    log.info(f"Inputs visibles: {len(inputs)}")

    inputs[0].clear()
    inputs[0].send_keys(USUARIO)
    inputs[1].clear()
    inputs[1].send_keys(CONTRASENA)

    boton = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(text(), 'Login')] | //input[@value='Login']")
    ))
    boton.click()
    log.info("Login enviado...")
    time.sleep(4)

    if "session_id=" not in driver.current_url:
        driver.save_screenshot("error_login.png")
        raise Exception(f"Login falló. URL: {driver.current_url}")

    session_id = driver.current_url.split("session_id=")[1].split("&")[0]
    log.info(f"✅ Login exitoso. session_id: {session_id[:8]}...")
    return session_id


def navegar_a_backups(driver: webdriver.Chrome, wait: WebDriverWait, session_id: str) -> list:
    url = f"{MANAGER_URL}/managerbackups.html?session_id={session_id}&cd={EMPRESA_CD}"
    log.info(f"Navegando a: {url}")
    driver.get(url)

    wait.until(EC.presence_of_element_located((By.ID, "gridmngbkps")))

    for recarga in range(20):
        log.info(f"Recarga {recarga+1}/10...")
        driver.refresh()
        time.sleep(4)

        filas = driver.find_elements(By.XPATH, "//tr[.//td[contains(text(), '.bak')]]")
        log.info(f"  filas .bak encontradas: {len(filas)}")

        if filas:
            log.info(f"✅ Tabla cargada en recarga {recarga+1}.")
            return filas

    raise TimeoutError("Tabla no cargó tras 10 recargas.")


def obtener_presigned_url(filas: list) -> tuple[str, str]:
    mejor_fila   = None
    mejor_fecha  = None
    mejor_nombre = "desconocido"

    for fila in filas:
        celdas = fila.find_elements(By.TAG_NAME, "td")
        if len(celdas) < 3:
            continue

        nombre      = celdas[1].text.strip()
        texto_fecha = celdas[2].text.strip()

        # ── Filtrar solo archivos T779354202A ──
        if "T779354202C" not in nombre:
            log.info(f"  Ignorando: {nombre}")
            continue

        try:
            fecha = datetime.fromisoformat(texto_fecha.replace(" ", "T"))
        except ValueError:
            try:
                fecha = datetime.strptime(texto_fecha[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                log.warning(f"No se pudo parsear fecha: '{texto_fecha}'")
                continue

        if mejor_fecha is None or fecha > mejor_fecha:
            mejor_fecha  = fecha
            mejor_fila   = fila
            mejor_nombre = nombre

    if mejor_fila is None:
        raise Exception("No se encontró ningún backup T779354202A.")

    log.info(f"Backup seleccionado: {mejor_nombre} ({mejor_fecha})")

    # Log completo del HTML de la fila para debug
    log.info(f"HTML fila completa: {mejor_fila.get_attribute('innerHTML')[:500]}")

    # Busca la presigned URL — puede estar oculta o en atributo
    # Busca la presigned URL — puede estar oculta o en atributo
    import html as html_module
    # Busca la presigned URL — puede estar oculta o en atributo
    try:
        elem = mejor_fila.find_element(By.CSS_SELECTOR, ".presigned_url")
        raw = elem.text.strip() or elem.get_attribute("innerHTML").strip()
        presigned_url = html_module.unescape(raw)
    except Exception:
        presigned_url = ""
    if not presigned_url:
        raise Exception("Presigned URL vacía.")

    return presigned_url, mejor_nombre
def descargar_desde_s3(presigned_url: str, nombre_archivo: str, carpeta_tmp: Path) -> Path:
    """Descarga el .bak directamente desde S3 usando la presigned URL."""
    nombre_limpio = Path(nombre_archivo).name
    if not nombre_limpio.endswith(".bak"):
        nombre_limpio += ".bak"

    ruta_tmp = carpeta_tmp / nombre_limpio
    log.info(f"Descargando {nombre_limpio} desde S3...")

    with requests.get(presigned_url, stream=True, timeout=600) as r:
        r.raise_for_status()
        total      = int(r.headers.get('content-length', 0))
        descargado = 0
        with open(ruta_tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)
                descargado += len(chunk)
                if total and descargado % (10 * 1024 * 1024) < 1024 * 1024:
                    log.info(f"  {descargado/1e6:.0f} MB / {total/1e6:.0f} MB ({descargado/total*100:.0f}%)")

    tam = ruta_tmp.stat().st_size / 1e6
    log.info(f"✅ Descarga completa: {nombre_limpio} ({tam:.1f} MB)")
    return ruta_tmp


def mover_a_destino(archivo: Path, destino: Path, nombre_original: str) -> Path:
    fecha         = datetime.now().strftime("%Y-%m-%d")
    stem          = Path(nombre_original).stem if nombre_original != "desconocido" else archivo.stem
    nuevo_nombre  = f"{stem}_{fecha}.bak"
    destino_final = destino / nuevo_nombre

    if destino_final.exists():
        nuevo_nombre  = f"{stem}_{fecha}_{int(time.time())}.bak"
        destino_final = destino / nuevo_nombre

    shutil.move(str(archivo), str(destino_final))
    log.info(f"Backup guardado en: {destino_final}")
    return destino_final


def main():
    log.info("=" * 55)
    log.info("  Iniciando descarga automática de backup Manager")
    log.info("=" * 55)

    destino, carpeta_tmp = preparar_carpetas()
    driver = crear_driver()

    try:
        wait = WebDriverWait(driver, 60)

        # 1. Login
        session_id = hacer_login(driver, wait)

        # 2. Navegar a backups y obtener tabla
        filas = navegar_a_backups(driver, wait, session_id)

        # 3. Obtener presigned URL del backup más reciente
        presigned_url, nombre_archivo = obtener_presigned_url(filas)

        # 4. Ya no necesitamos el navegador
        driver.quit()

        # 5. Descargar directamente desde S3
        archivo_tmp = descargar_desde_s3(presigned_url, nombre_archivo, carpeta_tmp)

        # 6. Mover a destino final
        ruta_final = mover_a_destino(archivo_tmp, destino, nombre_archivo)

        log.info(f"✅ Éxito — backup guardado en: {ruta_final}")

        with open("ultimo_bak.txt", "w") as f:
            f.write(str(ruta_final))

    except Exception as e:
        log.error(f"❌ Error: {e}")
        try:
            driver.save_screenshot("error_screenshot.png")
            log.info("Captura guardada: error_screenshot.png")
        except Exception:
            pass
        raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
