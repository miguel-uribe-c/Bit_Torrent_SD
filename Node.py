import json
from flask import Flask, jsonify, send_file, request
import threading
import time
import requests
import os
import sys
import signal
from pathlib import Path

def listar_archivos_locales():
    print("\n" + "="*50)
    print("ARCHIVOS LOCALES EN ESTE PEER")
    print("="*50)
    
    archivos = []
    segmentos = []
    
    for item in os.listdir('.'):
        if os.path.isfile(item) and not item.endswith('.py') and not item.endswith('.json'):
            archivos.append(item)
        elif os.path.isdir(item) and item.endswith("Segment"):
            segmentos.append(item)
    
    if not archivos and not segmentos:
        print("No hay archivos en este peer.")
        return archivos, segmentos
    
    if archivos:
        print("\nArchivos completos:")
        for i, a in enumerate(archivos, 1):
            size = os.path.getsize(a) if os.path.exists(a) else 0
            print(f"  {i}) {a} ({size} bytes)")
    
    if segmentos:
        print("\nArchivos fragmentados:")
        for i, s in enumerate(segmentos, 1):
            if os.path.exists(s):
                files_in_dir = [f for f in os.listdir(s) if f.startswith('fragment_')]
                file_name = s.replace('Segment', '')
                total_size = 0
                for f in files_in_dir:
                    f_path = os.path.join(s, f)
                    if os.path.exists(f_path):
                        total_size += os.path.getsize(f_path)
                print(f"  {i}) {file_name} - {len(files_in_dir)} fragmentos ({total_size} bytes)")
    
    print("="*50)
    return archivos, segmentos

app = Flask(__name__)
print(f"\n[Node] Iniciando nodo en IP: 192.168.1.64:5001")

# Variable global para controlar descargas activas
active_downloads = {}

def signal_handler(signum, frame):
    print(f"\n[Node] Señal recibida: {signum}. Guardando estado de descargas...")
    save_download_state()
    sys.exit(0)

def save_download_state():
    """Guarda el estado de las descargas en curso"""
    try:
        state = {
            'active_downloads': active_downloads,
            'timestamp': time.time()
        }
        with open('download_state.json', 'w') as f:
            json.dump(state, f)
        print("[Node] Estado de descargas guardado")
    except Exception as e:
        print(f"[Node] Error al guardar estado: {e}")

def load_download_state():
    """Carga el estado de descargas previas"""
    try:
        if os.path.exists('download_state.json'):
            with open('download_state.json', 'r') as f:
                state = json.load(f)
                return state.get('active_downloads', {})
    except Exception as e:
        print(f"[Node] Error al cargar estado: {e}")
    return {}

# ✅ 3️⃣ AGREGA ESTA FUNCIÓN (DEBAJO DE load_download_state())
def sync_local_fragments(filename):
    """Sincroniza fragmentos locales con el tracker"""
    segment_dir = filename + "Segment"
    if not os.path.exists(segment_dir):
        return

    fragments = []
    for f in os.listdir(segment_dir):
        if f.startswith("fragment_") and f.endswith(".part"):
            try:
                fragments.append(int(f.split("_")[1].split(".")[0]))
            except:
                pass

    if filename in active_downloads:
        payload = {
            "IP": "192.168.1.64",
            "fileName": filename,
            "fragments": sorted(fragments),
            "total_segments": active_downloads[filename]["total_segments"]
        }

        try:
            requests.post("http://192.168.1.68:5000/syncFragments",
                          json=payload, timeout=5)
            print(f"[Node] Fragmentos sincronizados con tracker ({len(fragments)})")
        except:
            print("[Node] No se pudo sincronizar con tracker")

@app.route('/downloadFile', methods=['POST'])
def download_file():
    try:
        if not request.is_json:
            return jsonify({"error": "La solicitud debe contener datos en formato JSON"}), 400
        
        data = request.get_json()
        fileName = data.get("fileName")
        segmentNumber = data.get("segmentNumber")
        
        if not fileName or not isinstance(fileName, str):
            return jsonify({"error": "Campo 'fileName' inválido"}), 400
        
        if segmentNumber is None or not isinstance(segmentNumber, int) or segmentNumber < 0:
            return jsonify({"error": "Campo 'segmentNumber' inválido"}), 400
        
        if ".." in fileName or "/" in fileName:
            return jsonify({"error": "Nombre de archivo inválido"}), 400
        
        segment_dir = fileName + "Segment"
        
        if not os.path.exists(segment_dir):
            return jsonify({"error": "El archivo no existe en este peer"}), 404
        
        file_path = os.path.join(segment_dir, f"fragment_{segmentNumber}.part")
        
        if not os.path.exists(file_path):
            return jsonify({"error": "El fragmento no existe"}), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

