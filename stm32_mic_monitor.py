#!/usr/bin/env python3
"""
Application de monitoring en temps réel pour 6 microphones STM32
Format binaire: 6 x int16_t (12 bytes) a 1KHz via UART
"""

import serial
import serial.tools.list_ports
import struct
import threading
import time
from datetime import datetime
from collections import deque
import tkinter as tk
from tkinter import ttk, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np


class STM32MicMonitor:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, max_points=1000):
        """
        Initialise le moniteur de microphones STM32
        Format binaire: 6 × int16_t = 12 bytes par échantillon à 1KHz

        Args:
            port: Port série (ex: '/dev/ttyUSB0' sous Linux, 'COM3' sous Windows)
            baudrate: Vitesse de communication (doit correspondre à la STM32)
            max_points: Nombre maximum de points à afficher sur les graphes
        """
        self.port = port
        self.baudrate = baudrate
        self.max_points = max_points

        # Données pour chaque microphone (A0-A5)
        self.num_mics = 6
        self.data = {
            'time': deque(maxlen=max_points),  # Temps commun à tous les canaux
            'values': [deque(maxlen=max_points) for _ in range(self.num_mics)]  # Valeurs filtrées
        }

        self.serial_conn = None
        self.running = False
        self.thread = None
        self.sample_count = 0
        self.last_freq_time = time.time()
        self.last_freq_count = 0
        self.sampling_freq = 0.0

        # Format binaire: 12 bytes = 6 × int16_t
        self.BYTES_PER_SAMPLE = 12
        self.SAMPLE_PERIOD = 0.001  # 1KHz = 1ms

    def connect(self):
        """Établit la connexion série avec la STM32"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )
            print(f"Connecté à {self.port} à {self.baudrate} bauds")
            return True
        except serial.SerialException as e:
            print(f"Erreur de connexion série: {e}")
            return False

    def disconnect(self):
        """Ferme la connexion série"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Connexion série fermée")

    def read_serial(self):
        """Thread de lecture des données série (format binaire)"""
        self.running = True
        self.debug_count = 0

        while self.running:
            try:
                if self.serial_conn:
                    bytes_available = self.serial_conn.in_waiting
                    samples_to_read = bytes_available // self.BYTES_PER_SAMPLE

                    if samples_to_read > 0:
                        raw = self.serial_conn.read(samples_to_read * self.BYTES_PER_SAMPLE)

                        # Décoder chaque échantillon
                        for s in range(samples_to_read):
                            offset = s * self.BYTES_PER_SAMPLE
                            values = struct.unpack('<6h', raw[offset:offset + self.BYTES_PER_SAMPLE])

                            # Debug: afficher les premiers échantillons
                            if self.debug_count < 5:
                                print(f"[DEBUG] Sample {self.sample_count}: {values}")
                                self.debug_count += 1

                            # Temps cumulatif en secondes
                            self.data['time'].append(self.sample_count * self.SAMPLE_PERIOD)

                            # Stocker les valeurs pour chaque canal
                            for i in range(6):
                                self.data['values'][i].append(values[i])

                            self.sample_count += 1

                        # Calcul de la fréquence d'échantillonnage
                        now = time.time()
                        elapsed = now - self.last_freq_time
                        if elapsed >= 1.0:
                            samples_since = self.sample_count - self.last_freq_count
                            self.sampling_freq = samples_since / elapsed
                            self.last_freq_count = self.sample_count
                            self.last_freq_time = now

                time.sleep(0.001)

            except Exception as e:
                print(f"Erreur de lecture série: {e}")
                time.sleep(0.1)

    def start_reading(self):
        """Démarre le thread de lecture série"""
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.read_serial, daemon=True)
            self.thread.start()
            print("Thread de lecture démarré")

    def stop_reading(self):
        """Arrête le thread de lecture série"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            print("Thread de lecture arrêté")

    def clear_data(self):
        """Vide toutes les données collectées"""
        self.data['time'].clear()
        for i in range(self.num_mics):
            self.data['values'][i].clear()
        self.sample_count = 0
        self.last_freq_count = 0
        print("Donnees reinitialisees")


class MonitorGUI:
    def __init__(self, root, monitor, refresh_rate=50):
        """Interface graphique pour le monitoring - Format binaire 1KHz"""
        self.root = root
        self.monitor = monitor
        self.root.title("STM32 - Monitoring 6 Microphones (Binaire 1KHz)")
        self.root.geometry("1200x800")

        # Vitesse de rafraîchissement (en millisecondes)
        self.refresh_rate = refresh_rate

        # Frame pour les informations en haut
        self.info_frame = tk.Frame(root)
        self.info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.time_label = tk.Label(self.info_frame, text="Heure: --:--:--",
                                   font=("Arial", 12, "bold"))
        self.time_label.pack(side=tk.LEFT, padx=20)

        self.freq_label = tk.Label(self.info_frame, text="Freq: 0 Hz",
                                   font=("Arial", 12, "bold"))
        self.freq_label.pack(side=tk.LEFT, padx=20)

        self.samples_label = tk.Label(self.info_frame, text="Samples: 0",
                                      font=("Arial", 12))
        self.samples_label.pack(side=tk.LEFT, padx=20)

        self.port_label = tk.Label(self.info_frame, text=f"Port: {monitor.port}",
                                   font=("Arial", 10))
        self.port_label.pack(side=tk.LEFT, padx=20)

        # Frame pour les controles
        ctrl_frame = tk.Frame(self.info_frame)
        ctrl_frame.pack(side=tk.RIGHT, padx=10)

        # Bouton Vider
        self.clear_button = tk.Button(
            ctrl_frame,
            text="Vider",
            command=self.clear_all_graphs,
            font=("Arial", 10),
            bg="#ff6b6b",
            fg="white",
            padx=10
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Toggle auto/manuel (defaut: auto)
        self.auto_scale = tk.BooleanVar(value=True)
        self.scale_button = tk.Button(
            ctrl_frame,
            text="Auto",
            command=self.toggle_scale_mode,
            font=("Arial", 10),
            bg="#28a745",
            fg="white",
            padx=8
        )
        self.scale_button.pack(side=tk.LEFT, padx=5)

        # Controles echelle manuelle
        tk.Label(ctrl_frame, text="Y:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 2))
        self.y_min_var = tk.StringVar(value="-2048")
        self.y_min_entry = tk.Entry(ctrl_frame, textvariable=self.y_min_var, width=6, font=("Arial", 9))
        self.y_min_entry.pack(side=tk.LEFT)
        self.y_min_entry.config(state='disabled')

        tk.Label(ctrl_frame, text="a", font=("Arial", 9)).pack(side=tk.LEFT, padx=2)
        self.y_max_var = tk.StringVar(value="2048")
        self.y_max_entry = tk.Entry(ctrl_frame, textvariable=self.y_max_var, width=6, font=("Arial", 9))
        self.y_max_entry.pack(side=tk.LEFT)
        self.y_max_entry.config(state='disabled')

        # Base de temps
        tk.Label(ctrl_frame, text="Fenetre:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(15, 2))
        self.time_window_var = tk.StringVar(value="1")
        self.time_window_entry = tk.Entry(ctrl_frame, textvariable=self.time_window_var, width=4, font=("Arial", 9))
        self.time_window_entry.pack(side=tk.LEFT)
        tk.Label(ctrl_frame, text="s", font=("Arial", 9)).pack(side=tk.LEFT, padx=2)

        # Creation des onglets
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Onglet 1: Vue 6 canaux (glissant)
        self.create_tab_all_channels()

        # Onglets 2-7: Vue individuelle par canal (cumulatif)
        self.single_axes = []
        self.single_lines = []
        self.single_canvas = []
        for i in range(6):
            self.create_tab_single_channel(i)

        # Demarrer les mises a jour
        self.update_plots()
        self.update_info()

    def create_tab_all_channels(self):
        """Onglet avec les 6 canaux en vue glissante"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="6 Canaux (glissant)")

        self.fig_all = Figure(figsize=(12, 7))
        self.axes_all = []
        self.lines_all = []

        for i in range(6):
            ax = self.fig_all.add_subplot(2, 3, i+1)
            ax.set_title(f'Canal A{i}', fontweight='bold')
            ax.set_xlabel('Temps (s)')
            ax.set_ylabel('Valeur')
            ax.grid(True, alpha=0.3)
            self.axes_all.append(ax)

            line, = ax.plot([], [], 'b-', linewidth=0.8)
            self.lines_all.append(line)

        self.fig_all.tight_layout()
        self.canvas_all = FigureCanvasTkAgg(self.fig_all, tab)
        self.canvas_all.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_tab_single_channel(self, channel_num):
        """Onglet individuel pour un canal (vue cumulative)"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=f"A{channel_num}")

        fig = Figure(figsize=(12, 7))
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title(f'Canal A{channel_num} - Vue cumulative', fontweight='bold', fontsize=14)
        ax.set_xlabel('Temps (s)', fontsize=12)
        ax.set_ylabel('Valeur', fontsize=12)
        ax.grid(True, alpha=0.3)

        line, = ax.plot([], [], 'b-', linewidth=0.8)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.single_axes.append(ax)
        self.single_lines.append(line)
        self.single_canvas.append(canvas)

    def update_plots(self):
        """Mise a jour periodique des graphes"""
        if len(self.monitor.data['time']) > 0:
            times = list(self.monitor.data['time'])
            current_time = times[-1] if times else 0

            # Onglet actif
            current_tab = self.notebook.index(self.notebook.select())

            # Onglet 0: Vue 6 canaux (glissant)
            if current_tab == 0:
                try:
                    time_window = float(self.time_window_var.get())
                except ValueError:
                    time_window = 1.0

                for i in range(6):
                    if len(self.monitor.data['values'][i]) > 0:
                        values = list(self.monitor.data['values'][i])
                        self.lines_all[i].set_data(times[:len(values)], values)

                        # Echelle Y
                        if self.auto_scale.get():
                            self.axes_all[i].relim()
                            self.axes_all[i].autoscale_view()
                        else:
                            try:
                                y_min = float(self.y_min_var.get())
                                y_max = float(self.y_max_var.get())
                                self.axes_all[i].set_ylim(y_min, y_max)
                            except ValueError:
                                pass

                        # Echelle X (fenetre glissante)
                        x_min = max(0, current_time - time_window)
                        x_max = max(time_window, current_time)
                        self.axes_all[i].set_xlim(x_min, x_max)

                self.canvas_all.draw()

            # Onglets 1-6: Vue individuelle (cumulatif)
            elif 1 <= current_tab <= 6:
                channel = current_tab - 1
                if len(self.monitor.data['values'][channel]) > 0:
                    values = list(self.monitor.data['values'][channel])
                    self.single_lines[channel].set_data(times[:len(values)], values)

                    # Echelle Y
                    if self.auto_scale.get():
                        self.single_axes[channel].relim()
                        self.single_axes[channel].autoscale_view()
                    else:
                        try:
                            y_min = float(self.y_min_var.get())
                            y_max = float(self.y_max_var.get())
                            self.single_axes[channel].set_ylim(y_min, y_max)
                        except ValueError:
                            pass

                    # Echelle X cumulative (tout l'historique)
                    self.single_axes[channel].set_xlim(0, max(current_time, 0.1))

                self.single_canvas[channel].draw()

        # Programmer la prochaine mise a jour
        self.root.after(self.refresh_rate, self.update_plots)

    def toggle_scale_mode(self):
        """Bascule entre echelle auto et manuelle"""
        self.auto_scale.set(not self.auto_scale.get())
        if self.auto_scale.get():
            self.scale_button.config(text="Auto", bg="#28a745")
            self.y_min_entry.config(state='disabled')
            self.y_max_entry.config(state='disabled')
        else:
            self.scale_button.config(text="Manuel", bg="#4a90d9")
            self.y_min_entry.config(state='normal')
            self.y_max_entry.config(state='normal')

    def clear_all_graphs(self):
        """Vide toutes les donnees des graphes"""
        self.monitor.clear_data()
        print("Graphes vides")

    def update_info(self):
        """Mise a jour des informations d'en-tete"""
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=f"Heure: {current_time}")
        self.freq_label.config(text=f"Freq: {self.monitor.sampling_freq:.0f} Hz")
        self.samples_label.config(text=f"Samples: {self.monitor.sample_count}")

        self.root.after(200, self.update_info)


