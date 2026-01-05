# tracker_windows/tracker_server.py
import socket
import threading
import json
import time
import sys
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import os

@dataclass
class PeerStatus:
    """Estado de un peer en la red"""
    peer_id: str
    ip_address: str
    port: int
    files_shared: Dict[str, float]  # archivo: porcentaje
    files_downloading: Dict[str, float]  # archivo: progreso
    role: str  # "seeder", "leecher", "peer"
    last_seen: datetime
    status: str  # "online", "offline", "recovering"
    
class BitTorrentTracker:
    def __init__(self, host='192.168.1.68', port=6881):
        self.host = host
        self.port = port
        self.peers: Dict[str, PeerStatus] = {}
        self.file_registry: Dict[str, Set[str]] = {}  # archivo -> [peer_ids]
        self.lock = threading.Lock()
        self.running = True
        
        # Estadísticas
        self.stats = {
            'total_peers': 0,
            'active_transfers': 0,
            'total_files': 0,
            'total_data_transferred': 0
        }
        
    def start(self):
        """Iniciar servidor tracker"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server.bind((self.host, self.port))
            server.listen(10)
            print(f"🚀 Tracker iniciado en {self.host}:{self.port}")
            print("="*60)
            
            # Hilo para mostrar estado
            display_thread = threading.Thread(target=self.display_network_status, daemon=True)
            display_thread.start()
            
            # Hilo para limpieza de peers inactivos
            cleanup_thread = threading.Thread(target=self.cleanup_inactive_peers, daemon=True)
            cleanup_thread.start()
            
            while self.running:
                client_socket, addr = server.accept()
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, addr)
                )
                client_thread.start()
                
        except Exception as e:
            print(f"❌ Error al iniciar tracker: {e}")
            sys.exit(1)
            
    def handle_client(self, client_socket, addr):
        """Manejar conexión de un peer"""
        try:
            data = client_socket.recv(4096).decode('utf-8')
            if not data:
                return
                
            message = json.loads(data)
            msg_type = message.get('type')
            
            with self.lock:
                if msg_type == 'REGISTER':
                    self.register_peer(message, addr[0], client_socket)
                    
                elif msg_type == 'QUERY':
                    self.handle_query(message, client_socket)
                    
                elif msg_type == 'ANNOUNCE':
                    self.handle_announce(message)
                    
                elif msg_type == 'HEARTBEAT':
                    self.handle_heartbeat(message)
                    
                elif msg_type == 'DISCONNECT':
                    self.handle_disconnect(message)
                    
                elif msg_type == 'RECONNECT':
                    self.handle_reconnect(message, client_socket)
                    
        except json.JSONDecodeError:
            print(f"⚠️  Mensaje inválido de {addr}")
        except Exception as e:
            print(f"❌ Error manejando cliente {addr}: {e}")
        finally:
            client_socket.close()
            
    def register_peer(self, message, ip, socket):
        """Registrar un nuevo peer"""
        peer_id = message.get('peer_id')
        port = message.get('port')
        files = message.get('files', {})
        
        # Determinar rol inicial
        complete_files = [f for f, p in files.items() if p == 100.0]
        role = "seeder" if complete_files else "leecher"
        
        peer_status = PeerStatus(
            peer_id=peer_id,
            ip_address=ip,
            port=port,
            files_shared=files,
            files_downloading={},
            role=role,
            last_seen=datetime.now(),
            status="online"
        )
        
        self.peers[peer_id] = peer_status
        
        # Actualizar registro de archivos
        for filename in files.keys():
            if filename not in self.file_registry:
                self.file_registry[filename] = set()
            self.file_registry[filename].add(peer_id)
            
        self.stats['total_peers'] += 1
        self.stats['total_files'] = len(self.file_registry)
        
        # Enviar confirmación
        response = {
            'type': 'REGISTER_RESPONSE',
            'status': 'success',
            'peer_id': peer_id,
            'role': role,
            'tracker_ip': self.host,
            'tracker_port': self.port
        }
        
        socket.send(json.dumps(response).encode('utf-8'))
        
        print(f"✅ Peer registrado: {peer_id} ({ip}:{port})")
        print(f"   Rol: {role}, Archivos: {len(files)}")
        
    def handle_query(self, message, socket):
        """Manejar consulta de archivos"""
        filename = message.get('filename')
        peer_id = message.get('peer_id')
        
        if filename not in self.file_registry:
            response = {'type': 'QUERY_RESPONSE', 'peers': []}
        else:
            peers_info = []
            for pid in self.file_registry[filename]:
                if pid in self.peers and self.peers[pid].status == "online":
                    peer = self.peers[pid]
                    # Verificar que tenga al menos 20% del archivo
                    if filename in peer.files_shared and peer.files_shared[filename] >= 20.0:
                        peers_info.append({
                            'peer_id': pid,
                            'ip': peer.ip_address,
                            'port': peer.port,
                            'progress': peer.files_shared[filename]
                        })
            
            response = {
                'type': 'QUERY_RESPONSE',
                'filename': filename,
                'peers': peers_info
            }
            
        socket.send(json.dumps(response).encode('utf-8'))
        
    def handle_announce(self, message):
        """Actualizar estado de un peer"""
        peer_id = message.get('peer_id')
        filename = message.get('filename')
        progress = message.get('progress', 0.0)
        action = message.get('action')  # 'download', 'upload', 'complete'
        
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            
            # Actualizar archivos compartidos
            if filename not in peer.files_shared or progress > peer.files_shared.get(filename, 0):
                peer.files_shared[filename] = progress
                
                # Si supera 20%, añadir al registro
                if progress >= 20.0:
                    if filename not in self.file_registry:
                        self.file_registry[filename] = set()
                    self.file_registry[filename].add(peer_id)
                    
            # Actualizar descargas
            if action == 'download':
                if filename not in peer.files_downloading:
                    peer.files_downloading[filename] = 0.0
                peer.files_downloading[filename] = progress
                
            # Actualizar rol
            if progress == 100.0:
                peer.role = "seeder"
            elif peer.role == "seeder" and progress < 100.0:
                peer.role = "peer"
                
            peer.last_seen = datetime.now()
            
            if action == 'upload':
                self.stats['total_data_transferred'] += message.get('chunk_size', 0)
                
    def handle_heartbeat(self, message):
        """Manejar latido de conexión"""
        peer_id = message.get('peer_id')
        if peer_id in self.peers:
            self.peers[peer_id].last_seen = datetime.now()
            
    def handle_disconnect(self, message):
        """Manejar desconexión de peer"""
        peer_id = message.get('peer_id')
        if peer_id in self.peers:
            self.peers[peer_id].status = "offline"
            print(f"⚠️  Peer desconectado: {peer_id}")
            
    def handle_reconnect(self, message, socket):
        """Manejar reconexión de peer"""
        peer_id = message.get('peer_id')
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            peer.status = "online"
            peer.last_seen = datetime.now()
            
            # Recuperar estado previo
            recovery_data = {
                'files_shared': peer.files_shared,
                'files_downloading': peer.files_downloading,
                'role': peer.role
            }
            
            response = {
                'type': 'RECONNECT_RESPONSE',
                'status': 'recovered',
                'recovery_data': recovery_data
            }
            
            socket.send(json.dumps(response).encode('utf-8'))
            print(f"🔁 Peer reconectado: {peer_id}")
            
    def cleanup_inactive_peers(self):
        """Limpiar peers inactivos por más de 2 minutos"""
        while self.running:
            time.sleep(30)
            with self.lock:
                now = datetime.now()
                to_remove = []
                for peer_id, peer in self.peers.items():
                    if (now - peer.last_seen).seconds > 120:  # 2 minutos
                        to_remove.append(peer_id)
                        
                for peer_id in to_remove:
                    del self.peers[peer_id]
                    # Limpiar del registro de archivos
                    for file_peers in self.file_registry.values():
                        file_peers.discard(peer_id)
                    print(f"🧹 Peer removido por inactividad: {peer_id}")
                    
    def display_network_status(self):
        """Mostrar estado de la red en tiempo real"""
        while self.running:
            time.sleep(5)
            self.clear_console()
            
            print("\n" + "="*80)
            print("📊 ESTADO DE LA RED BITTORRENT - TRACKER CENTRAL")
            print("="*80)
            
            print(f"\n👥 PEERS CONECTADOS: {len([p for p in self.peers.values() if p.status == 'online'])}")
            print(f"📁 ARCHIVOS REGISTRADOS: {len(self.file_registry)}")
            print(f"📊 DATOS TRANSFERIDOS: {self.stats['total_data_transferred'] / (1024*1024):.2f} MB")
            print("-"*80)
            
            # Tabla de peers
            print(f"\n{'Peer ID':<15} {'IP:Puerto':<20} {'Rol':<10} {'Estado':<10} {'Archivos':<10}")
            print("-"*80)
            
            for peer in sorted(self.peers.values(), key=lambda x: x.peer_id):
                status_icon = "🟢" if peer.status == "online" else "🔴"
                print(f"{peer.peer_id:<15} {peer.ip_address}:{peer.port:<19} "
                      f"{peer.role:<10} {status_icon:<4} {len(peer.files_shared):<10}")
                
            # Archivos disponibles
            print(f"\n📂 ARCHIVOS DISPONIBLES EN LA RED:")
            print("-"*80)
            for filename, peers in self.file_registry.items():
                active_peers = [p for p in peers if p in self.peers and self.peers[p].status == "online"]
                if active_peers:
                    print(f"  • {filename}: {len(active_peers)} peers activos")
                    
            # Transferencias activas
            active_transfers = []
            for peer in self.peers.values():
                for filename, progress in peer.files_downloading.items():
                    if progress < 100.0:
                        active_transfers.append({
                            'peer': peer.peer_id,
                            'file': filename,
                            'progress': progress
                        })
                        
            if active_transfers:
                print(f"\n⬇️  TRANSFERENCIAS ACTIVAS:")
                print("-"*80)
                for transfer in active_transfers:
                    bar = "█" * int(transfer['progress'] / 5)
                    space = " " * (20 - len(bar))
                    print(f"  {transfer['peer']} → {transfer['file']}: [{bar}{space}] {transfer['progress']:.1f}%")
                    
            print("\n" + "="*80)
            print("Presiona Ctrl+C para detener el tracker")
            
    def clear_console(self):
        """Limpiar consola"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
    def stop(self):
        """Detener tracker"""
        self.running = False
        print("\n🛑 Tracker detenido")

if __name__ == "__main__":
    # Obtener IP local automáticamente
    host = socket.gethostbyname(socket.gethostname())
    
    tracker = BitTorrentTracker(host=host, port=6881)
    
    try:
        tracker.start()
    except KeyboardInterrupt:
        tracker.stop()