#!/usr/bin/env python3
"""Version simplifiée pour test - Données binaires 1KHz (6 x int16_t)"""

import serial
import serial.tools.list_ports
import struct
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# Configuration
BAUDRATE = 921600
MAX_POINTS = 1000
BYTES_PER_SAMPLE = 13  # 1 header + 6 × int16_t = 13 bytes
HEADER_BYTE = 0xAA

def find_serial_port():
    """Détection automatique du port série"""
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("Aucun port série détecté!")
        return None

    print("Ports disponibles:")
    for i, port in enumerate(ports):
        print(f"  {i}: {port.device} - {port.description}")

    if len(ports) == 1:
        print(f"\nUtilisation automatique: {ports[0].device}")
        return ports[0].device

    try:
        choice = int(input("\nChoisir le numéro du port: "))
        return ports[choice].device
    except (ValueError, IndexError):
        print("Choix invalide, utilisation du premier port")
        return ports[0].device

# Trouver le port
port = find_serial_port()
if not port:
    exit(1)

# Ouvrir le port série
print(f"Connexion à {port} @ {BAUDRATE} bauds...")
ser = serial.Serial(port, BAUDRATE, timeout=0.1)
print("Connecté! En attente des données binaires (header 0xAA + 6 × int16_t = 13 bytes)...")

# Buffers pour visualisation
data_buffers = [deque(maxlen=MAX_POINTS) for _ in range(6)]
time_buffer = deque(maxlen=MAX_POINTS)  # Temps en secondes
sample_count = 0
skipped_bytes = 0
aligned = False  # True quand l'alignement sur les paquets est confirmé
SAMPLE_PERIOD = 0.001  # 1KHz = 1ms par échantillon
recv_buffer = bytearray()  # Buffer de réception pour synchronisation

# Créer la figure
fig, axes = plt.subplots(2, 3, figsize=(12, 6))
axes = axes.flatten()
lines = []

for i, ax in enumerate(axes):
    line, = ax.plot([], [], 'b-', linewidth=0.8)
    lines.append(line)
    ax.set_title(f'Canal A{i}')
    ax.set_xlabel('Temps (s)')
    ax.grid(True, alpha=0.3)

fig.suptitle('Monitoring 6 canaux - Binaire 1KHz')
plt.tight_layout()

def update(frame):
    global sample_count, recv_buffer, skipped_bytes, aligned

    # Lire tous les octets disponibles dans le buffer
    bytes_available = ser.in_waiting
    if bytes_available > 0:
        recv_buffer.extend(ser.read(bytes_available))

    # Scanner le buffer octet par octet
    decoded = False
    while len(recv_buffer) > 0:
        if recv_buffer[0] != HEADER_BYTE:
            # Octet parasite : on le jette
            aligned = False
            skipped_bytes += 1
            recv_buffer.pop(0)
            continue

        # Header 0xAA trouvé - assez de bytes pour un paquet complet ?
        if len(recv_buffer) < BYTES_PER_SAMPLE:
            break  # Attendre plus de données

        # Si pas encore aligné, valider avec double-header
        if not aligned:
            if len(recv_buffer) < BYTES_PER_SAMPLE + 1:
                break  # Attendre le byte suivant pour valider
            if recv_buffer[BYTES_PER_SAMPLE] != HEADER_BYTE:
                # Faux 0xAA dans les données - on le saute
                recv_buffer.pop(0)
                skipped_bytes += 1
                continue
            aligned = True

        # Extraire le paquet de 13 bytes
        packet = recv_buffer[:BYTES_PER_SAMPLE]
        recv_buffer = recv_buffer[BYTES_PER_SAMPLE:]

        # Décoder les 6 valeurs int16_t
        values = struct.unpack('<6h', packet[1:13])

        # Temps cumulatif en secondes
        time_buffer.append(sample_count * SAMPLE_PERIOD)

        for i in range(6):
            data_buffers[i].append(values[i])

        sample_count += 1
        decoded = True

    if decoded:
        # Mettre à jour les graphiques
        times = list(time_buffer)
        for i, line in enumerate(lines):
            if len(data_buffers[i]) > 0:
                line.set_data(times, list(data_buffers[i]))
                axes[i].relim()
                axes[i].autoscale_view()

        # Afficher stats toutes les 100 frames
        if frame % 100 == 0:
            fig.suptitle(f'Monitoring 6 canaux - {sample_count} samples ({skipped_bytes} octets ignorés)')

    return lines

# Animation
ani = FuncAnimation(fig, update, interval=10, blit=False, cache_frame_data=False)

try:
    plt.show()
except KeyboardInterrupt:
    pass
finally:
    ser.close()
    print(f"\nTotal: {sample_count} échantillons reçus")
