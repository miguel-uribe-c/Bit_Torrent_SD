import json
from flask import Flask, jsonify, send_file, request
import threading
import time
import requests
import os

app = Flask(__name__)

# Servicio que le permite a cada nodo proporcionar el segmento de un archivo.
@app.route('/downloadFile', methods=['POST'])
def download_file():
    try:
        # Verfifica que la socitud este en JSON.
        if not request.is_json:
            return jsonify({"error": "La solicitud debe contener datos en formato JSON"}), 400
        
        data = request.get_json()

        fileName = data.get("fileName")
        segmentNumber = data.get("segmentNumber")

        # Verifia que los atributos obtenidos arriba, sean partes deñ JSON.
        if not fileName or not isinstance(fileName, str):
            return jsonify({"error": "El campo 'fileName' es obligatorio y debe ser una cadena"}), 400

        if segmentNumber is None or not isinstance(segmentNumber, int) or segmentNumber < 0:
            return jsonify({"error": "El campo 'segmentNumber' es obligatorio y debe ser un entero no negativo"}), 400

        # Verfica que no existan rutas intrusivas.
        if ".." in fileName or "/" in fileName:
            return jsonify({"error": "Nombre de archivo inválido"}), 400
        
        basePath = os.path.join(os.path.dirname(__file__), fileName + "Segment")

        filePath = os.path.join(basePath, f"fragment_{segmentNumber}.part")

        # Verifica que el archivo exista.
        if not os.path.exists(filePath):
            return jsonify({"error": "El archivo no existe"}), 404

        return send_file(filePath, as_attachment=True)

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500
    

