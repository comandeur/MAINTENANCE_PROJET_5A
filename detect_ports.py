#!/usr/bin/env python3
"""
Script utilitaire pour détecter les ports série disponibles
Compatible Windows, Linux et macOS
"""

import sys
import serial.tools.list_ports


def list_serial_ports():
    """Liste tous les ports série disponibles"""
    ports = serial.tools.list_ports.comports()

    if not ports:
        print("❌ Aucun port série détecté!")
        print("\nVérifiez que:")
        print("  - Votre carte STM32 est bien branchée")
        print("  - Les drivers sont installés")
        print("  - Le câble USB fonctionne correctement")
        return []

    print("📡 Ports série détectés:\n")
    print("-" * 80)

    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device}")
        print(f"   Description: {port.description}")
        if port.manufacturer:
            print(f"   Fabricant:   {port.manufacturer}")
        if port.serial_number:
            print(f"   N° série:    {port.serial_number}")
        if port.hwid:
            print(f"   Hardware ID: {port.hwid}")
        print("-" * 80)

    return [port.device for port in ports]


def main():
    """Point d'entrée principal"""
    print("\n🔍 Détection des ports série disponibles\n")

    available_ports = list_serial_ports()

    if available_ports:
        print(f"\n✅ {len(available_ports)} port(s) détecté(s)")
        print("\n💡 Pour utiliser l'application de monitoring, lancez:")
        print(f"\n   python stm32_mic_monitor.py --port {available_ports[0]}")

        if len(available_ports) > 1:
            print("\n   Autres ports disponibles:")
            for port in available_ports[1:]:
                print(f"   python stm32_mic_monitor.py --port {port}")

    return 0 if available_ports else 1


if __name__ == "__main__":
    sys.exit(main())