def detect_and_select_port():
    """
    Détecte automatiquement les ports série disponibles et demande à l'utilisateur
    de choisir si plusieurs ports sont trouvés.

    Returns:
        str: Le port sélectionné, ou None si aucun port n'est disponible
    """
    print("\n🔍 Recherche des ports série disponibles...\n")

    # Lister tous les ports disponibles
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("❌ Aucun port série détecté!")
        print("\n⚠️  Vérifiez que:")
        print("   - Votre carte STM32 est bien branchée via USB")
        print("   - Les drivers STM32 sont installés")
        print("   - Le câble USB fonctionne correctement")
        return None

    # Si un seul port est trouvé, l'utiliser automatiquement
    if len(ports) == 1:
        selected_port = ports[0].device
        print(f"✅ Port détecté automatiquement: {selected_port}")
        print(f"   Description: {ports[0].description}")
        if ports[0].manufacturer:
            print(f"   Fabricant: {ports[0].manufacturer}")
        print()
        return selected_port

    # Si plusieurs ports sont trouvés, demander à l'utilisateur
    print(f"📡 {len(ports)} ports série détectés:\n")
    print("-" * 80)

    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device}")
        print(f"   Description: {port.description}")
        if port.manufacturer:
            print(f"   Fabricant:   {port.manufacturer}")
        if port.hwid:
            print(f"   Hardware ID: {port.hwid}")
        print("-" * 80)

    # Demander à l'utilisateur de choisir
    while True:
        try:
            choice = input(f"\n👉 Choisissez un port (1-{len(ports)}) ou 'q' pour quitter: ").strip()

            if choice.lower() == 'q':
                print("❌ Annulé par l'utilisateur")
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(ports):
                selected_port = ports[choice_num - 1].device
                print(f"\n✅ Port sélectionné: {selected_port}\n")
                return selected_port
            else:
                print(f"⚠️  Veuillez entrer un nombre entre 1 et {len(ports)}")
        except ValueError:
            print("⚠️  Entrée invalide. Veuillez entrer un nombre ou 'q'")
        except KeyboardInterrupt:
            print("\n❌ Annulé par l'utilisateur")
            return None


