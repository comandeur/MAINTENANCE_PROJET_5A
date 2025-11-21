#!/usr/bin/env python3
"""
Version simplifiée pour test - Affichage des 6 microphones
"""

import serial
import serial.tools.list_ports
import re
import time
import matplotlib.pyplot as plt
from collections import deque

# Configuration
BAUDRATE = 115200
MAX_POINTS = 200

# Pattern pour parser les données
PATTERN = re.compile(
    r'A(\d):\s+MIN=\s*(-?\d+)\s+MAX=\s*(-?\d+)\s+AMP=(\d+)\.(\d+)mV\s+RMS=(\d+)\.(\d+)mV'
)

def find_port():
    """Trouve automatiquement le port série"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("Aucun port trouvé!")
        return None
    if len(ports) == 1:
        print(f"Port: {ports[0].device}")
        return ports[0].device
    print("Ports disponibles:")
    for i, p in enumerate(ports, 1):
        print(f"  {i}. {p.device} - {p.description}")
    choice = input("Choix (numéro): ")
    return ports[int(choice)-1].device

def parse_line(line):
    """Parse une ligne UART"""
    match = PATTERN.match(line)
    if match:
        mic = int(match.group(1))
        amp = int(match.group(4)) + int(match.group(5)) / 1000.0
        rms = int(match.group(6)) + int(match.group(7)) / 1000.0
        return mic, rms, amp
    return None

def main():
    # Trouver le port
    port = find_port()
    if not port:
        return

    # Connexion
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=0.1)
        print(f"Connecté à {port}")
    except Exception as e:
        print(f"Erreur: {e}")
        return

    # Données pour 6 micros
    times = [deque(maxlen=MAX_POINTS) for _ in range(6)]
    rms_data = [deque(maxlen=MAX_POINTS) for _ in range(6)]
    amp_data = [deque(maxlen=MAX_POINTS) for _ in range(6)]

    # Créer la figure avec 6 graphes RMS
    plt.ion()
    fig, axes = plt.subplots(3, 2, figsize=(12, 8))
    axes = axes.flatten()

    lines = []
    for i, ax in enumerate(axes):
        line, = ax.plot([], [], 'b-', linewidth=1)
        lines.append(line)
        ax.set_title(f'Micro A{i} - RMS')
        ax.set_xlabel('Temps (s)')
        ax.set_ylabel('RMS (mV)')
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    plt.show(block=False)

    start_time = time.time()
    sample_count = 0
    last_print = time.time()

    print("\nLecture en cours... (Ctrl+C pour quitter)\n")

    try:
        while True:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    # Debug: afficher la ligne
                    if sample_count < 5:
                        print(f"[RAW] {line}")

                    result = parse_line(line)
                    if result:
                        mic, rms, amp = result
                        t = time.time() - start_time

                        times[mic].append(t)
                        rms_data[mic].append(rms)
                        amp_data[mic].append(amp)

                        sample_count += 1

            # Mise à jour des graphes toutes les 200ms
            if time.time() - last_print > 0.2:
                for i in range(6):
                    if len(times[i]) > 0:
                        lines[i].set_data(list(times[i]), list(rms_data[i]))
                        axes[i].relim()
                        axes[i].autoscale_view()

                fig.canvas.draw()
                fig.canvas.flush_events()

                # Afficher stats
                elapsed = time.time() - start_time
                freq = sample_count / elapsed if elapsed > 0 else 0
                print(f"\rSamples: {sample_count} | Freq: {freq:.1f} Hz | Temps: {elapsed:.1f}s", end="")

                last_print = time.time()

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n\nArrêt...")
    finally:
        ser.close()
        plt.close()
        print("Terminé.")

if __name__ == "__main__":
    main()
