#!/usr/bin/env python3
"""
Application de monitoring en temps réel pour 6 microphones STM32
Affiche les données RMS, MIN, MAX et crête-à-crête via UART
"""

import serial
import serial.tools.list_ports
import re
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
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, max_points=100):
        """
        Initialise le moniteur de microphones STM32

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
            'time': deque(maxlen=max_points),
            'rms': [deque(maxlen=max_points) for _ in range(self.num_mics)],
            'min': [deque(maxlen=max_points) for _ in range(self.num_mics)],
            'max': [deque(maxlen=max_points) for _ in range(self.num_mics)],
            'amplitude': [deque(maxlen=max_points) for _ in range(self.num_mics)]
        }

        self.serial_conn = None
        self.running = False
        self.thread = None
        self.start_time = time.time()
        self.sample_count = 0
        self.last_sample_time = time.time()
        self.sampling_freq = 0.0

        # Pattern pour parser les données UART
        # Format: "A0: MIN=  123 MAX=  456 AMP=123.456mV RMS=789.012mV"
        self.pattern = re.compile(
            r'A(\d):\s+MIN=\s*(-?\d+)\s+MAX=\s*(-?\d+)\s+AMP=(\d+)\.(\d+)mV\s+RMS=(\d+)\.(\d+)mV'
        )

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

    def parse_line(self, line):
        """Parse une ligne de données UART"""
        match = self.pattern.match(line)
        if match:
            mic_num = int(match.group(1))
            min_val = int(match.group(2))
            max_val = int(match.group(3))
            amp_int = int(match.group(4))
            amp_dec = int(match.group(5))
            rms_int = int(match.group(6))
            rms_dec = int(match.group(7))

            amplitude_mv = amp_int + amp_dec / 1000.0
            rms_mv = rms_int + rms_dec / 1000.0

            return {
                'mic': mic_num,
                'min': min_val,
                'max': max_val,
                'amplitude': amplitude_mv,
                'rms': rms_mv
            }
        return None

    def read_serial(self):
        """Thread de lecture des données série"""
        self.running = True
        data_buffer = [None] * self.num_mics

        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()

                    if line:
                        parsed = self.parse_line(line)
                        if parsed:
                            mic_num = parsed['mic']
                            data_buffer[mic_num] = parsed

                            # Si on a reçu toutes les données (A0-A5), on les stocke
                            if all(d is not None for d in data_buffer):
                                current_time = time.time() - self.start_time
                                self.data['time'].append(current_time)

                                for i, data_point in enumerate(data_buffer):
                                    self.data['rms'][i].append(data_point['rms'])
                                    self.data['min'][i].append(data_point['min'])
                                    self.data['max'][i].append(data_point['max'])
                                    self.data['amplitude'][i].append(data_point['amplitude'])

                                # Calcul de la fréquence d'échantillonnage
                                self.sample_count += 1
                                elapsed = time.time() - self.last_sample_time
                                if elapsed >= 1.0:  # Mise à jour chaque seconde
                                    self.sampling_freq = self.sample_count / elapsed
                                    self.sample_count = 0
                                    self.last_sample_time = time.time()

                                # Réinitialiser le buffer
                                data_buffer = [None] * self.num_mics

                time.sleep(0.001)  # Petite pause pour éviter de surcharger le CPU

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


class MonitorGUI:
    def __init__(self, root, monitor, refresh_rate=500):
        """Interface graphique pour le monitoring"""
        self.root = root
        self.monitor = monitor
        self.root.title("STM32 - Monitoring 6 Microphones")
        self.root.geometry("1400x900")

        # Vitesse de rafraîchissement (en millisecondes)
        self.refresh_rate = refresh_rate

        # Frame pour les informations en haut
        self.info_frame = tk.Frame(root)
        self.info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.time_label = tk.Label(self.info_frame, text="Heure: --:--:--",
                                   font=("Arial", 12, "bold"))
        self.time_label.pack(side=tk.LEFT, padx=20)

        self.freq_label = tk.Label(self.info_frame, text="Fréq. échantillonnage: 0.00 Hz",
                                   font=("Arial", 12, "bold"))
        self.freq_label.pack(side=tk.LEFT, padx=20)

        self.port_label = tk.Label(self.info_frame, text=f"Port: {monitor.port}",
                                   font=("Arial", 10))
        self.port_label.pack(side=tk.LEFT, padx=20)

        # Contrôle de la vitesse de rafraîchissement
        refresh_frame = tk.Frame(self.info_frame)
        refresh_frame.pack(side=tk.RIGHT, padx=20)

        tk.Label(refresh_frame, text="Rafraîchissement:", font=("Arial", 10)).pack(side=tk.LEFT)

        self.refresh_var = tk.IntVar(value=refresh_rate)
        self.refresh_scale = tk.Scale(
            refresh_frame,
            from_=100,
            to=2000,
            orient=tk.HORIZONTAL,
            variable=self.refresh_var,
            length=150,
            command=self.on_refresh_change
        )
        self.refresh_scale.pack(side=tk.LEFT, padx=5)

        self.refresh_label = tk.Label(refresh_frame, text=f"{refresh_rate}ms",
                                      font=("Arial", 10))
        self.refresh_label.pack(side=tk.LEFT)

        # Création des onglets
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Onglet 1: RMS de tous les micros
        self.create_tab_all_rms()

        # Onglet 2: MAX et MIN de tous les micros
        self.create_tab_all_minmax()

        # Onglet 3: Crête-à-crête de tous les micros
        self.create_tab_all_amplitude()

        # Onglets 4-9: Vues détaillées par micro
        for mic_num in range(6):
            self.create_tab_single_mic(mic_num)

        # Démarrer les mises à jour
        self.update_plots()
        self.update_info()

    def create_tab_all_rms(self):
        """Onglet 1: 6 graphes RMS"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="RMS - Tous les micros")

        fig = Figure(figsize=(14, 8))
        self.rms_axes = []

        for i in range(6):
            ax = fig.add_subplot(3, 2, i+1)
            ax.set_title(f'Microphone A{i} - RMS', fontweight='bold')
            ax.set_xlabel('Temps (s)')
            ax.set_ylabel('RMS (mV)')
            ax.grid(True, alpha=0.3)
            self.rms_axes.append(ax)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.rms_canvas = canvas

    def create_tab_all_minmax(self):
        """Onglet 2: 6 graphes MAX et MIN"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="MAX/MIN - Tous les micros")

        fig = Figure(figsize=(14, 8))
        self.minmax_axes = []

        for i in range(6):
            ax = fig.add_subplot(3, 2, i+1)
            ax.set_title(f'Microphone A{i} - MAX/MIN', fontweight='bold')
            ax.set_xlabel('Temps (s)')
            ax.set_ylabel('Valeur ADC')
            ax.grid(True, alpha=0.3)
            self.minmax_axes.append(ax)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.minmax_canvas = canvas

    def create_tab_all_amplitude(self):
        """Onglet 3: 6 graphes crête-à-crête"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Crête-à-crête - Tous les micros")

        fig = Figure(figsize=(14, 8))
        self.amplitude_axes = []

        for i in range(6):
            ax = fig.add_subplot(3, 2, i+1)
            ax.set_title(f'Microphone A{i} - Amplitude', fontweight='bold')
            ax.set_xlabel('Temps (s)')
            ax.set_ylabel('Amplitude (mV)')
            ax.grid(True, alpha=0.3)
            self.amplitude_axes.append(ax)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.amplitude_canvas = canvas

    def create_tab_single_mic(self, mic_num):
        """Onglets 4-9: Vue détaillée d'un microphone"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=f"Micro A{mic_num}")

        fig = Figure(figsize=(14, 8))

        # RMS en haut à gauche
        ax1 = fig.add_subplot(2, 2, 1)
        ax1.set_title(f'A{mic_num} - RMS', fontweight='bold')
        ax1.set_xlabel('Temps (s)')
        ax1.set_ylabel('RMS (mV)')
        ax1.grid(True, alpha=0.3)

        # Crête-à-crête en bas à gauche
        ax2 = fig.add_subplot(2, 2, 3)
        ax2.set_title(f'A{mic_num} - Crête-à-crête', fontweight='bold')
        ax2.set_xlabel('Temps (s)')
        ax2.set_ylabel('Amplitude (mV)')
        ax2.grid(True, alpha=0.3)

        # MAX en haut à droite
        ax3 = fig.add_subplot(2, 2, 2)
        ax3.set_title(f'A{mic_num} - MAX', fontweight='bold')
        ax3.set_xlabel('Temps (s)')
        ax3.set_ylabel('MAX (ADC)')
        ax3.grid(True, alpha=0.3)

        # MIN en bas à droite
        ax4 = fig.add_subplot(2, 2, 4)
        ax4.set_title(f'A{mic_num} - MIN', fontweight='bold')
        ax4.set_xlabel('Temps (s)')
        ax4.set_ylabel('MIN (ADC)')
        ax4.grid(True, alpha=0.3)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Stocker les axes et canvas pour la mise à jour
        if not hasattr(self, 'single_mic_axes'):
            self.single_mic_axes = []
            self.single_mic_canvas = []
        self.single_mic_axes.append([ax1, ax2, ax3, ax4])
        self.single_mic_canvas.append(canvas)

    def update_plots(self):
        """Mise à jour périodique des graphes"""
        if len(self.monitor.data['time']) > 0:
            times = list(self.monitor.data['time'])

            # Mise à jour onglet RMS
            for i, ax in enumerate(self.rms_axes):
                ax.clear()
                ax.set_title(f'Microphone A{i} - RMS', fontweight='bold')
                ax.set_xlabel('Temps (s)')
                ax.set_ylabel('RMS (mV)')
                ax.grid(True, alpha=0.3)
                if len(self.monitor.data['rms'][i]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['rms'][i]))
                    ax.plot(times[:data_len], list(self.monitor.data['rms'][i])[:data_len],
                           'b-', linewidth=1.5)
            self.rms_canvas.draw()

            # Mise à jour onglet MAX/MIN
            for i, ax in enumerate(self.minmax_axes):
                ax.clear()
                ax.set_title(f'Microphone A{i} - MAX/MIN', fontweight='bold')
                ax.set_xlabel('Temps (s)')
                ax.set_ylabel('Valeur ADC')
                ax.grid(True, alpha=0.3)
                if len(self.monitor.data['max'][i]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['max'][i]),
                                  len(self.monitor.data['min'][i]))
                    ax.plot(times[:data_len], list(self.monitor.data['max'][i])[:data_len],
                           'r-', linewidth=1.5, label='MAX')
                    ax.plot(times[:data_len], list(self.monitor.data['min'][i])[:data_len],
                           'g-', linewidth=1.5, label='MIN')
                    ax.legend()
            self.minmax_canvas.draw()

            # Mise à jour onglet amplitude
            for i, ax in enumerate(self.amplitude_axes):
                ax.clear()
                ax.set_title(f'Microphone A{i} - Amplitude', fontweight='bold')
                ax.set_xlabel('Temps (s)')
                ax.set_ylabel('Amplitude (mV)')
                ax.grid(True, alpha=0.3)
                if len(self.monitor.data['amplitude'][i]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['amplitude'][i]))
                    ax.plot(times[:data_len], list(self.monitor.data['amplitude'][i])[:data_len],
                           'purple', linewidth=1.5)
            self.amplitude_canvas.draw()

            # Mise à jour des vues individuelles
            for mic_num, axes in enumerate(self.single_mic_axes):
                ax_rms, ax_amp, ax_max, ax_min = axes

                # RMS
                ax_rms.clear()
                ax_rms.set_title(f'A{mic_num} - RMS', fontweight='bold')
                ax_rms.set_xlabel('Temps (s)')
                ax_rms.set_ylabel('RMS (mV)')
                ax_rms.grid(True, alpha=0.3)
                if len(self.monitor.data['rms'][mic_num]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['rms'][mic_num]))
                    ax_rms.plot(times[:data_len], list(self.monitor.data['rms'][mic_num])[:data_len],
                               'b-', linewidth=1.5)

                # Crête-à-crête
                ax_amp.clear()
                ax_amp.set_title(f'A{mic_num} - Crête-à-crête', fontweight='bold')
                ax_amp.set_xlabel('Temps (s)')
                ax_amp.set_ylabel('Amplitude (mV)')
                ax_amp.grid(True, alpha=0.3)
                if len(self.monitor.data['amplitude'][mic_num]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['amplitude'][mic_num]))
                    ax_amp.plot(times[:data_len], list(self.monitor.data['amplitude'][mic_num])[:data_len],
                               'purple', linewidth=1.5)

                # MAX
                ax_max.clear()
                ax_max.set_title(f'A{mic_num} - MAX', fontweight='bold')
                ax_max.set_xlabel('Temps (s)')
                ax_max.set_ylabel('MAX (ADC)')
                ax_max.grid(True, alpha=0.3)
                if len(self.monitor.data['max'][mic_num]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['max'][mic_num]))
                    ax_max.plot(times[:data_len], list(self.monitor.data['max'][mic_num])[:data_len],
                               'r-', linewidth=1.5)

                # MIN
                ax_min.clear()
                ax_min.set_title(f'A{mic_num} - MIN', fontweight='bold')
                ax_min.set_xlabel('Temps (s)')
                ax_min.set_ylabel('MIN (ADC)')
                ax_min.grid(True, alpha=0.3)
                if len(self.monitor.data['min'][mic_num]) > 0:
                    # Synchroniser les longueurs
                    data_len = min(len(times), len(self.monitor.data['min'][mic_num]))
                    ax_min.plot(times[:data_len], list(self.monitor.data['min'][mic_num])[:data_len],
                               'g-', linewidth=1.5)

                self.single_mic_canvas[mic_num].draw()

        # Programmer la prochaine mise à jour
        self.root.after(self.refresh_rate, self.update_plots)

    def on_refresh_change(self, value):
        """Callback quand le slider de rafraîchissement change"""
        self.refresh_rate = int(value)
        self.refresh_label.config(text=f"{self.refresh_rate}ms")

    def update_info(self):
        """Mise à jour des informations d'en-tête"""
        # Heure actuelle
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=f"Heure: {current_time}")

        # Fréquence d'échantillonnage
        self.freq_label.config(text=f"Fréq. échantillonnage: {self.monitor.sampling_freq:.2f} Hz")

        # Programmer la prochaine mise à jour
        self.root.after(100, self.update_info)  # Mise à jour toutes les 100ms


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
        default=100,
        help='Nombre de points à afficher (défaut: 100)'
    )
    parser.add_argument(
        '--refresh',
        type=int,
        default=500,
        help='Vitesse de rafraîchissement des graphiques en ms (défaut: 500, min: 100, max: 2000)'
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

    # Valider la vitesse de rafraîchissement
    refresh_rate = max(100, min(2000, args.refresh))
    if refresh_rate != args.refresh:
        print(f"⚠️  Vitesse de rafraîchissement ajustée à {refresh_rate}ms (limites: 100-2000ms)")

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
