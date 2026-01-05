# setup_network.py
import subprocess
import json
import sys
import os

def get_ip_address():
    """Obtener IP local"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def configure_network():
    """Configurar red para 3 máquinas"""
    
    config = {
        "tracker": {
            "ip": "192.168.1.100",  # Windows
            "port": 6881,
            "role": "tracker"
        },
        "peers": [
            {
                "name": "ubuntu_peer",
                "ip": "192.168.1.101",
                "port": 6882,
                "files": ["video1.mp4", "document1.pdf", "audio1.mp3"]
            },
            {
                "name": "mint_peer", 
                "ip": "192.168.1.102",
                "port": 6883,
                "files": ["video2.mp4", "document2.pdf", "audio2.mp3"]
            },
            {
                "name": "windows_peer",
                "ip": "192.168.1.103",
                "port": 6884,
                "files": ["video3.mp4", "document3.pdf", "audio3.mp3"]
            }
        ]
    }
    
    # Ajustar IPs según máquina actual
    current_ip = get_ip_address()
    
    print(f"🖥️  Máquina actual: {current_ip}")
    print("🔧 Configurando red BitTorrent...")
    
    # Guardar configuración
    with open('network_config.json', 'w') as f:
        json.dump(config, f, indent=2)
        
    # Crear directorios necesarios
    os.makedirs('shared_files', exist_ok=True)
    os.makedirs('downloads', exist_ok=True)
    
    print("✅ Configuración completada")
    print(f"📁 Archivo de configuración: network_config.json")
    
    return config

if __name__ == "__main__":
    configure_network()