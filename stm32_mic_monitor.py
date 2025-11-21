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

        # Données pour chaque microphone (A0-A5) - chaque micro a son propre historique
        self.num_mics = 6
        self.data = {
            'time': [deque(maxlen=max_points) for _ in range(self.num_mics)],
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
        self.debug_count = 0

        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()

                    if line:
                        # Debug: afficher les premières lignes reçues
                        if self.debug_count < 10:
                            print(f"[DEBUG] Reçu: '{line}'")
                            self.debug_count += 1

                        parsed = self.parse_line(line)
                        if parsed:
                            # Debug: afficher les données parsées
                            if self.debug_count <= 10:
                                print(f"[DEBUG] Parsé: mic={parsed['mic']} RMS={parsed['rms']} AMP={parsed['amplitude']}")

                            mic_num = parsed['mic']
                            current_time = time.time() - self.start_time

                            # Ajouter immédiatement les données pour ce microphone
                            self.data['time'][mic_num].append(current_time)
                            self.data['rms'][mic_num].append(parsed['rms'])
                            self.data['min'][mic_num].append(parsed['min'])
                            self.data['max'][mic_num].append(parsed['max'])
                            self.data['amplitude'][mic_num].append(parsed['amplitude'])

                            # Calcul de la fréquence d'échantillonnage
                            self.sample_count += 1
                            elapsed = time.time() - self.last_sample_time
                            if elapsed >= 1.0:  # Mise à jour chaque seconde
                                self.sampling_freq = self.sample_count / elapsed
                                self.sample_count = 0
                                self.last_sample_time = time.time()

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

    def clear_data(self):
        """Vide toutes les données collectées"""
        for i in range(self.num_mics):
            self.data['time'][i].clear()
            self.data['rms'][i].clear()
            self.data['min'][i].clear()
            self.data['max'][i].clear()
            self.data['amplitude'][i].clear()
        print("✅ Données réinitialisées")


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

        # Bouton pour réinitialiser les graphes
        self.clear_button = tk.Button(
            refresh_frame,
            text="🗑️ Vider",
            command=self.clear_all_graphs,
            font=("Arial", 10),
            bg="#ff6b6b",
            fg="white",
            padx=10,
            pady=2,
            relief=tk.RAISED,
            cursor="hand2"
        )
        self.clear_button.pack(side=tk.LEFT, padx=10)

        # Frame pour contrôle de l'échelle
        scale_frame = tk.Frame(self.info_frame)
        scale_frame.pack(side=tk.RIGHT, padx=20)

        # Toggle auto/manuel (défaut: manuel)
        self.auto_scale = tk.BooleanVar(value=False)
        self.scale_button = tk.Button(
            scale_frame,
            text="📏 Manuel",
            command=self.toggle_scale_mode,
            font=("Arial", 10),
            bg="#4a90d9",
            fg="white",
            padx=8,
            pady=2,
            cursor="hand2"
        )
        self.scale_button.pack(side=tk.LEFT, padx=5)

        # Contrôles d'échelle manuelle
        tk.Label(scale_frame, text="Y min:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 2))
        self.y_min_var = tk.StringVar(value="0")
        self.y_min_entry = tk.Entry(scale_frame, textvariable=self.y_min_var, width=6, font=("Arial", 9))
        self.y_min_entry.pack(side=tk.LEFT)

        tk.Label(scale_frame, text="Y max:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 2))
        self.y_max_var = tk.StringVar(value="3300")
        self.y_max_entry = tk.Entry(scale_frame, textvariable=self.y_max_var, width=6, font=("Arial", 9))
        self.y_max_entry.pack(side=tk.LEFT)

        # Bouton appliquer
        self.apply_scale_btn = tk.Button(
            scale_frame,
            text="Appliquer",
            command=self.apply_manual_scale,
            font=("Arial", 9),
            padx=5
        )
        self.apply_scale_btn.pack(side=tk.LEFT, padx=5)

        # Valeurs d'échelle manuelle actuelles
        self.manual_y_min = 0
        self.manual_y_max = 3300

        # Frame pour contrôle de la base de temps (axe X)
        time_frame = tk.Frame(self.info_frame)
        time_frame.pack(side=tk.RIGHT, padx=10)

        tk.Label(time_frame, text="Base temps:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))

        self.time_window_var = tk.StringVar(value="30")
        self.time_window_entry = tk.Entry(time_frame, textvariable=self.time_window_var, width=5, font=("Arial", 9))
        self.time_window_entry.pack(side=tk.LEFT)

        tk.Label(time_frame, text="s", font=("Arial", 9)).pack(side=tk.LEFT, padx=(2, 5))

        # Checkbox pour afficher tout l'historique
        self.show_all_time = tk.BooleanVar(value=False)
        self.show_all_checkbox = tk.Checkbutton(
            time_frame,
            text="Tout",
            variable=self.show_all_time,
            font=("Arial", 9),
            command=self.on_time_mode_change
        )
        self.show_all_checkbox.pack(side=tk.LEFT)

        # Valeur de fenêtre de temps (en secondes)
        self.time_window = 30.0

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

        # Initialiser les lignes de graphe (pour optimisation set_data)
        self.rms_lines = []
        self.minmax_lines_max = []
        self.minmax_lines_min = []
        self.amplitude_lines = []
        self.single_mic_lines = []

        for i in range(6):
            # RMS
            line, = self.rms_axes[i].plot([], [], 'b-', linewidth=1.5)
            self.rms_lines.append(line)

            # MAX/MIN
            line_max, = self.minmax_axes[i].plot([], [], 'r-', linewidth=1.5, label='MAX')
            line_min, = self.minmax_axes[i].plot([], [], 'g-', linewidth=1.5, label='MIN')
            self.minmax_lines_max.append(line_max)
            self.minmax_lines_min.append(line_min)
            self.minmax_axes[i].legend()

            # Amplitude
            line, = self.amplitude_axes[i].plot([], [], 'purple', linewidth=1.5)
            self.amplitude_lines.append(line)

            # Vues individuelles (RMS, Amplitude, MAX, MIN)
            ax_rms, ax_amp, ax_max, ax_min = self.single_mic_axes[i]
            line_rms, = ax_rms.plot([], [], 'b-', linewidth=1.5)
            line_amp, = ax_amp.plot([], [], 'purple', linewidth=1.5)
            line_max, = ax_max.plot([], [], 'r-', linewidth=1.5)
            line_min, = ax_min.plot([], [], 'g-', linewidth=1.5)
            self.single_mic_lines.append({
                'rms': line_rms,
                'amp': line_amp,
                'max': line_max,
                'min': line_min
            })

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

    def adjust_axis_scale(self, ax, current_time=None):
        """Ajuste l'échelle d'un axe selon le mode (auto ou manuel)"""
        # Gestion de l'axe Y
        if self.auto_scale.get():
            ax.relim()
            ax.autoscale_view()
        else:
            # Lire directement les valeurs des champs (appliquées automatiquement)
            try:
                y_min = float(self.y_min_var.get())
                y_max = float(self.y_max_var.get())
                if y_min < y_max:
                    ax.set_ylim(y_min, y_max)
            except ValueError:
                pass  # Garder l'échelle actuelle si valeurs invalides
            ax.relim()
            ax.autoscale_view(scaley=False)

        # Gestion de l'axe X (base de temps)
        if not self.show_all_time.get() and current_time is not None:
            # Lire la valeur de fenêtre de temps
            try:
                self.time_window = float(self.time_window_var.get())
            except ValueError:
                self.time_window = 30.0

            # Fenêtre glissante : afficher les dernières X secondes
            x_min = max(0, current_time - self.time_window)
            x_max = current_time
            ax.set_xlim(x_min, x_max)

    def update_plots(self):
        """Mise à jour périodique des graphes - optimisée pour ne redessiner que l'onglet visible"""
        # Déterminer quel onglet est actuellement visible
        current_tab = self.notebook.index(self.notebook.select())

        # Trouver le temps le plus récent parmi tous les micros
        current_time = 0
        for i in range(6):
            if len(self.monitor.data['time'][i]) > 0:
                current_time = max(current_time, self.monitor.data['time'][i][-1])

        # Onglet 0: RMS - Tous les micros
        if current_tab == 0:
            for i in range(6):
                if len(self.monitor.data['rms'][i]) > 0:
                    times_i = list(self.monitor.data['time'][i])
                    data_i = list(self.monitor.data['rms'][i])
                    self.rms_lines[i].set_data(times_i, data_i)
                    self.adjust_axis_scale(self.rms_axes[i], current_time)
            self.rms_canvas.draw()

        # Onglet 1: MAX/MIN - Tous les micros
        elif current_tab == 1:
            for i in range(6):
                if len(self.monitor.data['max'][i]) > 0:
                    times_i = list(self.monitor.data['time'][i])
                    self.minmax_lines_max[i].set_data(times_i, list(self.monitor.data['max'][i]))
                    self.minmax_lines_min[i].set_data(times_i, list(self.monitor.data['min'][i]))
                    self.adjust_axis_scale(self.minmax_axes[i], current_time)
            self.minmax_canvas.draw()

        # Onglet 2: Amplitude - Tous les micros
        elif current_tab == 2:
            for i in range(6):
                if len(self.monitor.data['amplitude'][i]) > 0:
                    times_i = list(self.monitor.data['time'][i])
                    self.amplitude_lines[i].set_data(times_i, list(self.monitor.data['amplitude'][i]))
                    self.adjust_axis_scale(self.amplitude_axes[i], current_time)
            self.amplitude_canvas.draw()

        # Onglets 3-8: Vues individuelles des micros
        elif 3 <= current_tab <= 8:
            mic_num = current_tab - 3
            if len(self.monitor.data['rms'][mic_num]) > 0:
                times_mic = list(self.monitor.data['time'][mic_num])

                # Mettre à jour les données des lignes
                self.single_mic_lines[mic_num]['rms'].set_data(times_mic, list(self.monitor.data['rms'][mic_num]))
                self.single_mic_lines[mic_num]['amp'].set_data(times_mic, list(self.monitor.data['amplitude'][mic_num]))
                self.single_mic_lines[mic_num]['max'].set_data(times_mic, list(self.monitor.data['max'][mic_num]))
                self.single_mic_lines[mic_num]['min'].set_data(times_mic, list(self.monitor.data['min'][mic_num]))

                # Ajuster les axes
                ax_rms, ax_amp, ax_max, ax_min = self.single_mic_axes[mic_num]
                for ax in [ax_rms, ax_amp, ax_max, ax_min]:
                    self.adjust_axis_scale(ax, current_time)

                self.single_mic_canvas[mic_num].draw()

        # Programmer la prochaine mise à jour
        self.root.after(self.refresh_rate, self.update_plots)

    def on_refresh_change(self, value):
        """Callback quand le slider de rafraîchissement change"""
        self.refresh_rate = int(value)
        self.refresh_label.config(text=f"{self.refresh_rate}ms")

    def toggle_scale_mode(self):
        """Bascule entre échelle auto et manuelle"""
        self.auto_scale.set(not self.auto_scale.get())
        if self.auto_scale.get():
            self.scale_button.config(text="📏 Auto", bg="#28a745")
            # Désactiver les champs manuels
            self.y_min_entry.config(state='disabled')
            self.y_max_entry.config(state='disabled')
            self.apply_scale_btn.config(state='disabled')
        else:
            self.scale_button.config(text="📏 Manuel", bg="#4a90d9")
            # Activer les champs manuels
            self.y_min_entry.config(state='normal')
            self.y_max_entry.config(state='normal')
            self.apply_scale_btn.config(state='normal')

    def apply_manual_scale(self):
        """Applique les valeurs d'échelle manuelle"""
        try:
            y_min = float(self.y_min_var.get())
            y_max = float(self.y_max_var.get())
            if y_min >= y_max:
                print("⚠️ Y min doit être inférieur à Y max")
                return
            self.manual_y_min = y_min
            self.manual_y_max = y_max
            print(f"📏 Échelle appliquée: {y_min} - {y_max}")
        except ValueError:
            print("⚠️ Valeurs d'échelle invalides")

    def on_time_mode_change(self):
        """Callback quand le mode de base de temps change"""
        if self.show_all_time.get():
            self.time_window_entry.config(state='disabled')
            print("⏱️ Base de temps: affichage de tout l'historique")
        else:
            self.time_window_entry.config(state='normal')
            print(f"⏱️ Base de temps: fenêtre glissante de {self.time_window_var.get()}s")

    def clear_all_graphs(self):
        """Vide toutes les données des graphes"""
        # Demander confirmation
        from tkinter import messagebox
        if messagebox.askyesno("Confirmation", "Voulez-vous vraiment vider tous les graphes ?"):
            # Vider les données du moniteur
            self.monitor.clear_data()

            # Réinitialiser visuellement tous les graphes
            # (Les lignes seront automatiquement mises à jour lors du prochain refresh)
            print("🗑️ Graphes vidés")

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
