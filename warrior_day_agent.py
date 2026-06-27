"""
⚔️ WARRIOR SCHEDULER UNIFIÉ
Gère les deux agents dans un seul service Railway:
  - Pre-Market Agent → 8h00, 8h30, 9h00 ET (lundi–vendredi)
  - Day Trading Agent → boucle 9h30–16h00 ET (lundi–vendredi)
"""

import subprocess
import threading
import time
import os
import http.server
import socketserver
from datetime import datetime
import pytz

ET = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────
# ÉTAT GLOBAL
# ─────────────────────────────────────────────
state = {
    "last_premarket": None,   # heure du dernier scan pre-market
    "day_running":    False,  # boucle day agent active
    "scans_done":     [],     # historique des scans
}

def now_et():
    return datetime.now(ET)

def log(msg):
    print(f"[SCHEDULER {now_et().strftime('%H:%M:%S')} ET] {msg}", flush=True)

def is_weekday():
    return now_et().weekday() < 5  # Lundi=0 … Vendredi=4

def run_script(script_name):
    """Lance un script Python et attend sa fin."""
    log(f"🚀 Lancement {script_name}")
    try:
        result = subprocess.run(
            ["python", script_name],
            capture_output=False,
            timeout=300  # max 5 minutes par scan
        )
        log(f"✅ {script_name} terminé (code {result.returncode})")
    except subprocess.TimeoutExpired:
        log(f"⚠ {script_name} timeout après 5 minutes")
    except Exception as e:
        log(f"⚠ {script_name} erreur: {e}")


# ─────────────────────────────────────────────
# PRE-MARKET — 8h00, 8h30, 9h00 ET
# ─────────────────────────────────────────────
PREMARKET_TIMES = ["08:00", "08:30", "09:00"]

def premarket_scheduler():
    """Thread qui surveille l'heure et lance le scan pre-market."""
    log("📡 Pre-Market scheduler démarré")
    scans_done_today = set()

    while True:
        now  = now_et()
        hhmm = now.strftime("%H:%M")
        day  = now.strftime("%Y-%m-%d")

        # Reset à minuit
        if hhmm == "00:01":
            scans_done_today = set()

        if is_weekday() and hhmm in PREMARKET_TIMES:
            key = f"{day}_{hhmm}"
            if key not in scans_done_today:
                scans_done_today.add(key)
                state["last_premarket"] = hhmm
                state["scans_done"].append(f"PreMarket {hhmm}")
                run_script("warrior_ai_agent.py")

        time.sleep(30)  # Vérifie toutes les 30 secondes


# ─────────────────────────────────────────────
# DAY TRADING — boucle 9h30–16h00 ET
# ─────────────────────────────────────────────
DAY_START = (9,  30)   # 9h30 ET
DAY_END   = (16,  0)   # 16h00 ET
DAY_INTERVAL = 300     # 5 minutes entre chaque scan

def is_market_hours():
    now = now_et()
    if not is_weekday():
        return False
    open_time  = now.replace(hour=DAY_START[0], minute=DAY_START[1], second=0, microsecond=0)
    close_time = now.replace(hour=DAY_END[0],   minute=DAY_END[1],   second=0, microsecond=0)
    return open_time <= now <= close_time

def day_scheduler():
    """Thread qui lance le day agent toutes les 5 min pendant les heures de marché."""
    log("📈 Day Trading scheduler démarré")

    while True:
        if is_market_hours():
            if not state["day_running"]:
                state["day_running"] = True
                log("🟢 Marché ouvert — Day Agent actif")

            state["scans_done"].append(f"Day {now_et().strftime('%H:%M')}")
            run_script("warrior_day_agent.py")

            # Attendre 5 minutes avant prochain scan
            log(f"💤 Prochain scan day dans {DAY_INTERVAL//60} min")
            time.sleep(DAY_INTERVAL)

        else:
            if state["day_running"]:
                state["day_running"] = False
                log("🔴 Marché fermé — Day Agent en pause")

            time.sleep(60)  # Vérifie toutes les minutes si marché ouvert


# ─────────────────────────────────────────────
# SERVEUR KEEPALIVE RAILWAY
# ─────────────────────────────────────────────
PORT_WEB = int(os.environ.get("PORT", 8080))

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        now    = now_et()
        market = "OPEN" if is_market_hours() else "CLOSED"
        last   = state["last_premarket"] or "—"
        nb     = len(state["scans_done"])
        msg    = (f"⚔️ Warrior Scheduler | {now.strftime('%H:%M')} ET | "
                  f"Market: {market} | Last pre-market: {last} | Scans: {nb}")
        self.wfile.write(msg.encode())
    def log_message(self, format, *args):
        pass


# ─────────────────────────────────────────────
# DÉMARRAGE
# ─────────────────────────────────────────────
log("=" * 55)
log("  ⚔️  WARRIOR SCHEDULER UNIFIÉ")
log(f"  {now_et().strftime('%Y-%m-%d %H:%M')} ET")
log("  Pre-Market : 8h00 / 8h30 / 9h00 ET")
log("  Day Agent  : 9h30–16h00 ET (toutes les 5 min)")
log("=" * 55)

# Lancer les deux schedulers en threads parallèles
t1 = threading.Thread(target=premarket_scheduler, daemon=True)
t2 = threading.Thread(target=day_scheduler,       daemon=True)
t1.start()
t2.start()
log("✅ Threads démarrés — Pre-Market + Day Trading")

# Serveur HTTP keepalive (Railway exige un port ouvert)
log(f"🌐 Serveur keepalive sur port {PORT_WEB}")
with socketserver.TCPServer(("", PORT_WEB), Handler) as httpd:
    httpd.serve_forever()
