# tracker_windows/tracker_console.py
import threading
import json
import time
from datetime import datetime

class TrackerConsole:
    def __init__(self, tracker):
        self.tracker = tracker
        self.commands = {
            'help': self.show_help,
            'peers': self.list_peers,
            'files': self.list_files,
            'stats': self.show_stats,
            'kick': self.kick_peer,
            'broadcast': self.broadcast_message,
            'save': self.save_state,
            'load': self.load_state
        }
        
    def show_help(self):
        print("\n📋 COMANDOS DISPONIBLES:")
        print("  help       - Mostrar esta ayuda")
        print("  peers      - Listar todos los peers")
        print("  files      - Listar archivos disponibles")
        print("  stats      - Mostrar estadísticas")
        print("  kick <id>  - Expulsar un peer")
        print("  broadcast  - Enviar mensaje a todos")
        print("  save       - Guardar estado")
        print("  load       - Cargar estado")
        print("  exit       - Salir")
        
    def list_peers(self, detailed=False):
        print("\n👥 LISTA DE PEERS:")
        print("-"*60)
        for peer_id, peer in self.tracker.peers.items():
            print(f"\n🔹 {peer_id}")
            print(f"   IP: {peer.ip_address}:{peer.port}")
            print(f"   Estado: {'🟢 Online' if peer.status == 'online' else '🔴 Offline'}")
            print(f"   Rol: {peer.role}")
            print(f"   Última conexión: {peer.last_seen.strftime('%H:%M:%S')}")
            
            if detailed:
                print(f"   Archivos compartidos: {len(peer.files_shared)}")
                for file, progress in peer.files_shared.items():
                    print(f"     - {file}: {progress}%")
                    
    def list_files(self):
        print("\n📁 ARCHIVOS EN LA RED:")
        print("-"*60)
        for filename, peers in self.tracker.file_registry.items():
            active_peers = [p for p in peers if p in self.tracker.peers and self.tracker.peers[p].status == 'online']
            print(f"\n📄 {filename}")
            print(f"   Disponible en: {len(active_peers)} peer(s)")
            for peer_id in active_peers:
                progress = self.tracker.peers[peer_id].files_shared.get(filename, 0)
                print(f"   • {peer_id}: {progress}% completo")
                
    def show_stats(self):
        print("\n📊 ESTADÍSTICAS DE LA RED:")
        print("-"*60)
        print(f"Peers totales registrados: {self.tracker.stats['total_peers']}")
        print(f"Peers en línea: {len([p for p in self.tracker.peers.values() if p.status == 'online'])}")
        print(f"Archivos únicos: {len(self.tracker.file_registry)}")
        print(f"Datos transferidos: {self.tracker.stats['total_data_transferred'] / (1024*1024):.2f} MB")
        
        # Transferencias simultáneas
        active_downloads = sum(len(p.files_downloading) for p in self.tracker.peers.values())
        print(f"Descargas activas: {active_downloads}")
        
    def start_console(self):
        """Iniciar consola interactiva"""
        self.show_help()
        
        while True:
            try:
                command = input("\ntracker> ").strip().split()
                if not command:
                    continue
                    
                cmd = command[0].lower()
                
                if cmd == 'exit':
                    print("👋 Saliendo de la consola...")
                    break
                    
                if cmd in self.commands:
                    if len(command) > 1:
                        self.commands[cmd](command[1])
                    else:
                        self.commands[cmd]()
                else:
                    print(f"❌ Comando desconocido: {cmd}")
                    
            except KeyboardInterrupt:
                print("\n👋 Saliendo de la consola...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")