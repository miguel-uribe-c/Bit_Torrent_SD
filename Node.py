import json
from flask import Flask, jsonify, send_file, request
import threading
import time
import requests
import os
import sys

def listar_archivos_locales():
    print("\n" + "="*50)
    print("ARCHIVOS LOCALES EN ESTE PEER")
    print("="*50)
    
    archivos = []
    segmentos = []
    
    for item in os.listdir('.'):
        if os.path.isfile(item) and not item.endswith('.py'):
            archivos.append(item)
        elif os.path.isdir(item) and item.endswith("Segment"):
            segmentos.append(item)
    
    if not archivos and not segmentos:
        print("No hay archivos en este peer.")
        return
    
    if archivos:
        print("\nArchivos completos:")
        for a in archivos:
            print(f"  • {a} ({os.path.getsize(a)} bytes)")
    
    if segmentos:
        print("\nArchivos fragmentados:")
        for s in segmentos:
            files_in_dir = os.listdir(s)
            print(f"  • {s.replace('Segment', '')} - {len(files_in_dir)} fragmentos")
    
    print("="*50)

app = Flask(__name__)
print(f"\n[Node] Iniciando nodo en IP: 192.168.1.64:5001")

@app.route('/downloadFile', methods=['POST'])
def download_file():
    try:
        if not request.is_json:
            return jsonify({"error": "La solicitud debe contener datos en formato JSON"}), 400
        
        data = request.get_json()
        fileName = data.get("fileName")
        segmentNumber = data.get("segmentNumber")
        
        print(f"\n[Node] Solicitud de descarga de fragmento")
        print(f"[Node] Archivo: {fileName}, Segmento: {segmentNumber}")
        
        if not fileName or not isinstance(fileName, str):
            return jsonify({"error": "Campo 'fileName' inválido"}), 400
        
        if segmentNumber is None or not isinstance(segmentNumber, int) or segmentNumber < 0:
            return jsonify({"error": "Campo 'segmentNumber' inválido"}), 400
        
        if ".." in fileName or "/" in fileName:
            return jsonify({"error": "Nombre de archivo inválido"}), 400
        
        segment_dir = fileName + "Segment"
        
        if not os.path.exists(segment_dir):
            print(f"[Node] ERROR: Directorio {segment_dir} no existe")
            return jsonify({"error": "El archivo no existe en este peer"}), 404
        
        file_path = os.path.join(segment_dir, f"fragment_{segmentNumber}.part")
        
        if not os.path.exists(file_path):
            print(f"[Node] ERROR: Fragmento {segmentNumber} no encontrado en {segment_dir}")
            return jsonify({"error": "El fragmento no existe"}), 404
        
        print(f"[Node] Enviando fragmento: {file_path}")
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        print(f"[Node] Error en download_file: {e}")
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
                fragmento = archivo.read(10240)  # 10KB por fragmento
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
            "currentSegments": fragments  # Tiene todos los segmentos
        })
    
    return currentFragments

