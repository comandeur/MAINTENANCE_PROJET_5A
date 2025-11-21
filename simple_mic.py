#!/usr/bin/env python3
"""Version simplifiée pour test - Données binaires 1KHz (6 x int16_t)"""

import serial
import serial.tools.list_ports
import struct
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# Configuration
BAUDRATE = 115200
MAX_POINTS = 1000
BYTES_PER_SAMPLE = 12  # 6 × int16_t = 12 bytes

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
print("Connecté! En attente des données binaires (6 × int16_t = 12 bytes)...")

# Buffers pour visualisation
data_buffers = [deque(maxlen=MAX_POINTS) for _ in range(6)]
time_buffer = deque(maxlen=MAX_POINTS)  # Temps en secondes
sample_count = 0
SAMPLE_PERIOD = 0.001  # 1KHz = 1ms par échantillon

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
    global sample_count

    # Lire tous les échantillons disponibles
    bytes_available = ser.in_waiting
    samples_to_read = bytes_available // BYTES_PER_SAMPLE

    if samples_to_read > 0:
        raw = ser.read(samples_to_read * BYTES_PER_SAMPLE)

        # Décoder chaque échantillon
        for s in range(samples_to_read):
            offset = s * BYTES_PER_SAMPLE
            values = struct.unpack('<6h', raw[offset:offset + BYTES_PER_SAMPLE])

            # Temps cumulatif en secondes
            time_buffer.append(sample_count * SAMPLE_PERIOD)

            for i in range(6):
                data_buffers[i].append(values[i])

            sample_count += 1

        # Mettre à jour les graphiques
        times = list(time_buffer)
        for i, line in enumerate(lines):
            if len(data_buffers[i]) > 0:
                line.set_data(times, list(data_buffers[i]))
                axes[i].relim()
                axes[i].autoscale_view()

        # Afficher stats toutes les 100 frames
        if frame % 100 == 0:
            fig.suptitle(f'Monitoring 6 canaux - {sample_count} samples reçus')

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
