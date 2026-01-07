import json
from collections import Counter
from flask import Flask, jsonify, request
app = Flask(__name__)

# Arreglo que guarda todos los nodos pertenecientes a la red, unto con los archivos que poseen.
peers = []

# Solictudes pendientes de descargas.
pendingRequests = []


# Servicio para que un nodo entre a la red.
@app.route('/enterNetwork', methods=['POST'])
def enterNetwork():
 potencialPeer = json.loads(request.data)
 registredIP = []
 # Se busca si el peer ya pertenece a la red.
 for peer in peers:
  registredIP.append(peer["IP"])
 if potencialPeer['IP'] in registredIP:
  return jsonify({ 'location': 'Nodo ya perteneciente a la red bitTorrent' }), 200
 
 # Si no es así, agregalo al arreglo de peers.
 peers.append(potencialPeer)

 print(peers)

 return jsonify({ 'location': 'Se ha agregado su nodo a la red.' }), 201

# Servicio que devuelve todos los peers pertenecientes a la red.
@app.route('/peers', methods=['GET'])
def getPeers():
  return jsonify(peers)


# Servicio que itera através del arreglo descargas pendientes y verifica que no haya solicitudes pendientes.
@app.route('/verifyPendingDownloads', methods = ["POST"])
def verifyPendingDownloads():
  peerInfo = json.loads(request.data)
  req = next((r for r in pendingRequests if r["IP"] == peerInfo["IP"]), None)
  if req is None:
    return jsonify({ 'message': 'No hay descargas pendientes.' }), 200
  return jsonify({"pendingRequests" : pendingRequests, 'message': 'Hya descargas pendientes.'}), 200

# Servicio que actualiza la información de la lista de los peers.
@app.route('/updatePeers', methods = ["POST"])
def updatePeers():
   newPeerInfo = json.loads(request.data)
   req = next((r for r in pendingRequests if r["File2Download"] == newPeerInfo["fileName"] and r["IP"] == newPeerInfo["IP"]), None) # Busca si la socitud de descarga existe.
   if req is None:
      return jsonify({ 'error': 'No se identifico la solicitud de descarga.' }), 404

  # Segmento que se encarga de actualizar la solicitud de descarga, si esta solitud ha culminado (se han descargado todos los fragmentos) se borra.
   for dic in req["peersAndLeechers"]:
        if dic["IP"] == newPeerInfo["peerIP"]:
            dic["trackerSegment"] = newPeerInfo["currentSegments"] + 1
            if dic["trackerSegment"] == dic["LastFile"]:
                req["peersAndLeechers"].remove(dic)
            break

    # Buscar al peer dentro del areglo.
   peer = next((p for p in peers if newPeerInfo['IP'] == p["IP"]), None)
   if peer is None:
    return jsonify({ 'error': 'No se identifico el peer.' }), 404
   file = next((f for f in peer["Files"] if f["fileName"] == newPeerInfo["fileName"]), None)
   # Si no se registra el archivo dentro de la solicitud actualiza al peer para inidicar que se va a iniciar la descarga del archivo.
   if file is None:
      peer["Files"].append({"fileName" : newPeerInfo["fileName"], "numSegments" : newPeerInfo["numSegments"], "currentSegments": newPeerInfo["currentSegments"]})
      return jsonify({ 'messsage': 'Se ha actualizado el estatus del peer.' }), 200
   # Si ya se encuentra el archivo, actualiza los fragmentos que se han descargado.
   file["currentSegments"] = newPeerInfo["currentSegments"]
   return jsonify({ 'messsage': 'Se ha actualizado el estatus del peer.' }), 200

# Servicio que agrega un archivo a la red.
@app.route('/addFile/<ip>', methods=['PUT'])
def addFile(ip: str):
 # Busca al peer dentro del arreglo de peers
 peer = next((p for p in peers if p['IP'] == ip), None)
 if peer is None:
   return jsonify({ 'error': 'No se identifico el peer.' }), 404 # Si no se encuentra el peer, notificalo.

 updatedFiles = json.loads(request.data)

# Segmento que ayuda a la actualización del peer, agregando uh archivo a su sublista "Files".
 auxDic = {file["fileName"] : file for file in peer["Files"]}
 for file in updatedFiles["addedFiles"]:
   auxDic[file["fileName"]] = file
 peer["Files"] = list(auxDic.values())

 return jsonify(peers), 200

# Servicio que devuelve todos los archivos de la red, sin importar el numero de peers que los poseean.
@app.route('/allFiles', methods = ['GET'])
def showFiles():
  allFiles = set()
  for peer in peers:
    for file in peer["Files"]:
        allFiles.add(file["fileName"])

  listAllFiles = list(allFiles)

  return jsonify({ 'Files': listAllFiles }), 200

# Servicio que gestiona la descarga de un archivo-
@app.route("/downloadFile", methods = ["POST"])
def downloadFile():
  infomarionForDownload = json.loads(request.data)
  availablePeers = []
  # Ciclos for que identifican a todos los peers (nodos) que poseen el archivo deseado por el peer origen que cumple la condición de que se cuenta con más del 20% del archivo.
  for peer in peers:
      for file in peer["Files"]:
          if file["fileName"] == infomarionForDownload["fileName"] and file["currentSegments"] / file["numSegments"] >= 0.2:
              availablePeers.append({
                  "IP": peer["IP"],
                  "currentSegments": file["currentSegments"],
                  "numSegments": file["numSegments"]
              })
  # =============== Algoritmo para elegir a los peers y el numero de fragmentos que le corresponde proporcionar al peer cliente ==================
  availablePeers = sorted(availablePeers, key=lambda x: x["currentSegments"])


  count = Counter(peer["numSegments"] for peer in availablePeers)

  sortedSegments = sorted(count.keys())
    
  ranges = []
  start = -1  
    
  for num in sortedSegments:
      occurrences = count[num]
      rangeSize = num - start
        
      if rangeSize < occurrences:
          raise ValueError(f"Rango insuficiente para dividir en {occurrences} partes")
        
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
          #result.append(data[range_index])
          range_index += 1

# ====================================================================================================================================================

  availablePeers2 = availablePeers

  for peer in availablePeers2:
     peer.update({"trackerSegment": peer["StartingFile"]})

  downloadingResolution = {
    "IP": infomarionForDownload["IP"],
    "File2Download" : infomarionForDownload["fileName"],
    "peersAndLeechers" : availablePeers2
  }

  # Se actualiza la lista "pendingRequests"
  pendingRequests.append(downloadingResolution)

  # Se le notifica al peer cliente, de que peers o seeders puede obtener los fragmentos del archivo deseado.
  return jsonify({ 'Status': 'Se han encontrado peers y seeders para proveer los archivos.', 'information':  {
    "IP": infomarionForDownload["IP"],
    "File2Download" : infomarionForDownload["fileName"],
    "peersAndLeechers" : availablePeers
  }}), 200

# Servicio que devuelve la lista de descargas pendientes.
@app.route("/pendingDownloads", methods = ["GET"])
def pendingDownloads():
   return jsonify(pendingRequests)
#============================================================================


if __name__ == '__main__':
   app.run(port=5000, host="192.168.1.64", debug=True, threaded=True)