def main():
    """Point d'entrée principal"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitoring en temps réel de 6 microphones STM32"
    )
    parser.add_argument(
        '--port',
        default=None,
        help='Port série (ex: /dev/ttyUSB0, COM3). Si non spécifié, détection automatique.'
    )
    parser.add_argument(
        '--baudrate',
        type=int,
        default=115200,
        help='Vitesse de communication (défaut: 115200)'
    )
    parser.add_argument(
        '--points',
        type=int,
        default=1000,
        help='Nombre de points a afficher (defaut: 1000 = 1s a 1KHz)'
    )
    parser.add_argument(
        '--refresh',
        type=int,
        default=50,
        help='Vitesse de rafraichissement en ms (defaut: 50)'
    )

    args = parser.parse_args()

    # Détection automatique du port si non spécifié
    port_to_use = args.port
    if port_to_use is None:
        port_to_use = detect_and_select_port()
        if port_to_use is None:
            print("\n❌ Impossible de continuer sans port série.")
            print("\n💡 Vous pouvez spécifier manuellement un port avec:")
            print("   python stm32_mic_monitor.py --port COM3")
            return

    # Créer le moniteur
    monitor = STM32MicMonitor(
        port=port_to_use,
        baudrate=args.baudrate,
        max_points=args.points
    )

    # Connexion série
    if not monitor.connect():
        print("❌ Impossible de se connecter au port série!")
        print(f"   Port utilisé: {port_to_use}")
        print("\n⚠️  Vérifiez que:")
        print("   - La carte STM32 est bien branchée")
        print("   - Les drivers sont installés")
        print("   - Aucun autre programme n'utilise le port (Arduino IDE, PuTTY, etc.)")
        print("   - Le câble USB fonctionne correctement")
        print("\n💡 Essayez de:")
        print("   - Débrancher et rebrancher la carte")
        print("   - Relancer l'application (elle redétectera les ports)")
        return

    # Démarrer la lecture
    monitor.start_reading()

    # Vitesse de rafraichissement
    refresh_rate = max(10, min(1000, args.refresh))

    # Créer l'interface graphique
    root = tk.Tk()
    gui = MonitorGUI(root, monitor, refresh_rate=refresh_rate)

    def on_closing():
        """Nettoyage lors de la fermeture"""
        monitor.stop_reading()
        monitor.disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nInterruption par l'utilisateur")
        on_closing()


if __name__ == "__main__":
    main()