def segmentFile(filesList):
    print(f"\n[Node] Segmentando archivos: {filesList}")
    currentFragments = []
    
    for file in filesList:
        file = file.strip()
        if not os.path.exists(file):
            print(f"[Node] ERROR: El archivo {file} no existe")
            continue
        
        segment_dir = file + "Segment"
        
        # Limpiar directorio si ya existe
        if os.path.exists(segment_dir):
            print(f"[Node] Directorio {segment_dir} ya existe, recreando...")
            import shutil
            shutil.rmtree(segment_dir)
        
        os.makedirs(segment_dir, exist_ok=True)
        
        fragments = 0
        with open(file, 'rb') as archivo:
            while True:
                fragmento = archivo.read(10240)
                if not fragmento:
                    break
                
                ruta_fragmento = os.path.join(segment_dir, f"fragment_{fragments}.part")
                
                with open(ruta_fragmento, 'wb') as f:
                    f.write(fragmento)
                
                fragments += 1
        
        print(f"[Node] Archivo {file} segmentado en {fragments} fragmentos")
        
        currentFragments.append({
            "fileName": file,
            "numSegments": fragments,
            "currentSegments": fragments
        })
    
    return currentFragments

def reconstruct_file(filename):
    """Reconstruye el archivo desde los fragmentos"""
    try:
        segment_dir = filename + "Segment"
        
        if not os.path.exists(segment_dir):
            print(f"[Node] ERROR: No existe directorio para {filename}")
            return False
        
        # Obtener todos los fragmentos
        fragments = []
        for f in os.listdir(segment_dir):
            if f.startswith('fragment_') and f.endswith('.part'):
                try:
                    segment_num = int(f.split('_')[1].split('.')[0])
                    fragments.append((segment_num, os.path.join(segment_dir, f)))
                except:
                    pass
        
        if not fragments:
            print(f"[Node] ERROR: No hay fragmentos para {filename}")
            return False
        
        # ✅ 5️⃣ BLOQUEA RECONSTRUCCIÓN INCOMPLETA
        # Verificar que tenemos todos los fragmentos esperados
        if filename in active_downloads:
            total_segments = active_downloads[filename].get("total_segments", 0)
            if total_segments > 0:
                expected = set(range(total_segments))
                actual = set([x[0] for x in fragments])
                
                if expected != actual:
                    print(f"[Node] ❌ Archivo incompleto, no se puede reconstruir")
                    print(f"[Node] Faltan fragmentos: {sorted(expected - actual)}")
                    return False
        
        # Ordenar por número de fragmento
        fragments.sort(key=lambda x: x[0])
        
        # Reconstruir archivo
        print(f"[Node] Reconstruyendo {filename} con {len(fragments)} fragmentos...")
        
        with open(filename, 'wb') as output_file:
            for segment_num, fragment_path in fragments:
                with open(fragment_path, 'rb') as f:
                    output_file.write(f.read())
        
        file_size = os.path.getsize(filename)
        print(f"[Node] ✓ Archivo reconstruido: {filename} ({file_size} bytes)")
        
        # Notificar al tracker que la descarga está completa
        try:
            complete_data = {
                "IP": "192.168.1.64",
                "fileName": filename
            }
            requests.post("http://192.168.1.68:5000/completeDownload", 
                         json=complete_data, timeout=5)
        except:
            print("[Node] No se pudo notificar al tracker")
        
        # Eliminar del registro de descargas activas
        if filename in active_downloads:
            del active_downloads[filename]
        save_download_state()
        
        return True
        
    except Exception as e:
        print(f"[Node] Error al reconstruir archivo: {e}")
        return False