def clientTask():
        
        exit = False
        
        deviceIp = input("Ingresa la dirección IP del dispositivo: ")

        # Manda a llamar el servicio que verifica que existan descargas oebdientes.
        responseInitial = requests.post("http://172.22.88.17:5000/verifyPendingDownloads", json={"IP" : deviceIp})

        initialResponse = responseInitial.json()

        # Si hay descargas pendientes, se realizan ciclos para cada solicitud.
        if not initialResponse["message"] == 'No hay descargas pendientes.':
            for req in initialResponse["pendingRequests"]: # para cada solicitud pendiente.
                leechersAndSeeders = req["peersAndLeechers"] # Obten los peers y los leechers
                for peer in  leechersAndSeeders: # para cada peer
                    for i in range(peer["trackerSegment"], peer["LastFile"], 1): # Genera un bucle for para cada fragmento
                        response4 = requests.post("http://" + peer["IP"] + ":5001" + "/downloadFile", json = {"fileName" : req["File2Download"], "segmentNumber": i}) # Realiza la solicitud
                        if response4.status_code == 200:
                            file_name = f"fragment_{i}.part"
                            if not os.path.exists(req["File2Download"] + "Segment"):
                                os.makedirs(req["File2Download"] + "Segment")

                            file_path = os.path.join(req["File2Download"] + "Segment", file_name)
                            with open(file_path, "wb") as f:
                                f.write(response4.content) # Guarda el contenido de la solicitud
                            print(f"Archivo guardado en: {file_path}")
                            try:
                                # Notifica al tracker que se ha obtenido un fragmento de archivo.
                                response5 = requests.post("http://172.22.88.17:5000/updatePeers", json = {"fileName" : req["File2Download"], "IP" : deviceIp, "currentSegments": i, "numSegments": leechersAndSeeders[0]["numSegments"], "peerIP" : peer["IP"]})
                            except Exception as e:
                                print(f"Ocurrió un error al solicitar un archivo: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"Error: {response.status_code}")
                            print(response.json()) 
                # Segmento de código que se encarga de reconstruir el archivo.
                fragmentos = sorted([os.path.join(req["File2Download"] + "Segment", f) for f in os.listdir(req["File2Download"] + "Segment")],key=lambda x: int(os.path.basename(x).split('_')[1].split('.')[0]))
                with open(req["File2Download"], 'wb') as archivo:
                        for fragmento in fragmentos:
                            with open(fragmento, 'rb') as f:
                                archivo.write(f.read())
                print(f"Archivo reconstruido como {req["File2Download"]}.")

        filesInnput = input("Ingresa el archivo que deseas incorporar a la red(por ejemplo: hola.txt, ejemplo.mp3): ")
        
        filesList = [file.strip() for file in filesInnput.split(',')]

        currentFragments = segmentFile(filesList)
        
        payload = {
            "IP": deviceIp,
            "Files": currentFragments
        }
        
        api_url = "http://172.22.88.17:5000/enterNetwork" # Se llama al servicio para incluir a este nodo en la red.
        try:
            response = requests.post(api_url, json=payload)
            
            if response.status_code == 201:
                print("Solicitud exitosa. Ahora es parte de la red:")
                print(response.json())
            else:
                print(f"Error: {response.status_code}. Respuesta del servidor:")
                print(response.text)
        except Exception as e:
            print(f"Ocurrió un error al unirse a la red: {e}")


        while not exit:
            select = input("Escoja alguna de las siguientes opciones.  \n1) Agregar un archivo a la red. \n2) Descargar un archivo de la red. \nSu respuesta: ")
            if select == "1":
                filesInnput = input("Ingresa los archivos separados por comas (por ejemplo: hola.txt, ejemplo.mp3): ")
                filesList = [file.strip() for file in filesInnput.split(',')]
                currentFragments = segmentFile(filesList)
                newFiles = {"addedFiles": currentFragments}
                try:
                    response1 = requests.put( "http://172.22.88.17:5000/addFile/" + deviceIp, json=newFiles) # Llama al servicio para agregar un archivo a la red.
            
                    if response1.status_code == 201:
                        print("Se ha agregado el archivo a la red:")
                        print(response1.json())
                    else:
                        print(f"Error: {response.status_code}. Respuesta del servidor:")
                        print(response1.text)
                except Exception as e:
                    print(f"Ocurrió un error al agregar un archivo: {e}")
            elif select == "2":
                try:
                    response2 = requests.get("http://172.22.88.17:5000/allFiles") # LLama al servicio para obtener todos los archivos disponibles de la red.
                    if response2.status_code == 200:
                        desiredFile = ''
                        print("Solicitud exitosa. Estos son los archivos que se encuentran en la red:")
                        for file in response2.json()['Files']: #Revisa la lista de archivos y los imprime.
                            print('- ' + file)
                        while not desiredFile in response2.json()['Files']:
                            desiredFile = input("Escriba el archivo que desea descargar: ")
                        try:
                            response3 = requests.post("http://172.22.88.17:5000/downloadFile", json={"fileName" : desiredFile, "IP" : deviceIp }) # LLama al servicio para descargar el archivo y le pasa la dirección IP del nodo y el archivo que se desea descargar.
                            
                            if response3.status_code == 200:
                                try:
                                   information = response3.json()["information"] # Accede a la información de la respuesta del tracker.
                                   leechersAndSeeders = information["peersAndLeechers"] # Obtiene todos los seeders y leechers (Peer)
                                   for peer in  leechersAndSeeders: # para cada peer
                                       for i in range(peer["StartingFile"], peer["LastFile"], 1): # Se genera un ciclo for para cada fragmento a descargar.
                                            response4 = requests.post("http://" + peer["IP"] + ":5001" + "/downloadFile", json = {"fileName" : information["File2Download"], "segmentNumber": i}) # Manda a llamar al servicio del nodo (peer) del cual se debe descargar el archivo.
                                            if response4.status_code == 200:
                                                file_name = f"fragment_{i}.part"
                                                if not os.path.exists(desiredFile + "Segment"): # Si no existe el directorio.
                                                    os.makedirs(desiredFile + "Segment") # Crealo.

                                                file_path = os.path.join(desiredFile + "Segment", file_name)
                                                with open(file_path, "wb") as f:
                                                    f.write(response4.content) # Guarda el fragmento recuperado.
                                                print(f"Archivo guardado en: {file_path}")
                                                try:
                                                    response5 = requests.post("http://172.22.88.17:5000/updatePeers", json = {"fileName" : desiredFile, "IP" : deviceIp, "currentSegments": i, "numSegments": leechersAndSeeders[0]["numSegments"], "peerIP" : peer["IP"]}) # Se le notifica al Tracker que fragmento  se ha recuperado y de que peer se ha recuperado.
                                                except Exception as e:
                                                    print(f"Ocurrió un error al solicitar un archivo: {e}")
                                                    import traceback
                                                    traceback.print_exc()
                                            else:
                                                print(f"Respuesta del servidor: {response.status_code}")
                                                print(response.json()) 

                                   # reconstruye el archivo.             
                                   fragmentos = sorted([os.path.join(desiredFile + "Segment", f) for f in os.listdir(desiredFile + "Segment")],key=lambda x: int(os.path.basename(x).split('_')[1].split('.')[0]))
                                   with open(desiredFile, 'wb') as archivo:
                                        for fragmento in fragmentos:
                                            with open(fragmento, 'rb') as f:
                                                archivo.write(f.read())
                                   print(f"Archivo reconstruido como {desiredFile}.")
                                   
                                except Exception as e:
                                    print(f"Hubo un error en el procedimiento para la obtencion del archivo en la red: {e}")
                        except Exception as e:
                            print(f"Ocurrió un error al solicitar un archivo: {e}")
                    else:
                        print(f"Error: {response.status_code}. Respuesta del servidor:")
                        print(response.text)
                except Exception as e:
                    print(f"Ocurrió un error al unirse a la red: {e}")
            elif select == "3":
                exit = True


# Función para segmentar el archivo.
def segmentFile(filesList):
    currentFragments = []
    for file in filesList:
            if not os.path.exists(file + "Segment"):
                os.makedirs(file + "Segment")
                with open(file, 'rb') as archivo:
                    fragments = 0
                    while fragmento := archivo.read(10240):
                        ruta_fragmento = os.path.join(file + "Segment", f'fragment_{fragments}.part')
                        with open(ruta_fragmento, 'wb') as f:
                            f.write(fragmento)
                            fragments += 1
            print(f"Archivo segmentado en {fragments} fragmentos en la carpeta {file + "Segment"}.")
            currentFragments.append({"fileName": file, "numSegments": fragments, "currentSegments": fragments})
            return currentFragments


if __name__ == "__main__":
    # Thread para que se ejcute la función del cliente.
    client_thread = threading.Thread(target=clientTask)
    client_thread.start()

    # Corre el cliente.
    app.run(host="172.22.88.17", port=5001, debug=False, threaded=True)