def clientTask():
    exit = False
    currentFragments = []
    
    deviceIp = "192.168.1.64"
    print(f"\n[Node] IP del nodo: {deviceIp}")
    print(f"[Node] Tracker en: 192.168.1.68:5000")
    
    # Verificar conexión con tracker
    try:
        print("[Node] Probando conexión con tracker...")
        response = requests.get("http://192.168.1.68:5000/peers", timeout=5)
        print(f"[Node] Conexión exitosa con tracker: {response.status_code}")
    except Exception as e:
        print(f"[Node] ERROR: No se puede conectar al tracker: {e}")
        print("[Node] Verifica que el tracker esté ejecutándose y la IP sea correcta")
        return
    
    # Unirse a la red
    payload = {
        "IP": deviceIp,
        "Files": currentFragments
    }
    
    try:
        response = requests.post("http://192.168.1.68:5000/enterNetwork", json=payload)
        if response.status_code == 201:
            print("[Node] Unido exitosamente a la red P2P")
        else:
            print(f"[Node] Respuesta del tracker: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Node] Error al unirse a la red: {e}")
    
    while not exit:
        print("\n" + "="*50)
        print("MENÚ PRINCIPAL - PEER P2P")
        print("="*50)
        print("1) Agregar un archivo a la red")
        print("2) Descargar un archivo de la red")
        print("3) Ver archivos locales del peer")
        print("4) Ver archivos disponibles en la red")
        print("5) Salir del sistema")
        print("="*50)
        
        select = input("\nSeleccione una opción: ")
        
        if select == "1":
            print("\n[Node] AGREGAR ARCHIVO A LA RED")
            print("Archivos disponibles localmente:")
            
            local_files = [f for f in os.listdir('.') if os.path.isfile(f) and not f.endswith('.py')]
            for i, f in enumerate(local_files, 1):
                print(f"  {i}) {f} ({os.path.getsize(f)} bytes)")
            
            if not local_files:
                print("  No hay archivos disponibles para compartir")
                continue
            
            file_input = input("\nIngresa el nombre del archivo a compartir (o número de la lista): ")
            
            try:
                # Si ingresó un número
                if file_input.isdigit():
                    idx = int(file_input) - 1
                    if 0 <= idx < len(local_files):
                        filesList = [local_files[idx]]
                    else:
                        print("[Node] ERROR: Número inválido")
                        continue
                else:
                    filesList = [file_input.strip()]
                
                print(f"[Node] Procesando archivo(s): {filesList}")
                
                # Segmentar archivo
                currentFragments = segmentFile(filesList)
                
                if not currentFragments:
                    print("[Node] ERROR: No se pudieron segmentar los archivos")
                    continue
                
                # Enviar al tracker
                newFiles = {"addedFiles": currentFragments}
                print(f"[Node] Enviando al tracker: {newFiles}")
                
                response = requests.put(f"http://192.168.1.68:5000/addFile/{deviceIp}", json=newFiles)
                
                if response.status_code == 200:
                    print("[Node] ✓ Archivo agregado exitosamente a la red")
                    print(f"[Node] Respuesta del tracker: {response.json()}")
                else:
                    print(f"[Node] ERROR: {response.status_code} - {response.text}")
                    
            except Exception as e:
                print(f"[Node] Error al agregar archivo: {e}")
                import traceback
                traceback.print_exc()
                
        elif select == "2":
            print("\n[Node] DESCARGAR ARCHIVO DE LA RED")
            
            try:
                # Obtener lista de archivos disponibles
                response = requests.get("http://192.168.1.68:5000/allFiles")
                
                if response.status_code == 200:
                    available_files = response.json().get('Files', [])
                    
                    if not available_files:
                        print("[Node] No hay archivos disponibles en la red")
                        continue
                    
                    print("\nArchivos disponibles en la red:")
                    for i, file in enumerate(available_files, 1):
                        print(f"  {i}) {file}")
                    
                    file_choice = input("\nIngresa el nombre del archivo a descargar (o número): ")
                    
                    if file_choice.isdigit():
                        idx = int(file_choice) - 1
                        if 0 <= idx < len(available_files):
                            desiredFile = available_files[idx]
                        else:
                            print("[Node] ERROR: Número inválido")
                            continue
                    else:
                        desiredFile = file_choice
                    
                    if desiredFile not in available_files:
                        print(f"[Node] ERROR: El archivo '{desiredFile}' no está disponible")
                        continue
                    
                    print(f"[Node] Solicitando descarga de: {desiredFile}")
                    
                    # Solicitar descarga al tracker
                    download_request = {
                        "fileName": desiredFile,
                        "IP": deviceIp
                    }
                    
                    response = requests.post("http://192.168.1.68:5000/downloadFile", json=download_request)
                    
                    if response.status_code == 200:
                        info = response.json().get('information', {})
                        peers_list = info.get('peersAndLeechers', [])
                        
                        if not peers_list:
                            print("[Node] ERROR: No hay peers disponibles para descargar")
                            continue
                        
                        print(f"[Node] Peers disponibles para descarga: {len(peers_list)}")
                        
                        # Descargar segmentos
                        for peer in peers_list:
                            print(f"[Node] Descargando de peer {peer['IP']}")
                            print(f"[Node] Segmentos a descargar: {peer['StartingFile']} a {peer['LastFile']}")
                            
                            for i in range(peer['StartingFile'], peer['LastFile']):
                                try:
                                    segment_url = f"http://{peer['IP']}:5001/downloadFile"
                                    segment_data = {
                                        "fileName": desiredFile,
                                        "segmentNumber": i
                                    }
                                    
                                    print(f"[Node] Descargando segmento {i}...")
                                    segment_response = requests.post(segment_url, json=segment_data, timeout=10)
                                    
                                    if segment_response.status_code == 200:
                                        # Guardar segmento
                                        segment_dir = desiredFile + "Segment"
                                        os.makedirs(segment_dir, exist_ok=True)
                                        
                                        segment_path = os.path.join(segment_dir, f"fragment_{i}.part")
                                        with open(segment_path, 'wb') as f:
                                            f.write(segment_response.content)
                                        
                                        print(f"[Node] ✓ Segmento {i} guardado")
                                        
                                        # Notificar al tracker
                                        update_data = {
                                            "fileName": desiredFile,
                                            "IP": deviceIp,
                                            "currentSegments": i + 1,
                                            "numSegments": peer['numSegments'],
                                            "peerIP": peer['IP']
                                        }
                                        
                                        requests.post("http://192.168.1.68:5000/updatePeers", json=update_data)
                                        
                                    else:
                                        print(f"[Node] ERROR en segmento {i}: {segment_response.status_code}")
                                        
                                except Exception as e:
                                    print(f"[Node] Error al descargar segmento {i}: {e}")
                        
                        # Reconstruir archivo
                        print(f"[Node] Reconstruyendo archivo {desiredFile}...")
                        segment_dir = desiredFile + "Segment"
                        
                        if os.path.exists(segment_dir):
                            fragments = sorted(
                                [os.path.join(segment_dir, f) for f in os.listdir(segment_dir) if f.startswith('fragment_')],
                                key=lambda x: int(os.path.basename(x).split('_')[1].split('.')[0])
                            )
                            
                            if fragments:
                                with open(desiredFile, 'wb') as output_file:
                                    for fragment in fragments:
                                        with open(fragment, 'rb') as f:
                                            output_file.write(f.read())
                                
                                print(f"[Node] ✓ Archivo reconstruido: {desiredFile} ({os.path.getsize(desiredFile)} bytes)")
                            else:
                                print("[Node] ERROR: No se encontraron fragmentos")
                        else:
                            print("[Node] ERROR: No se pudo reconstruir el archivo")
                            
                    else:
                        print(f"[Node] ERROR en solicitud de descarga: {response.status_code} - {response.text}")
                        
                else:
                    print(f"[Node] ERROR al obtener archivos: {response.status_code}")
                    
            except Exception as e:
                print(f"[Node] Error en descarga: {e}")
                import traceback
                traceback.print_exc()
                
        elif select == "3":
            listar_archivos_locales()
            
        elif select == "4":
            print("\n[Node] CONSULTANDO ARCHIVOS DISPONIBLES EN LA RED")
            try:
                response = requests.get("http://192.168.1.68:5000/allFiles")
                if response.status_code == 200:
                    files = response.json().get('Files', [])
                    if files:
                        print("\nArchivos disponibles en la red P2P:")
                        for file in files:
                            print(f"  • {file}")
                    else:
                        print("No hay archivos en la red")
                else:
                    print(f"Error: {response.status_code}")
            except Exception as e:
                print(f"Error: {e}")
                
        elif select == "5":
            print("\n[Node] Cerrando peer correctamente...")
            exit = True
            os._exit(0)

if __name__ == "__main__":
    print("\n" + "="*50)
    print("INICIANDO NODO P2P - UBUNTU")
    print(f"IP: 192.168.1.64")
    print(f"Puerto: 5001")
    print("="*50)
    
    # Iniciar servidor en segundo plano
    server_thread = threading.Thread(
        target=app.run,
        kwargs={'host': '192.168.1.64', 'port': 5001, 'debug': False, 'threaded': True}
    )
    server_thread.daemon = True
    server_thread.start()
    
    # Esperar un momento para que el servidor inicie
    time.sleep(2)
    
    # Ejecutar interfaz de usuario
    clientTask()