def check_download_complete(filename):
    """Verifica si todos los fragmentos están presentes para un archivo"""
    try:
        segment_dir = filename + "Segment"
        
        if not os.path.exists(segment_dir):
            return False
        
        # Buscar información del tracker sobre el archivo
        try:
            response = requests.get("http://192.168.1.68:5000/allFiles", timeout=5)
            if response.status_code == 200:
                # Obtener información de peers para conocer el total de segmentos
                peers_response = requests.get("http://192.168.1.68:5000/peers", timeout=5)
                if peers_response.status_code == 200:
                    peers = peers_response.json()
                    for peer in peers:
                        for file_info in peer.get("Files", []):
                            if file_info.get("fileName") == filename:
                                total_segments = file_info.get("numSegments", 0)
                                
                                # Contar fragmentos locales
                                local_fragments = []
                                for f in os.listdir(segment_dir):
                                    if f.startswith('fragment_') and f.endswith('.part'):
                                        try:
                                            num = int(f.split('_')[1].split('.')[0])
                                            local_fragments.append(num)
                                        except:
                                            pass
                                
                                # Verificar si tenemos todos los fragmentos
                                if total_segments > 0 and len(local_fragments) >= total_segments:
                                    # Verificar que sean consecutivos desde 0
                                    local_fragments.sort()
                                    if local_fragments == list(range(total_segments)):
                                        return True
        except:
            pass
        
        return False
        
    except Exception as e:
        print(f"[Node] Error en check_download_complete: {e}")
        return False

def resume_interrupted_downloads():
    """Reanuda descargas interrumpidas"""
    global active_downloads
    
    try:
        # Cargar estado previo
        active_downloads = load_download_state()
        
        if active_downloads:
            print(f"\n[Node] Descargas interrumpidas encontradas: {len(active_downloads)}")
            
            # ✅ 4️⃣ MODIFICA resume_interrupted_downloads()
            for filename, download_info in list(active_downloads.items()):
                # Sincronizar fragmentos locales con el tracker
                sync_local_fragments(filename)
                
                print(f"\n[Node] Intentando reanudar: {filename}")
                
                # Verificar si ya está completo
                if check_download_complete(filename):
                    print(f"[Node] {filename} ya está completo, reconstruyendo...")
                    if reconstruct_file(filename):
                        print(f"[Node] ✓ Reconstrucción exitosa")
                        if filename in active_downloads:
                            del active_downloads[filename]
                    continue
                
                # Solicitar reanudación al tracker
                try:
                    resume_data = {
                        "IP": "192.168.1.64",
                        "fileName": filename
                    }
                    
                    response = requests.post("http://192.168.1.68:5000/resumeDownload",
                                           json=resume_data, timeout=10)
                    
                    if response.status_code == 200:
                        resume_info = response.json()
                        
                        if resume_info.get('status') == 'resume_available':
                            print(f"[Node] Reanudación disponible para {filename}")
                            print(f"[Node] Segmentos descargados: {resume_info.get('downloaded_segments', [])}")
                            print(f"[Node] Segmentos faltantes: {resume_info.get('missing_segments', [])}")
                            
                            # Iniciar descarga de segmentos faltantes
                            download_missing_segments(filename, resume_info)
                        else:
                            print(f"[Node] No se puede reanudar {filename}: {resume_info.get('status')}")
                    else:
                        print(f"[Node] Error al solicitar reanudación: {response.status_code}")
                        
                except Exception as e:
                    print(f"[Node] Error al reanudar {filename}: {e}")
        
        # Limpiar archivo de estado
        if os.path.exists('download_state.json'):
            try:
                os.remove('download_state.json')
            except:
                pass
                
    except Exception as e:
        print(f"[Node] Error en resume_interrupted_downloads: {e}")

