#!/usr/bin/env python3
"""
Application de monitoring en temps réel pour 6 microphones STM32
Affiche les données RMS, MIN, MAX et crête-à-crête via UART
"""

import serial
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
    def __init__(self, root, monitor):
        """Interface graphique pour le monitoring"""
        self.root = root
        self.monitor = monitor
        self.root.title("STM32 - Monitoring 6 Microphones")
        self.root.geometry("1400x900")

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
                    ax.plot(times, list(self.monitor.data['rms'][i]), 'b-', linewidth=1.5)
            self.rms_canvas.draw()

            # Mise à jour onglet MAX/MIN
            for i, ax in enumerate(self.minmax_axes):
                ax.clear()
                ax.set_title(f'Microphone A{i} - MAX/MIN', fontweight='bold')
                ax.set_xlabel('Temps (s)')
                ax.set_ylabel('Valeur ADC')
                ax.grid(True, alpha=0.3)
                if len(self.monitor.data['max'][i]) > 0:
                    ax.plot(times, list(self.monitor.data['max'][i]), 'r-',
                           linewidth=1.5, label='MAX')
                    ax.plot(times, list(self.monitor.data['min'][i]), 'g-',
                           linewidth=1.5, label='MIN')
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
                    ax.plot(times, list(self.monitor.data['amplitude'][i]),
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
                    ax_rms.plot(times, list(self.monitor.data['rms'][mic_num]),
                               'b-', linewidth=1.5)

                # Crête-à-crête
                ax_amp.clear()
                ax_amp.set_title(f'A{mic_num} - Crête-à-crête', fontweight='bold')
                ax_amp.set_xlabel('Temps (s)')
                ax_amp.set_ylabel('Amplitude (mV)')
                ax_amp.grid(True, alpha=0.3)
                if len(self.monitor.data['amplitude'][mic_num]) > 0:
                    ax_amp.plot(times, list(self.monitor.data['amplitude'][mic_num]),
                               'purple', linewidth=1.5)

                # MAX
                ax_max.clear()
                ax_max.set_title(f'A{mic_num} - MAX', fontweight='bold')
                ax_max.set_xlabel('Temps (s)')
                ax_max.set_ylabel('MAX (ADC)')
                ax_max.grid(True, alpha=0.3)
                if len(self.monitor.data['max'][mic_num]) > 0:
                    ax_max.plot(times, list(self.monitor.data['max'][mic_num]),
                               'r-', linewidth=1.5)

                # MIN
                ax_min.clear()
                ax_min.set_title(f'A{mic_num} - MIN', fontweight='bold')
                ax_min.set_xlabel('Temps (s)')
                ax_min.set_ylabel('MIN (ADC)')
                ax_min.grid(True, alpha=0.3)
                if len(self.monitor.data['min'][mic_num]) > 0:
                    ax_min.plot(times, list(self.monitor.data['min'][mic_num]),
                               'g-', linewidth=1.5)

                self.single_mic_canvas[mic_num].draw()

        # Programmer la prochaine mise à jour
        self.root.after(500, self.update_plots)  # Mise à jour toutes les 500ms

    def update_info(self):
        """Mise à jour des informations d'en-tête"""
        # Heure actuelle
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=f"Heure: {current_time}")

        # Fréquence d'échantillonnage
        self.freq_label.config(text=f"Fréq. échantillonnage: {self.monitor.sampling_freq:.2f} Hz")

        # Programmer la prochaine mise à jour
        self.root.after(100, self.update_info)  # Mise à jour toutes les 100ms


def main():
    """Point d'entrée principal"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitoring en temps réel de 6 microphones STM32"
    )
    parser.add_argument(
        '--port',
        default='/dev/ttyUSB0',
        help='Port série (ex: /dev/ttyUSB0, COM3)'
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

    args = parser.parse_args()

    # Créer le moniteur
    monitor = STM32MicMonitor(
        port=args.port,
        baudrate=args.baudrate,
        max_points=args.points
    )

    # Connexion série
    if not monitor.connect():
        print("Impossible de se connecter au port série!")
        print(f"Vérifiez que {args.port} est disponible et que vous avez les permissions nécessaires.")
        return

    # Démarrer la lecture
    monitor.start_reading()

    # Créer l'interface graphique
    root = tk.Tk()
    gui = MonitorGUI(root, monitor)

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
