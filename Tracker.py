import json
from collections import Counter
from flask import Flask, jsonify, request
import time

app = Flask(__name__)

# Arreglo que guarda todos los nodos pertenecientes a la red
peers = []

# Solicitudes pendientes de descargas
pendingRequests = []

# Registro de progreso de descargas por IP y archivo
download_progress = {}

print("=== INICIANDO TRACKER EN IP: 192.168.1.68:5000 ===")

# Servicio para que un nodo entre a la red
@app.route('/enterNetwork', methods=['POST'])
def enterNetwork():
    try:
        potencialPeer = request.get_json()
        print(f"\n[Tracker] Solicitud de entrada a la red desde IP: {potencialPeer.get('IP')}")
        
        registredIP = [peer["IP"] for peer in peers]
        
        if potencialPeer['IP'] in registredIP:
            print(f"[Tracker] IP {potencialPeer['IP']} ya existe en la red")
            return jsonify({'location': 'Nodo ya perteneciente a la red bitTorrent'}), 200
        
        # Si no es así, agregalo al arreglo de peers
        peers.append(potencialPeer)
        print(f"[Tracker] Peer {potencialPeer['IP']} agregado exitosamente")
        print(f"[Tracker] Archivos que reporta: {potencialPeer.get('Files', [])}")
        print(f"[Tracker] Total de peers en red: {len(peers)}")

        return jsonify({'location': 'Se ha agregado su nodo a la red.'}), 201
    except Exception as e:
        print(f"[Tracker] Error en enterNetwork: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio para verificar y reanudar descargas pendientes
@app.route('/resumeDownload', methods=['POST'])
def resumeDownload():
    try:
        data = request.get_json()
        ip = data.get("IP")
        filename = data.get("fileName")
        
        print(f"\n[Tracker] Solicitud de reanudación para {ip} - Archivo: {filename}")
        
        # Buscar si hay progreso guardado para esta descarga
        progress_key = f"{ip}_{filename}"
        
        if progress_key in download_progress:
            progress = download_progress[progress_key]
            downloaded_segments = sorted(progress.get("downloaded_segments", []))
            total_segments = progress.get("total_segments", 0)
            
            print(f"[Tracker] Progreso encontrado: {len(downloaded_segments)}/{total_segments} segmentos")
            
            # Verificar qué segmentos faltan
            all_segments = set(range(total_segments))
            downloaded_set = set(downloaded_segments)
            missing_segments = sorted(list(all_segments - downloaded_set))
            
            print(f"[Tracker] Segmentos faltantes: {missing_segments}")
            
            # Buscar peers que tengan el archivo
            availablePeers = []
            for peer in peers:
                for file in peer.get("Files", []):
                    if file["fileName"] == filename and file["currentSegments"] / file["numSegments"] >= 0.2:
                        availablePeers.append({
                            "IP": peer["IP"],
                            "currentSegments": file["currentSegments"],
                            "numSegments": file["numSegments"]
                        })
            
            if availablePeers and missing_segments:
                # Ordenar peers por segmentos disponibles
                availablePeers = sorted(availablePeers, key=lambda x: x["currentSegments"])
                
                # Distribuir segmentos faltantes entre los peers disponibles
                # Primero, agrupar segmentos faltantes por rango
                segments_to_download = missing_segments
                
                # Asignar segmentos a peers
                assigned_segments = {}
                for i, peer in enumerate(availablePeers):
                    assigned_segments[peer["IP"]] = []
                
                # Distribuir segmentos equitativamente
                for idx, segment in enumerate(segments_to_download):
                    peer_idx = idx % len(availablePeers)
                    peer_ip = availablePeers[peer_idx]["IP"]
                    assigned_segments[peer_ip].append(segment)
                
                # Crear lista de peers con sus segmentos asignados
                peers_with_assignments = []
                for peer in availablePeers:
                    if assigned_segments[peer["IP"]]:
                        segments = sorted(assigned_segments[peer["IP"]])
                        peers_with_assignments.append({
                            "IP": peer["IP"],
                            "numSegments": peer["numSegments"],
                            "segments_to_download": segments,
                            "total_assigned": len(segments)
                        })
                
                if peers_with_assignments:
                    return jsonify({
                        'status': 'resume_available',
                        'filename': filename,
                        'downloaded_segments': downloaded_segments,
                        'missing_segments': missing_segments,
                        'total_segments': total_segments,
                        'peers': peers_with_assignments
                    }), 200
        
        return jsonify({'status': 'no_resume_data'}), 200
        
    except Exception as e:
        print(f"[Tracker] Error en resumeDownload: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que actualiza el progreso de descarga
@app.route('/updateDownloadProgress', methods=['POST'])
def updateDownloadProgress():
    try:
        data = request.get_json()
        ip = data.get("IP")
        filename = data.get("fileName")
        segment = data.get("segment")
        total_segments = data.get("total_segments")
        
        progress_key = f"{ip}_{filename}"
        
        if progress_key not in download_progress:
            download_progress[progress_key] = {
                "ip": ip,
                "filename": filename,
                "total_segments": total_segments,
                "downloaded_segments": [],
                "last_update": time.time()
            }
        
        # Agregar segmento a la lista si no existe
        if segment not in download_progress[progress_key]["downloaded_segments"]:
            download_progress[progress_key]["downloaded_segments"].append(segment)
            download_progress[progress_key]["last_update"] = time.time()
            print(f"[Tracker] Progreso actualizado para {progress_key}: Segmento {segment}")
        
        return jsonify({'status': 'progress_updated'}), 200
        
    except Exception as e:
        print(f"[Tracker] Error en updateDownloadProgress: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que elimina progreso de descarga completada
@app.route('/completeDownload', methods=['POST'])
def completeDownload():
    try:
        data = request.get_json()
        ip = data.get("IP")
        filename = data.get("fileName")
        
        progress_key = f"{ip}_{filename}"
        
        if progress_key in download_progress:
            del download_progress[progress_key]
            print(f"[Tracker] Progreso eliminado para {progress_key}")
        
        return jsonify({'status': 'download_completed'}), 200
        
    except Exception as e:
        print(f"[Tracker] Error en completeDownload: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que verifica descargas pendientes
@app.route('/verifyPendingDownloads', methods=["POST"])
def verifyPendingDownloads():
    try:
        peerInfo = request.get_json()
        ip = peerInfo.get("IP")
        
        print(f"\n[Tracker] Verificando descargas pendientes para IP: {ip}")
        
        # Buscar progresos guardados
        progress_keys = [key for key in download_progress.keys() if key.startswith(f"{ip}_")]
        progress_list = []
        
        for key in progress_keys:
            progress = download_progress[key]
            downloaded = len(progress["downloaded_segments"])
            total = progress["total_segments"]
            progress_percent = (downloaded / total * 100) if total > 0 else 0
            progress_list.append({
                "fileName": progress["filename"],
                "downloaded_segments": downloaded,
                "total_segments": total,
                "progress_percent": progress_percent
            })
        
        if not progress_list:
            print(f"[Tracker] No hay descargas pendientes para {ip}")
            return jsonify({'message': 'No hay descargas pendientes.'}), 200
        
        response_data = {
            'message': 'Hay descargas pendientes.',
            'pending_downloads': progress_list
        }
        
        print(f"[Tracker] Descargas pendientes encontradas: {response_data}")
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"[Tracker] Error en verifyPendingDownloads: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que agrega un archivo a la red
@app.route('/addFile/<ip>', methods=['PUT'])
def addFile(ip: str):
    try:
        print(f"\n[Tracker] Solicitud de agregar archivo desde IP: {ip}")
        
        # Busca al peer dentro del arreglo de peers
        peer = next((p for p in peers if p['IP'] == ip), None)
        if peer is None:
            print(f"[Tracker] ERROR: Peer {ip} no encontrado")
            return jsonify({'error': 'No se identificó el peer.'}), 404

        updatedFiles = request.get_json()
        print(f"[Tracker] Archivos recibidos: {updatedFiles}")

        # Segmento que ayuda a la actualización del peer
        auxDic = {file["fileName"]: file for file in peer.get("Files", [])}
        
        for file in updatedFiles.get("addedFiles", []):
            auxDic[file["fileName"]] = file
            print(f"[Tracker] Archivo agregado/actualizado: {file['fileName']} con {file['numSegments']} segmentos")
        
        peer["Files"] = list(auxDic.values())
        
        print(f"[Tracker] Archivos actualizados del peer {ip}: {peer['Files']}")
        print(f"[Tracker] Total de archivos en la red ahora: {sum(len(p.get('Files', [])) for p in peers)}")

        return jsonify({'message': 'Archivos actualizados exitosamente', 'peers': peers}), 200
    except Exception as e:
        print(f"[Tracker] Error en addFile: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que devuelve todos los archivos de la red
@app.route('/allFiles', methods=['GET'])
def showFiles():
    try:
        allFiles = set()
        for peer in peers:
            for file in peer.get("Files", []):
                allFiles.add(file["fileName"])
        
        listAllFiles = list(allFiles)
        
        print(f"\n[Tracker] Consulta de archivos disponibles. Total: {len(listAllFiles)}")
        
        return jsonify({'Files': listAllFiles}), 200
    except Exception as e:
        print(f"[Tracker] Error en showFiles: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que gestiona la descarga de un archivo
@app.route("/downloadFile", methods=["POST"])
def downloadFile():
    try:
        informationForDownload = request.get_json()
        fileName = informationForDownload.get("fileName")
        clientIP = informationForDownload.get("IP")
        
        print(f"\n[Tracker] Solicitud de descarga de: {fileName} por IP: {clientIP}")
        
        # Verificar si hay progreso previo
        progress_key = f"{clientIP}_{fileName}"
        resume_mode = False
        downloaded_segments = []
        
        if progress_key in download_progress:
            resume_mode = True
            downloaded_segments = download_progress[progress_key]["downloaded_segments"]
            print(f"[Tracker] Modo reanudación. Segmentos ya descargados: {downloaded_segments}")
        
        availablePeers = []
        
        # Buscar peers que tengan el archivo
        for peer in peers:
            for file in peer.get("Files", []):
                if file["fileName"] == fileName:
                    # Verificar si tiene al menos 20% del archivo
                    if file["currentSegments"] / file["numSegments"] >= 0.2:
                        availablePeers.append({
                            "IP": peer["IP"],
                            "currentSegments": file["currentSegments"],
                            "numSegments": file["numSegments"]
                        })
        
        if not availablePeers:
            print(f"[Tracker] ERROR: No se encontraron peers con el archivo {fileName}")
            return jsonify({'error': 'No se encontraron peers con el archivo solicitado'}), 404
        
        print(f"[Tracker] Peers disponibles para {fileName}: {len(availablePeers)}")
        
        # Ordenar peers por segmentos disponibles
        availablePeers = sorted(availablePeers, key=lambda x: x["currentSegments"])
        
        # Si es modo reanudación, asignar solo segmentos faltantes
        if resume_mode and downloaded_segments:
            total_segments = availablePeers[0]["numSegments"]
            all_segments = set(range(total_segments))
            downloaded_set = set(downloaded_segments)
            missing_segments = sorted(list(all_segments - downloaded_set))
            
            print(f"[Tracker] Segmentos a descargar en reanudación: {missing_segments}")
            
            # Distribuir segmentos faltantes entre peers
            peers_with_assignments = []
            for i, peer in enumerate(availablePeers):
                # Asignar segmentos de forma equitativa
                segments_for_this_peer = []
                for idx, segment in enumerate(missing_segments):
                    if idx % len(availablePeers) == i:
                        segments_for_this_peer.append(segment)
                
                if segments_for_this_peer:
                    peers_with_assignments.append({
                        "IP": peer["IP"],
                        "numSegments": peer["numSegments"],
                        "segments_to_download": segments_for_this_peer
                    })
            
            return jsonify({
                'Status': 'Reanudación disponible',
                'mode': 'resume',
                'information': {
                    "IP": clientIP,
                    "File2Download": fileName,
                    "peers": peers_with_assignments,
                    "downloaded_segments": downloaded_segments,
                    "total_segments": total_segments
                }
            }), 200
        
        # Modo normal (descarga completa)
        # Distribuir segmentos entre los peers disponibles
        count = Counter(peer["numSegments"] for peer in availablePeers)
        sortedSegments = sorted(count.keys())
        
        ranges = []
        start = -1
        
        for num in sortedSegments:
            occurrences = count[num]
            rangeSize = num - start
            
            if rangeSize < occurrences:
                print(f"[Tracker] ERROR: Rango insuficiente para dividir")
                return jsonify({'error': 'Error en distribución de segmentos'}), 500
            
            base_size = rangeSize // occurrences
            extra = rangeSize % occurrences
            
            for i in range(occurrences):
                end = start + base_size + (1 if i < extra else 0)
                ranges.append((start + 1, end))
                start = end
        
        range_index = 0
        for num in sortedSegments:
            for _ in range(count[num]):
                availablePeers[range_index]["StartingFile"] = ranges[range_index][0]
                availablePeers[range_index]["LastFile"] = ranges[range_index][1]
                range_index += 1
        
        # Crear copia con información de seguimiento
        availablePeers2 = availablePeers.copy()
        for peer in availablePeers2:
            peer["trackerSegment"] = peer["StartingFile"]
        
        downloadingResolution = {
            "IP": clientIP,
            "File2Download": fileName,
            "peersAndLeechers": availablePeers2
        }
        
        pendingRequests.append(downloadingResolution)
        print(f"[Tracker] Descarga programada. Peers asignados: {availablePeers}")
        
        return jsonify({
            'Status': 'Se han encontrado peers para proveer el archivo.',
            'mode': 'new',
            'information': {
                "IP": clientIP,
                "File2Download": fileName,
                "peersAndLeechers": availablePeers
            }
        }), 200
        
    except Exception as e:
        print(f"[Tracker] Error en downloadFile: {e}")
        return jsonify({'error': str(e)}), 500

# Servicio que actualiza la información de los peers
@app.route('/updatePeers', methods=["POST"])
def updatePeers():
    try:
        newPeerInfo = request.get_json()
        
        # Buscar el peer
        peer = next((p for p in peers if newPeerInfo['IP'] == p["IP"]), None)
        if peer is None:
            return jsonify({'error': 'No se identificó el peer.'}), 404
        
        # Buscar el archivo en el peer
        file = next((f for f in peer.get("Files", []) if f["fileName"] == newPeerInfo["fileName"]), None)
        
        if file is None:
            # Si no existe, agregarlo
            peer.setdefault("Files", []).append({
                "fileName": newPeerInfo["fileName"],
                "numSegments": newPeerInfo["numSegments"],
                "currentSegments": newPeerInfo["currentSegments"]
            })
        else:
            # Si existe, actualizar segmentos
            file["currentSegments"] = newPeerInfo["currentSegments"]
        
        return jsonify({'message': 'Se ha actualizado el estatus del peer.'}), 200
    except Exception as e:
        print(f"[Tracker] Error en updatePeers: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pendingDownloads', methods=["GET"])
def pendingDownloads():
    return jsonify(pendingRequests)

@app.route('/peers', methods=['GET'])
def getPeers():
    return jsonify(peers)
# Servicio para sincronizar fragmentos locales
@app.route('/syncFragments', methods=['POST'])
def syncFragments():
    try:
        data = request.get_json()
        ip = data.get("IP")
        filename = data.get("fileName")
        fragments = data.get("fragments", [])
        total_segments = data.get("total_segments", 0)
        
        progress_key = f"{ip}_{filename}"
        
        if progress_key not in download_progress:
            download_progress[progress_key] = {
                "ip": ip,
                "filename": filename,
                "total_segments": total_segments,
                "downloaded_segments": fragments,
                "last_update": time.time()
            }
        else:
            # Combinar listas de fragmentos
            existing = download_progress[progress_key]["downloaded_segments"]
            combined = list(set(existing + fragments))
            download_progress[progress_key]["downloaded_segments"] = sorted(combined)
            download_progress[progress_key]["last_update"] = time.time()
        
        print(f"[Tracker] Fragmentos sincronizados para {progress_key}: {len(fragments)} fragmentos")
        
        return jsonify({'status': 'synced'}), 200
        
    except Exception as e:
        print(f"[Tracker] Error en syncFragments: {e}")
        return jsonify({'error': str(e)}), 500
if __name__ == '__main__':
    print("\n" + "="*50)
    print("TRACKER P2P INICIADO CON REANUDACIÓN MEJORADA")
    print(f"IP: 192.168.1.68")
    print(f"Puerto: 5000")
    print("="*50 + "\n")
    app.run(port=5000, host="192.168.1.68", debug=True, threaded=True)