def download_missing_segments(filename, resume_info):
    """Descarga los segmentos faltantes de una descarga interrumpida"""
    try:
        deviceIp = "192.168.1.64"
        missing_segments = resume_info.get('missing_segments', [])
        peers = resume_info.get('peers', [])
        
        if not missing_segments:
            print(f"[Node] No hay segmentos faltantes para {filename}")
            return True
        
        if not peers:
            print(f"[Node] No hay peers disponibles para {filename}")
            return False
        
        print(f"[Node] Descargando {len(missing_segments)} segmentos faltantes...")
        
        segment_dir = filename + "Segment"
        os.makedirs(segment_dir, exist_ok=True)
        
        # Registrar descarga activa
        active_downloads[filename] = {
            "start_time": time.time(),
            "total_segments": resume_info.get('total_segments', 0)
        }
        save_download_state()
        
        # Descargar cada segmento faltante
        downloaded_count = 0
        for segment in missing_segments:
            # ✅ 6️⃣ EVITA REDESCARGAR FRAGMENTOS EXISTENTES
            segment_path = os.path.join(segment_dir, f"fragment_{segment}.part")
            if os.path.exists(segment_path):
                print(f"[Node] Segmento {segment} ya existe, saltando")
                continue
            
            # Encontrar un peer que pueda proveer este segmento
            for peer in peers:
                segments_to_download = peer.get('segments_to_download', [])
                if segment in segments_to_download:
                    try:
                        segment_url = f"http://{peer['IP']}:5001/downloadFile"
                        segment_data = {
                            "fileName": filename,
                            "segmentNumber": segment
                        }
                        
                        print(f"[Node] Descargando segmento {segment} de {peer['IP']}...")
                        response = requests.post(segment_url, json=segment_data, timeout=30)
                        
                        if response.status_code == 200:
                            # Guardar segmento
                            with open(segment_path, 'wb') as f:
                                f.write(response.content)
                            
                            print(f"[Node] ✓ Segmento {segment} guardado")
                            downloaded_count += 1
                            
                            # Actualizar progreso en tracker
                            update_progress = {
                                "IP": deviceIp,
                                "fileName": filename,
                                "segment": segment,
                                "total_segments": resume_info.get('total_segments', 0)
                            }
                            
                            try:
                                requests.post("http://192.168.1.68:5000/updateDownloadProgress",
                                            json=update_progress, timeout=5)
                            except:
                                pass
                            
                            break  # Segmento descargado, pasar al siguiente
                        else:
                            print(f"[Node] Error en segmento {segment}: {response.status_code}")
                            
                    except Exception as e:
                        print(f"[Node] Error al descargar segmento {segment}: {e}")
                        continue
        
        print(f"[Node] Descargados {downloaded_count}/{len(missing_segments)} segmentos faltantes")
        
        # Verificar si ahora está completo
        if check_download_complete(filename):
            print(f"[Node] ¡Todos los segmentos descargados! Reconstruyendo...")
            if reconstruct_file(filename):
                return True
            else:
                print(f"[Node] Error al reconstruir archivo después de descarga")
                return False
        else:
            print(f"[Node] Descarga parcial completada. Faltan segmentos.")
            return False
            
    except Exception as e:
        print(f"[Node] Error en download_missing_segments: {e}")
        return False

def download_file_normal(filename, download_info):
    """Descarga un archivo desde cero"""
    try:
        deviceIp = "192.168.1.64"
        peers_list = download_info.get('peersAndLeechers', [])
        
        if not peers_list:
            print(f"[Node] ERROR: No hay peers disponibles para {filename}")
            return False
        
        print(f"[Node] Descargando {filename} de {len(peers_list)} peer(s)")
        
        segment_dir = filename + "Segment"
        os.makedirs(segment_dir, exist_ok=True)
        
        # Registrar descarga activa
        active_downloads[filename] = {
            "start_time": time.time(),
            "total_segments": peers_list[0]['numSegments'] if peers_list else 0
        }
        save_download_state()
        
        # Descargar todos los segmentos
        for peer in peers_list:
            print(f"[Node] Descargando de peer {peer['IP']}")
            print(f"[Node] Rango: {peer['StartingFile']} a {peer['LastFile']}")
            
            for segment in range(peer['StartingFile'], peer['LastFile']):
                # Verificar si el segmento ya existe
                segment_path = os.path.join(segment_dir, f"fragment_{segment}.part")
                if os.path.exists(segment_path):
                    print(f"[Node] Segmento {segment} ya existe, saltando")
                    continue
                
                try:
                    segment_url = f"http://{peer['IP']}:5001/downloadFile"
                    segment_data = {
                        "fileName": filename,
                        "segmentNumber": segment
                    }
                    
                    print(f"[Node] Descargando segmento {segment}...")
                    response = requests.post(segment_url, json=segment_data, timeout=30)
                    
                    if response.status_code == 200:
                        # Guardar segmento
                        with open(segment_path, 'wb') as f:
                            f.write(response.content)
                        
                        print(f"[Node] ✓ Segmento {segment} guardado")
                        
                        # Actualizar progreso en tracker
                        update_progress = {
                            "IP": deviceIp,
                            "fileName": filename,
                            "segment": segment,
                            "total_segments": peer['numSegments']
                        }
                        
                        try:
                            requests.post("http://192.168.1.68:5000/updateDownloadProgress",
                                        json=update_progress, timeout=5)
                        except:
                            pass
                        
                    else:
                        print(f"[Node] Error en segmento {segment}: {response.status_code}")
                        
                except Exception as e:
                    print(f"[Node] Error al descargar segmento {segment}: {e}")
                    continue
        
        # Verificar si la descarga está completa
        if check_download_complete(filename):
            print(f"[Node] ✓ Todos los fragmentos descargados para {filename}")
            if reconstruct_file(filename):
                return True
            else:
                print(f"[Node] ✗ Error al reconstruir archivo")
                return False
        else:
            print(f"[Node] ✗ La descarga no se completó totalmente")
            return False
            
    except Exception as e:
        print(f"[Node] Error en download_file_normal: {e}")
        return False

