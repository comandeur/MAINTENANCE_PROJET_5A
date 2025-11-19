# 🚀 Démarrage Rapide - Monitoring STM32

## Installation (une seule fois)

```bash
pip install -r requirements.txt
```

## Étape 1: Trouver votre port COM

### 🪟 Sous Windows

**Option A - Script automatique (recommandé):**
```bash
python detect_ports.py
```

**Option B - Manuellement:**
1. Branchez votre carte STM32
2. Ouvrez le **Gestionnaire de périphériques** (Windows + X)
3. Développez **"Ports (COM et LPT)"**
4. Notez le numéro (ex: COM3, COM5, COM7)

### 🐧 Sous Linux

```bash
python detect_ports.py
```

Ou manuellement:
```bash
ls /dev/tty*
# Cherchez /dev/ttyUSB0, /dev/ttyACM0, etc.
```

### 🍎 Sous macOS

```bash
python detect_ports.py
```

Ou manuellement:
```bash
ls /dev/cu.*
# Cherchez /dev/cu.usbserial-*, /dev/cu.usbmodem*, etc.
```

## Étape 2: Lancer l'application

### 🪟 Windows
```bash
python stm32_mic_monitor.py --port COM3
```
*(Remplacez COM3 par votre port)*

### 🐧 Linux
```bash
python stm32_mic_monitor.py --port /dev/ttyUSB0
```

### 🍎 macOS
```bash
python stm32_mic_monitor.py --port /dev/cu.usbserial-0001
```

## Options supplémentaires

```bash
# Changer la vitesse (baudrate)
python stm32_mic_monitor.py --port COM3 --baudrate 115200

# Afficher plus de points sur les graphes
python stm32_mic_monitor.py --port COM3 --points 200
```

## ⚠️ Problèmes courants

### "FileNotFoundError" ou "could not open port"
- ✅ Vérifiez que la carte est branchée
- ✅ Lancez `python detect_ports.py` pour voir les ports disponibles
- ✅ Vérifiez le numéro de port (COM3, COM5, etc.)

### "Permission denied" (Linux)
```bash
sudo usermod -a -G dialout $USER
# Puis déconnectez-vous et reconnectez-vous
```

Ou temporairement:
```bash
sudo chmod 666 /dev/ttyUSB0
```

### "Access denied" (Windows)
- ✅ Fermez Arduino IDE, PuTTY ou autres logiciels utilisant le port
- ✅ Débranchez et rebranchez la carte
- ✅ Vérifiez que les drivers STM32 sont installés

### Aucune donnée n'apparaît
- ✅ Vérifiez que la STM32 envoie bien les données avec un terminal série
- ✅ Vérifiez le baudrate (doit être identique sur STM32 et Python)
- ✅ Vérifiez le format des données (voir README_MONITORING.md)

## 📊 Interface de l'application

Une fois lancée, vous verrez **9 onglets**:

1. **RMS - Tous les micros**: Vue d'ensemble RMS
2. **MAX/MIN - Tous les micros**: Vue d'ensemble MIN/MAX
3. **Crête-à-crête - Tous les micros**: Vue d'ensemble amplitudes
4. **Micro A0**: Vue détaillée micro 0
5. **Micro A1**: Vue détaillée micro 1
6. **Micro A2**: Vue détaillée micro 2
7. **Micro A3**: Vue détaillée micro 3
8. **Micro A4**: Vue détaillée micro 4
9. **Micro A5**: Vue détaillée micro 5

**En haut de l'écran:**
- 🕐 Heure exacte
- 📊 Fréquence d'échantillonnage
- 🔌 Port série utilisé

## 📝 Plus d'informations

Consultez **README_MONITORING.md** pour la documentation complète.
