# STM32 Microphone Monitor - Application de Monitoring en Temps Réel

Application Python pour visualiser en temps réel les données de 6 microphones connectés à une carte STM32 via UART.

## Fonctionnalités

L'application affiche les données suivantes pour 6 microphones (A0-A5):
- **RMS** (Root Mean Square) en mV
- **MIN** et **MAX** (valeurs ADC)
- **Amplitude crête-à-crête** en mV

### Interface Graphique

L'application propose **9 onglets** de visualisation:

#### En-tête commun (tous les onglets)
- Heure exacte
- Fréquence d'échantillonnage (commune aux 6 micros)
- Port série utilisé

#### Onglets de visualisation

1. **RMS - Tous les micros**: 6 graphes séparés montrant le RMS de chaque microphone
2. **MAX/MIN - Tous les micros**: 6 graphes séparés montrant MAX et MIN pour chaque microphone
3. **Crête-à-crête - Tous les micros**: 6 graphes séparés montrant l'amplitude de chaque microphone
4. **Micro A0**: Vue détaillée du microphone A0 avec 4 graphes:
   - RMS (haut gauche)
   - Crête-à-crête (bas gauche)
   - MAX (haut droite)
   - MIN (bas droite)
5. **Micro A1**: Vue détaillée du microphone A1 (même disposition)
6. **Micro A2**: Vue détaillée du microphone A2 (même disposition)
7. **Micro A3**: Vue détaillée du microphone A3 (même disposition)
8. **Micro A4**: Vue détaillée du microphone A4 (même disposition)
9. **Micro A5**: Vue détaillée du microphone A5 (même disposition)

## Installation

### Prérequis

- Python 3.7 ou supérieur
- pip (gestionnaire de paquets Python)

### Installation des dépendances

```bash
pip install -r requirements.txt
```

Les dépendances incluent:
- `pyserial`: Communication série avec la STM32
- `matplotlib`: Affichage des graphes
- `numpy`: Traitement des données

## Utilisation

### Lancement basique

```bash
python stm32_mic_monitor.py
```

Par défaut, l'application se connecte à `/dev/ttyUSB0` à 115200 bauds.

### Options de ligne de commande

```bash
python stm32_mic_monitor.py --port COM3 --baudrate 115200 --points 200
```

**Arguments disponibles:**
- `--port`: Port série (ex: `/dev/ttyUSB0` sous Linux, `COM3` sous Windows)
- `--baudrate`: Vitesse de communication (défaut: 115200)
- `--points`: Nombre de points à afficher sur les graphes (défaut: 100)

### Exemples

**Sous Linux:**
```bash
# Port USB0
python stm32_mic_monitor.py --port /dev/ttyUSB0

# Port ACM0 (souvent pour ST-Link)
python stm32_mic_monitor.py --port /dev/ttyACM0
```

**Sous Windows:**
```bash
# Port COM3
python stm32_mic_monitor.py --port COM3

# Port COM5 avec plus de points
python stm32_mic_monitor.py --port COM5 --points 200
```

**Sous macOS:**
```bash
python stm32_mic_monitor.py --port /dev/cu.usbserial-0001
```

## Format des données UART

L'application attend des données au format suivant depuis la STM32:

```
A0: MIN=  123 MAX=  456 AMP=123.456mV RMS=789.012mV
A1: MIN=  234 MAX=  567 AMP=234.567mV RMS=890.123mV
A2: MIN=  345 MAX=  678 AMP=345.678mV RMS=901.234mV
A3: MIN=  456 MAX=  789 AMP=456.789mV RMS=123.456mV
A4: MIN=  567 MAX=  890 AMP=567.890mV RMS=234.567mV
A5: MIN=  678 MAX=  901 AMP=678.901mV RMS=345.678mV
```

### Format regex utilisé:
```
A(\d): MIN=\s*(-?\d+) MAX=\s*(-?\d+) AMP=(\d+)\.(\d+)mV RMS=(\d+)\.(\d+)mV
```

## Configuration STM32

Assurez-vous que votre code STM32:
1. Envoie les données au format spécifié ci-dessus
2. Utilise la même vitesse de communication (baudrate)
3. Envoie les données pour les 6 microphones (A0-A5) en séquence

Exemple de code STM32:
```c
sprintf(msg, "A0: MIN=%5d MAX=%5d AMP=%lu.%03lumV RMS=%lu.%03lumV\r\n",
        min_ac[0], max_ac[0],
        amplitude_mv[0]/1000, amplitude_mv[0]%1000,
        rms_mv[0]/1000, rms_mv[0]%1000);
HAL_UART_Transmit(&huart2, (uint8_t*)msg, strlen(msg), HAL_MAX_DELAY);
```

## Permissions (Linux)

Sous Linux, vous devrez peut-être ajouter votre utilisateur au groupe `dialout` pour accéder au port série:

```bash
sudo usermod -a -G dialout $USER
```

Puis déconnectez-vous et reconnectez-vous pour que les changements prennent effet.

Ou donnez temporairement les permissions:
```bash
sudo chmod 666 /dev/ttyUSB0
```

## Dépannage

### Problème: "Impossible de se connecter au port série"

**Solutions:**
1. Vérifiez que le port série est correct:
   - Linux: `ls /dev/tty*` pour lister les ports
   - Windows: Vérifiez dans le Gestionnaire de périphériques
2. Vérifiez que vous avez les permissions (Linux)
3. Assurez-vous qu'aucun autre programme n'utilise le port (ex: Arduino IDE, minicom)

### Problème: "Aucune donnée n'apparaît"

**Solutions:**
1. Vérifiez que la STM32 envoie bien des données (testez avec un terminal série comme `minicom` ou PuTTY)
2. Vérifiez que le baudrate est correct
3. Vérifiez que le format des données correspond exactement au format attendu

### Problème: "Les graphes ne se mettent pas à jour"

**Solutions:**
1. Vérifiez que les 6 microphones envoient leurs données en séquence complète
2. L'application attend de recevoir A0-A5 avant de mettre à jour les graphes

## Architecture du code

### Classe `STM32MicMonitor`
- Gère la connexion série
- Parse les données UART
- Stocke les données dans des buffers circulaires (deque)
- Calcule la fréquence d'échantillonnage

### Classe `MonitorGUI`
- Crée l'interface graphique avec Tkinter
- Gère les 9 onglets de visualisation
- Met à jour les graphes toutes les 500ms
- Met à jour les informations d'en-tête toutes les 100ms

### Threading
- Thread principal: Interface graphique (Tkinter)
- Thread secondaire: Lecture série (daemon)

## Personnalisation

### Modifier le nombre de points affichés
```bash
python stm32_mic_monitor.py --points 500
```

### Modifier la fréquence de rafraîchissement des graphes
Dans `stm32_mic_monitor.py`, ligne ~485:
```python
self.root.after(500, self.update_plots)  # 500ms par défaut
```

### Modifier la fréquence de mise à jour de l'en-tête
Dans `stm32_mic_monitor.py`, ligne ~497:
```python
self.root.after(100, self.update_info)  # 100ms par défaut
```

## Licence

Ce code est fourni à des fins éducatives et de développement.