def clientTask():
    global active_downloads
    
    exit_flag = False
    currentFragments = []
    deviceIp = "192.168.1.64"
    
    print(f"\n[Node] IP del nodo: {deviceIp}")
    print(f"[Node] Tracker en: 192.168.1.68:5000")
    
    # Configurar manejo de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Reanudar descargas interrumpidas
    resume_interrupted_downloads()
    
    # Verificar conexión con tracker
    try:
        print("[Node] Probando conexión con tracker...")
        response = requests.get("http://192.168.1.68:5000/peers", timeout=5)
        if response.status_code == 200:
            print(f"[Node] ✓ Conexión exitosa con tracker")
        else:
            print(f"[Node] ✗ Error del tracker: {response.status_code}")
    except Exception as e:
        print(f"[Node] ✗ No se puede conectar al tracker: {e}")
    
    # Unirse a la red
    payload = {
        "IP": deviceIp,
        "Files": currentFragments
    }
    
    try:
        response = requests.post("http://192.168.1.68:5000/enterNetwork", 
                               json=payload, timeout=10)
        if response.status_code == 201:
            print("[Node] ✓ Unido exitosamente a la red P2P")
    except Exception as e:
        print(f"[Node] ✗ Error al unirse a la red: {e}")
    
    while not exit_flag:
        try:
            print("\n" + "="*50)
            print("MENÚ PRINCIPAL - PEER P2P (UBUNTU)")
            print("="*50)
            print("1) Agregar un archivo a la red")
            print("2) Descargar un archivo de la red")
            print("3) Ver archivos locales del peer")
            print("4) Ver archivos disponibles en la red")
            print("5) Reanudar descargas interrumpidas")
            print("6) Ver estado de descargas activas")
            print("7) Salir del sistema")
            print("="*50)
            
            select = input("\nSeleccione una opción: ").strip()
            
            if select == "1":
                print("\n[Node] AGREGAR ARCHIVO A LA RED")
                archivos_locales, _ = listar_archivos_locales()
                
                if not archivos_locales:
                    print("[Node] ✗ No hay archivos completos para compartir")
                    continue
                
                print("\n[Node] Seleccione el archivo por número:")
                for i, archivo in enumerate(archivos_locales, 1):
                    print(f"  {i}) {archivo}")
                
                try:
                    eleccion = input("\nOpción: ").strip()
                    
                    if eleccion.isdigit():
                        opcion = int(eleccion)
                        if 1 <= opcion <= len(archivos_locales):
                            archivo_seleccionado = archivos_locales[opcion - 1]
                        else:
                            print("[Node] ✗ Opción inválida")
                            continue
                    else:
                        archivo_seleccionado = eleccion
                        if not os.path.exists(archivo_seleccionado):
                            print(f"[Node] ✗ El archivo '{archivo_seleccionado}' no existe")
                            continue
                    
                    print(f"[Node] Procesando: {archivo_seleccionado}")
                    
                    # Segmentar archivo
                    currentFragments = segmentFile([archivo_seleccionado])
                    
                    if not currentFragments:
                        print("[Node] ✗ No se pudo segmentar el archivo")
                        continue
                    
                    # Enviar al tracker
                    newFiles = {"addedFiles": currentFragments}
                    
                    response = requests.put(f"http://192.168.1.68:5000/addFile/{deviceIp}", 
                                          json=newFiles, timeout=10)
                    
                    if response.status_code == 200:
                        print("[Node] ✓ Archivo agregado exitosamente a la red")
                    else:
                        print(f"[Node] ✗ Error del tracker: {response.status_code}")
                        
                except Exception as e:
                    print(f"[Node] ✗ Error: {e}")
                    
            elif select == "2":
                print("\n[Node] DESCARGAR ARCHIVO DE LA RED")
                
                try:
                    response = requests.get("http://192.168.1.68:5000/allFiles", timeout=5)
                    
                    if response.status_code == 200:
                        available_files = response.json().get('Files', [])
                        
                        if not available_files:
                            print("[Node] ✗ No hay archivos disponibles en la red")
                            continue
                        
                        print("\n[Node] Archivos disponibles en la red:")
                        for i, file in enumerate(available_files, 1):
                            print(f"  {i}) {file}")
                        
                        try:
                            eleccion = input("\nSeleccione archivo por número: ").strip()
                            
                            if not eleccion.isdigit():
                                print("[Node] ✗ Debe ingresar un número")
                                continue
                            
                            opcion = int(eleccion)
                            if 1 <= opcion <= len(available_files):
                                desiredFile = available_files[opcion - 1]
                            else:
                                print("[Node] ✗ Número inválido")
                                continue
                            
                            # Verificar si ya está en descarga
                            if desiredFile in active_downloads:
                                print(f"[Node] Este archivo ya se está descargando")
                                continue
                            
                            # Solicitar descarga
                            download_request = {
                                "fileName": desiredFile,
                                "IP": deviceIp
                            }
                            
                            print(f"[Node] Solicitando descarga de: {desiredFile}")
                            response = requests.post("http://192.168.1.68:5000/downloadFile", 
                                                   json=download_request, timeout=10)
                            
                            if response.status_code == 200:
                                info = response.json()
                                
                                if info.get('mode') == 'resume':
                                    print(f"[Node] Reanudando descarga existente...")
                                    success = download_missing_segments(desiredFile, info.get('information', {}))
                                else:
                                    print(f"[Node] Iniciando nueva descarga...")
                                    success = download_file_normal(desiredFile, info.get('information', {}))
                                
                                if success:
                                    print(f"[Node] ✓ Descarga completada: {desiredFile}")
                                else:
                                    print(f"[Node] ✗ La descarga no se completó")
                            else:
                                print(f"[Node] ✗ Error en solicitud: {response.status_code}")
                                
                        except Exception as e:
                            print(f"[Node] ✗ Error: {e}")
                            
                    else:
                        print(f"[Node] ✗ Error del tracker: {response.status_code}")
                        
                except Exception as e:
                    print(f"[Node] ✗ Error en descarga: {e}")
                    
            elif select == "3":
                listar_archivos_locales()
                
            elif select == "4":
                print("\n[Node] CONSULTANDO ARCHIVOS DISPONIBLES EN LA RED")
                try:
                    response = requests.get("http://192.168.1.68:5000/allFiles", timeout=5)
                    if response.status_code == 200:
                        files = response.json().get('Files', [])
                        if files:
                            print("\n[Node] Archivos disponibles en la red P2P:")
                            for i, file in enumerate(files, 1):
                                print(f"  {i}) {file}")
                        else:
                            print("[Node] ✗ No hay archivos en la red")
                    else:
                        print(f"[Node] ✗ Error: {response.status_code}")
                except Exception as e:
                    print(f"[Node] ✗ Error: {e}")
                    
            elif select == "5":
                print("\n[Node] REANUDANDO DESCARGAS INTERRUMPIDAS")
                resume_interrupted_downloads()
                
            elif select == "6":
                print("\n[Node] ESTADO DE DESCARGAS ACTIVAS")
                if active_downloads:
                    for filename, info in active_downloads.items():
                        segment_dir = filename + "Segment"
                        if os.path.exists(segment_dir):
                            fragments = [f for f in os.listdir(segment_dir) if f.startswith('fragment_')]
                            print(f"  • {filename}: {len(fragments)} fragmentos descargados")
                else:
                    print("  [Node] No hay descargas activas")
                    
            elif select == "7":
                print("\n[Node] Cerrando peer correctamente...")
                
                # Guardar estado final
                save_download_state()
                
                exit_flag = True
                os._exit(0)
                
        except KeyboardInterrupt:
            print("\n[Node] Interrupción por teclado detectada")
            save_download_state()
            continue
        except Exception as e:
            print(f"[Node] ✗ Error en el menú: {e}")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("INICIANDO NODO P2P - UBUNTU")
    print("Con reanudación mejorada y sincronización")
    print(f"IP: 192.168.1.64")
    print(f"Puerto: 5001")
    print("="*50)
    
    # Iniciar servidor en segundo plano
    server_thread = threading.Thread(
        target=app.run,
        kwargs={'host': '192.168.1.64', 'port': 5001, 'debug': False, 'threaded': True},
        daemon=True
    )
    server_thread.start()
    
    # Esperar a que el servidor inicie
    time.sleep(2)
    
    # Ejecutar interfaz de usuario
    clientTask()
