# peer_linux/peer_node.py
import socket
import threading
import json
import hashlib
import os
import time
import sys
from datetime import datetime
from typing import Dict, List, Optional
import struct
import random

class BitTorrentPeer:
    def __init__(self, peer_id=None, tracker_ip='192.168.1.100', tracker_port=6881):
        self.peer_id = peer_id or f"peer_{random.randint(1000, 9999)}"
        self.tracker_ip = tracker_ip
        self.tracker_port = tracker_port
        
        # Archivos locales
        self.shared_dir = "./shared_files"
        self.download_dir = "./downloads"
        self.state_file = f"./peer_state_{self.peer_id}.json"
        
        # Estado del peer
        self.files_shared: Dict[str, float] = {}  # archivo: porcentaje
        self.files_downloading: Dict[str, Dict] = {}  # Información de descarga
        self.active_connections: Dict[str, socket.socket] = {}
        
        # Configuración de red
        self.local_ip = self.get_local_ip()
        self.local_port = random.randint(6882, 6890)
        
        # Servidor para recibir conexiones
        self.server_socket = None
        self.running = True
        
        # Cargar estado previo si existe
        self.load_state()
        
    def get_local_ip(self):
        """Obtener IP local"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
        
    def start(self):
        """Iniciar nodo peer"""
        print(f"🚀 Iniciando Peer: {self.peer_id}")
        print(f"📍 IP Local: {self.local_ip}:{self.local_port}")
        print(f"🔗 Tracker: {self.tracker_ip}:{self.tracker_port}")
        
        # Iniciar servidor para conexiones entrantes
        server_thread = threading.Thread(target=self.start_server, daemon=True)
        server_thread.start()
        
        # Registrar en tracker
        if not self.register_with_tracker():
            print("❌ No se pudo conectar al tracker")
            return
            
        # Iniciar heartbeat
        heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        # Mostrar interfaz
        self.show_interface()
        
    def start_server(self):
        """Iniciar servidor para conexiones de otros peers"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.local_ip, self.local_port))
            self.server_socket.listen(5)
            
            while self.running:
                client_socket, addr = self.server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_incoming_connection,
                    args=(client_socket, addr)
                )
                client_thread.start()
                
        except Exception as e:
            print(f"❌ Error en servidor: {e}")
            
    def handle_incoming_connection(self, client_socket, addr):
        """Manejar conexión entrante de otro peer"""
        try:
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                return
                
            message = json.loads(data)
            msg_type = message.get('type')
            
            if msg_type == 'REQUEST_CHUNK':
                self.send_chunk(client_socket, message)
            elif msg_type == 'STATUS_QUERY':
                self.send_status(client_socket)
                
        except Exception as e:
            print(f"❌ Error manejando conexión de {addr}: {e}")
        finally:
            client_socket.close()
            
    def register_with_tracker(self):
        """Registrarse en el tracker"""
        try:
            # Escanear archivos compartidos
            self.scan_shared_files()
            
            # Crear mensaje de registro
            register_msg = {
                'type': 'REGISTER',
                'peer_id': self.peer_id,
                'port': self.local_port,
                'files': self.files_shared,
                'ip': self.local_ip
            }
            
            # Conectar al tracker
            tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tracker_socket.connect((self.tracker_ip, self.tracker_port))
            tracker_socket.send(json.dumps(register_msg).encode('utf-8'))
            
            response = tracker_socket.recv(4096).decode('utf-8')
            response_data = json.loads(response)
            
            if response_data.get('status') == 'success':
                print(f"✅ Registrado en tracker como {self.peer_id}")
                print(f"   Rol asignado: {response_data.get('role')}")
                return True
                
        except Exception as e:
            print(f"❌ Error registrándose en tracker: {e}")
            
        return False
        
    def scan_shared_files(self):
        """Escanear archivos en el directorio compartido"""
        if not os.path.exists(self.shared_dir):
            os.makedirs(self.shared_dir)
            # Crear archivos de prueba si no existen
            self.create_sample_files()
            
        for filename in os.listdir(self.shared_dir):
            filepath = os.path.join(self.shared_dir, filename)
            if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                self.files_shared[filename] = 100.0  # 100% completo
                
    def create_sample_files(self):
        """Crear archivos de prueba de 50MB+"""
        sample_files = [
            "video_1.mp4",
            "video_2.mp4", 
            "document_1.pdf",
            "document_2.pdf",
            "audio_1.mp3",
            "audio_2.mp3"
        ]
        
        for filename in sample_files:
            filepath = os.path.join(self.shared_dir, filename)
            with open(filepath, 'wb') as f:
                # Crear archivo de ~52MB
                f.write(os.urandom(52 * 1024 * 1024))
            print(f"📁 Creado archivo: {filename} (52MB)")
            
    def query_file(self, filename):
        """Consultar archivo en tracker"""
        try:
            query_msg = {
                'type': 'QUERY',
                'peer_id': self.peer_id,
                'filename': filename
            }
            
            tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tracker_socket.connect((self.tracker_ip, self.tracker_port))
            tracker_socket.send(json.dumps(query_msg).encode('utf-8'))
            
            response = tracker_socket.recv(4096).decode('utf-8')
            response_data = json.loads(response)
            
            tracker_socket.close()
            
            if response_data.get('peers'):
                return response_data['peers']
            else:
                print(f"❌ Archivo no encontrado: {filename}")
                
        except Exception as e:
            print(f"❌ Error consultando archivo: {e}")
            
        return []
        
    def download_file(self, filename, peers_info):
        """Descargar archivo de múltiples peers"""
        print(f"\n⬇️  Iniciando descarga: {filename}")
        print(f"   Fuentes disponibles: {len(peers_info)}")
        
        # Inicializar estructura de descarga
        if filename not in self.files_downloading:
            self.files_downloading[filename] = {
                'progress': 0.0,
                'total_size': 0,
                'downloaded': 0,
                'chunks': {},
                'sources': peers_info
            }
            
        # Descargar de múltiples peers simultáneamente
        threads = []
        chunk_size = 1024 * 1024  # 1MB por chunk
        
        for i, peer_info in enumerate(peers_info[:3]):  # Máximo 3 fuentes
            thread = threading.Thread(
                target=self.download_from_peer,
                args=(filename, peer_info, chunk_size, i)
            )
            threads.append(thread)
            thread.start()
            
        # Monitorear progreso
        self.monitor_download(filename)
        
        # Esperar a que terminen todos los hilos
        for thread in threads:
            thread.join()
            
        # Completar archivo
        self.complete_download(filename)
        
    def download_from_peer(self, filename, peer_info, chunk_size, thread_id):
        """Descargar fragmentos de un peer específico"""
        peer_id = peer_info['peer_id']
        peer_ip = peer_info['ip']
        peer_port = peer_info['port']
        
        try:
            # Conectar al peer
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.connect((peer_ip, peer_port))
            
            # Solicitar chunks disponibles
            chunk_request = {
                'type': 'REQUEST_CHUNK',
                'filename': filename,
                'peer_id': self.peer_id,
                'chunk_index': thread_id  # Cada thread descarga chunks diferentes
            }
            
            peer_socket.send(json.dumps(chunk_request).encode('utf-8'))
            
            # Recibir chunks
            while True:
                # Primero recibir información del chunk
                chunk_info_data = peer_socket.recv(1024)
                if not chunk_info_data:
                    break
                    
                chunk_info = json.loads(chunk_info_data.decode('utf-8'))
                
                if chunk_info.get('type') == 'CHUNK_DATA':
                    chunk_index = chunk_info['chunk_index']
                    chunk_size = chunk_info['chunk_size']
                    
                    # Recibir datos del chunk
                    received = 0
                    chunk_data = b''
                    
                    while received < chunk_size:
                        data = peer_socket.recv(min(4096, chunk_size - received))
                        if not data:
                            break
                        chunk_data += data
                        received += len(data)
                        
                    # Guardar chunk
                    self.save_chunk(filename, chunk_index, chunk_data)
                    
                    # Anunciar progreso al tracker
                    self.announce_progress(filename)
                    
                elif chunk_info.get('type') == 'NO_MORE_CHUNKS':
                    break
                    
            peer_socket.close()
            
        except Exception as e:
            print(f"❌ Error descargando de {peer_id}: {e}")
            
    def save_chunk(self, filename, chunk_index, chunk_data):
        """Guardar chunk descargado"""
        download_info = self.files_downloading[filename]
        
        # Crear directorio temporal si no existe
        temp_dir = os.path.join(self.download_dir, filename + "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Guardar chunk
        chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index:04d}")
        with open(chunk_path, 'wb') as f:
            f.write(chunk_data)
            
        # Actualizar progreso
        download_info['chunks'][chunk_index] = True
        download_info['downloaded'] += len(chunk_data)
        
        if download_info['total_size'] > 0:
            progress = (download_info['downloaded'] / download_info['total_size']) * 100
            download_info['progress'] = progress
            
    def announce_progress(self, filename):
        """Anunciar progreso al tracker"""
        try:
            progress = self.files_downloading[filename]['progress']
            
            # Actualizar archivos compartidos si tiene más del 20%
            if progress >= 20.0 and filename not in self.files_shared:
                self.files_shared[filename] = progress
                
            announce_msg = {
                'type': 'ANNOUNCE',
                'peer_id': self.peer_id,
                'filename': filename,
                'progress': progress,
                'action': 'download'
            }
            
            tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tracker_socket.connect((self.tracker_ip, self.tracker_port))
            tracker_socket.send(json.dumps(announce_msg).encode('utf-8'))
            tracker_socket.close()
            
        except Exception as e:
            print(f"⚠️  Error anunciando progreso: {e}")
            
    def monitor_download(self, filename):
        """Monitorear y mostrar progreso de descarga"""
        import time
        
        print(f"\n📊 Progreso de descarga: {filename}")
        print("-"*50)
        
        while filename in self.files_downloading:
            info = self.files_downloading[filename]
            progress = info['progress']
            
            # Mostrar barra de progreso
            bar_length = 40
            filled = int(bar_length * progress / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            downloaded_mb = info['downloaded'] / (1024 * 1024)
            
            print(f"\r[{bar}] {progress:.1f}% ({downloaded_mb:.1f} MB)", end='', flush=True)
            
            if progress >= 100.0:
                print()  # Nueva línea
                break
                
            time.sleep(1)
            
    def complete_download(self, filename):
        """Completar la descarga ensamblando chunks"""
        print(f"\n✅ Descarga completada: {filename}")
        
        # Ensamblar chunks
        temp_dir = os.path.join(self.download_dir, filename + "_temp")
        final_path = os.path.join(self.download_dir, filename)
        
        # Ordenar chunks
        chunk_files = sorted([
            f for f in os.listdir(temp_dir) 
            if f.startswith('chunk_')
        ])
        
        with open(final_path, 'wb') as final_file:
            for chunk_file in chunk_files:
                chunk_path = os.path.join(temp_dir, chunk_file)
                with open(chunk_path, 'rb') as cf:
                    final_file.write(cf.read())
                    
        # Limpiar chunks temporales
        import shutil
        shutil.rmtree(temp_dir)
        
        # Actualizar estado
        self.files_shared[filename] = 100.0
        del self.files_downloading[filename]
        
        print(f"📁 Archivo guardado en: {final_path}")
        
    def send_heartbeat(self):
        """Enviar latidos periódicos al tracker"""
        while self.running:
            try:
                heartbeat_msg = {
                    'type': 'HEARTBEAT',
                    'peer_id': self.peer_id
                }
                
                tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tracker_socket.connect((self.tracker_ip, self.tracker_port))
                tracker_socket.send(json.dumps(heartbeat_msg).encode('utf-8'))
                tracker_socket.close()
                
            except:
                print("⚠️  Error enviando heartbeat, intentando reconexión...")
                self.reconnect_to_tracker()
                
            time.sleep(30)  # Cada 30 segundos
            
    def reconnect_to_tracker(self):
        """Reconectar al tracker después de desconexión"""
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                print(f"🔄 Intentando reconexión ({attempt + 1}/{max_attempts})...")
                
                reconnect_msg = {
                    'type': 'RECONNECT',
                    'peer_id': self.peer_id,
                    'port': self.local_port,
                    'ip': self.local_ip
                }
                
                tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tracker_socket.connect((self.tracker_ip, self.tracker_port))
                tracker_socket.send(json.dumps(reconnect_msg).encode('utf-8'))
                
                response = tracker_socket.recv(4096).decode('utf-8')
                response_data = json.loads(response)
                
                if response_data.get('status') == 'recovered':
                    print("✅ Reconexión exitosa, estado recuperado")
                    return True
                    
            except Exception as e:
                print(f"❌ Intento {attempt + 1} fallido: {e}")
                time.sleep(2)  # Esperar antes de reintentar
                
        return False
        
    def save_state(self):
        """Guardar estado del peer"""
        state = {
            'peer_id': self.peer_id,
            'files_shared': self.files_shared,
            'files_downloading': self.files_downloading,
            'local_ip': self.local_ip,
            'local_port': self.local_port,
            'last_update': datetime.now().isoformat()
        }
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
            
        print("💾 Estado guardado")
        
    def load_state(self):
        """Cargar estado previo del peer"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    
                # Restaurar estado de descargas en progreso
                if 'files_downloading' in state:
                    self.files_downloading = state['files_downloading']
                    print("📂 Estado anterior cargado, descargas pendientes recuperadas")
                    
            except Exception as e:
                print(f"⚠️  Error cargando estado: {e}")
                
    def show_interface(self):
        """Mostrar interfaz interactiva"""
        print("\n" + "="*60)
        print(f"👤 PEER: {self.peer_id}")
        print(f"📍 {self.local_ip}:{self.local_port}")
        print("="*60)
        
        while self.running:
            try:
                print("\n📋 MENÚ PRINCIPAL:")
                print("1. Listar mis archivos compartidos")
                print("2. Buscar archivo en la red")
                print("3. Descargar archivo")
                print("4. Ver descargas en progreso")
                print("5. Simular desconexión/reconexión")
                print("6. Guardar estado y salir")
                
                choice = input("\nSeleccione opción (1-6): ").strip()
                
                if choice == '1':
                    self.list_shared_files()
                elif choice == '2':
                    self.search_file()
                elif choice == '3':
                    self.download_menu()
                elif choice == '4':
                    self.show_downloads()
                elif choice == '5':
                    self.simulate_disconnection()
                elif choice == '6':
                    self.save_state()
                    print("👋 Saliendo...")
                    self.running = False
                    break
                    
            except KeyboardInterrupt:
                print("\n👋 Saliendo...")
                self.running = False
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                
    def list_shared_files(self):
        """Listar archivos compartidos por este peer"""
        print("\n📁 MIS ARCHIVOS COMPARTIDOS:")
        print("-"*50)
        for filename, progress in self.files_shared.items():
            status = "✅ COMPLETO" if progress == 100 else f"⬇️  {progress:.1f}%"
            print(f"  • {filename}: {status}")
            
    def search_file(self):
        """Buscar archivo en la red"""
        filename = input("\n🔍 Nombre del archivo a buscar: ").strip()
        if not filename:
            return
            
        peers = self.query_file(filename)
        if peers:
            print(f"\n📄 Archivo encontrado: {filename}")
            print("Fuentes disponibles:")
            for i, peer in enumerate(peers, 1):
                print(f"  {i}. {peer['peer_id']} ({peer['ip']}:{peer['port']}) - {peer['progress']}%")
        else:
            print("❌ Archivo no encontrado en la red")
            
    def download_menu(self):
        """Menú de descarga"""
        filename = input("\n⬇️  Nombre del archivo a descargar: ").strip()
        if not filename:
            return
            
        # Verificar si ya lo tenemos
        if filename in self.files_shared and self.files_shared[filename] == 100.0:
            print("✅ Ya tienes este archivo completo")
            return
            
        # Buscar en la red
        peers = self.query_file(filename)
        if not peers:
            print("❌ Archivo no disponible")
            return
            
        # Descargar
        self.download_file(filename, peers)
        
    def show_downloads(self):
        """Mostrar descargas en progreso"""
        if not self.files_downloading:
            print("\n📭 No hay descargas en progreso")
            return
            
        print("\n⬇️  DESCARGAS EN PROGRESO:")
        print("-"*60)
        for filename, info in self.files_downloading.items():
            print(f"\n📄 {filename}")
            print(f"   Progreso: {info['progress']:.1f}%")
            print(f"   Descargado: {info['downloaded'] / (1024*1024):.1f} MB")
            print(f"   Fuentes: {len(info['sources'])}")
            
    def simulate_disconnection(self):
        """Simular desconexión y reconexión"""
        print("\n🔌 SIMULANDO DESCONEXIÓN...")
        
        # Simular desconexión
        disconnect_msg = {
            'type': 'DISCONNECT',
            'peer_id': self.peer_id
        }
        
        try:
            tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tracker_socket.connect((self.tracker_ip, self.tracker_port))
            tracker_socket.send(json.dumps(disconnect_msg).encode('utf-8'))
            tracker_socket.close()
            
            print("⚠️  Desconectado del tracker")
            time.sleep(3)  # Esperar 3 segundos
            
            # Reconectar
            print("🔄 RECONECTANDO...")
            if self.reconnect_to_tracker():
                print("✅ Reconexión exitosa")
            else:
                print("❌ No se pudo reconectar")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='BitTorrent Peer Node')
    parser.add_argument('--peer-id', help='ID del peer (opcional)')
    parser.add_argument('--tracker-ip', default='192.168.1.100', 
                       help='IP del tracker')
    parser.add_argument('--tracker-port', type=int, default=6881,
                       help='Puerto del tracker')
    
    args = parser.parse_args()
    
    # Configurar según máquina
    # Windows tracker: 192.168.1.100
    # Ubuntu peer: 192.168.1.101  
    # Mint peer: 192.168.1.102
    
    peer = BitTorrentPeer(
        peer_id=args.peer_id,
        tracker_ip=args.tracker_ip,
        tracker_port=args.tracker_port
    )
    
    try:
        peer.start()
    except KeyboardInterrupt:
        peer.save_state()
        print("\n👋 Peer detenido")