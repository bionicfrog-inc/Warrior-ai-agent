"""
⚔️ WARRIOR AI SCHEDULER
Lance l'agent automatiquement chaque matin pre-market
"""

import subprocess
import sys
import os
import time
from datetime import datetime
import pytz

ET = pytz.timezone("America/New_York")

# Heures de scan pre-market (ET)
SCAN_TIMES = [
    "04:00",  # Ouverture pre-market
    "06:00",  # Milieu pre-market
    "08:00",  # 1h30 avant ouverture — meilleur moment
    "08:30",  # 1h avant ouverture
    "09:00",  # 30 min avant ouverture
    "10:23",
]

print("⚔️ WARRIOR AI SCHEDULER démarré")
print(f"Scans prévus : {', '.join(SCAN_TIMES)} ET")

def should_scan(now_et):
    """Vérifie si on doit lancer un scan maintenant."""
    if now_et.weekday() >= 5:  # Weekend
        return False
    current_time = now_et.strftime("%H:%M")
    return current_time in SCAN_TIMES

last_scan = None

while True:
    now_et = datetime.now(ET)
    current_time = now_et.strftime("%H:%M")

    if should_scan(now_et) and current_time != last_scan:
        print(f"\n🚀 Lancement scan à {current_time} ET")
        last_scan = current_time

        try:
            result = subprocess.run(
                [sys.executable, "warrior_ai_agent.py"],
                timeout=300,
                cwd=os.getcwd()
            )
            print(f"✅ Scan terminé (code: {result.returncode})")
        except subprocess.TimeoutExpired:
            print("⚠ Scan timeout après 5 minutes")
        except Exception as e:
            print(f"⚠ Erreur scan: {e}")

    # Attendre 30 secondes avant de vérifier à nouveau
    time.sleep(30)
