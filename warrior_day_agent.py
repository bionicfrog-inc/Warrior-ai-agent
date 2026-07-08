"""
⚔️ WARRIOR DAY AGENT — Intraday Edition
Scan toutes les 5 minutes de 9h30 à 16h00 ET
Alerte Telegram SEULEMENT si signal détecté
Ross Cameron methodology — setups intraday
"""

import requests
import os
import json
import time
from datetime import datetime, timedelta
import pytz

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
FINNHUB_KEY       = os.environ.get("FINNHUB_KEY",       "")
TG_TOKEN          = os.environ.get("TG_TOKEN",          "")
TG_CHAT_ID        = os.environ.get("TG_CHAT_ID",        "")
ANTHROPIC_KEY     = os.environ.get("ANTHROPIC_KEY",     "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
LOCAL_WEBHOOK_URL = os.environ.get("LOCAL_WEBHOOK_URL", "")

ET = pytz.timezone("America/New_York")

# Critères intraday Ross Cameron
MIN_PRIX      = 1.00    # Minimum $1 intraday (plus strict qu'en pre-market)
MAX_PRIX      = 50.0
MIN_RVOL      = 5.0     # RVOL 5x+ obligatoire
MIN_VOL_DAY   = 500_000 # Volume cumulé minimum pour être liquide
MAX_FLOAT     = 500.0   # Shares outstanding — Claude filtre
MIN_CHANGE    = 5.0     # +5% minimum sur la journée
TOP_N         = 5       # Top 5 analysés par Claude
SCAN_INTERVAL = 300     # Scan toutes les 5 minutes (300 secondes)
MIN_CONVICTION_WEBHOOK = 5  # Conviction min pour envoyer le webhook à warrior_local.py

# Mémoire des alertes déjà envoyées (évite les doublons)
# Format: {symbol: {"setup": "Gap & Go", "sent_at": datetime, "price": 5.20}}
# Persistée sur disque car le script tourne en one-shot (relancé par
# scheduler.py toutes les 5 min) — sans ça le cooldown serait perdu
# à chaque relance.
ALERTES_FILE = os.environ.get("ALERTES_FILE", "alertes_envoyees.json")
COOLDOWN_MINUTES = 30  # Même stock → pas d'alerte avant 30 min

def load_alertes() -> dict:
    if not os.path.exists(ALERTES_FILE):
        return {}
    try:
        with open(ALERTES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {
            symbol: {
                "setup":   entry["setup"],
                "sent_at": datetime.fromisoformat(entry["sent_at"]),
                "price":   entry["price"],
            }
            for symbol, entry in raw.items()
        }
    except Exception as e:
        print(f"⚠ Impossible de charger {ALERTES_FILE}: {e}")
        return {}

def save_alertes(data: dict):
    try:
        serializable = {
            symbol: {
                "setup":   entry["setup"],
                "sent_at": entry["sent_at"].isoformat(),
                "price":   entry["price"],
            }
            for symbol, entry in data.items()
        }
        with open(ALERTES_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
    except Exception as e:
        print(f"⚠ Impossible de sauvegarder {ALERTES_FILE}: {e}")

alertes_envoyees: dict = load_alertes()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def now_et():
    return datetime.now(ET)

def is_market_open():
    """Vérifie si le marché est ouvert (9h30–16h00 ET, lundi–vendredi)."""
    now = now_et()
    if now.weekday() >= 5:  # Samedi/Dimanche
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now <= market_close

def escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def log(msg):
    print(f"[{now_et().strftime('%H:%M:%S')} ET] {msg}", flush=True)


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(message, parse_mode="HTML"):
    if not TG_TOKEN or not TG_CHAT_ID:
        log(f"⚠ Telegram non configuré\n{message}")
        return False
    try:
        url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {
            "chat_id":    TG_CHAT_ID,
            "text":       message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        r = requests.post(url, data=data, timeout=10)
        if r.status_code == 200:
            log("✅ Telegram envoyé")
            return True
        else:
            log(f"⚠ Telegram erreur {r.status_code}: {r.text[:100]}")
            return False
    except Exception as e:
        log(f"⚠ Telegram: {e}")
        return False


# ─────────────────────────────────────────────
# WEBHOOK LOCAL (PC via ngrok) — MANQUANT DANS LA VERSION ORIGINALE
# ─────────────────────────────────────────────
def send_webhook(stock_data, ai_analysis):
    """Envoie le signal JSON au PC local (warrior_local.py) via ngrok pour exécution.
    C'est cette fonction qui manquait — sans elle, le Day Agent ne pouvait
    qu'alerter sur Telegram mais jamais faire entrer le bot en position."""
    if not LOCAL_WEBHOOK_URL:
        log("  ⚠ LOCAL_WEBHOOK_URL non configuré — webhook ignoré")
        return
    if not ai_analysis:
        return

    conviction = ai_analysis.get("conviction", 0)
    if conviction < MIN_CONVICTION_WEBHOOK:
        log(f"  ⏭ Conviction {conviction}/10 < {MIN_CONVICTION_WEBHOOK} — webhook non envoyé")
        return

    payload = {
        "symbol":         stock_data["symbol"],
        "price":          stock_data["price"],
        "gap":            stock_data.get("gap", 0),
        "variation":      stock_data["variation"],
        "rvol":           stock_data["rvol"],
        "float_m":        stock_data["float_m"],
        "conviction":     conviction,
        "recommendation": ai_analysis.get("recommendation", "SURVEILLER"),
        "setup_type":     ai_analysis.get("setup_type", stock_data.get("setup", "")),
        "entry_zone":     ai_analysis.get("entry_zone", ""),
        "stop_loss":      ai_analysis.get("stop_loss", ""),
        "target_1":       ai_analysis.get("target_1", ""),
        "target_2":       ai_analysis.get("target_2", ""),
        "risk_reward":    ai_analysis.get("risk_reward", ""),
        "timestamp":      now_et().isoformat(),
    }

    try:
        r = requests.post(f"{LOCAL_WEBHOOK_URL}/signal", json=payload, timeout=8)
        if r.status_code == 200:
            log(f"  ✅ Webhook envoyé → {stock_data['symbol']}")
        else:
            log(f"  ⚠ Webhook erreur {r.status_code}: {r.text[:150]}")
    except Exception as e:
        log(f"  ⚠ Webhook exception: {e}")


def get_historical_setup_stats():
    """Récupère les stats de performance par setup depuis warrior_local.py (PC).
    Échec silencieux si indisponible — ne bloque jamais un scan."""
    if not LOCAL_WEBHOOK_URL:
        return ""
    try:
        r = requests.get(
            f"{LOCAL_WEBHOOK_URL}/proposals",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=6
        )
        if r.status_code != 200:
            return ""
        stats = r.json().get("setup_stats", {})
        if not stats:
            return ""
        lines = []
        for setup, s in stats.items():
            lines.append(
                f"- {setup}: {s['count']} proposition(s) passées, "
                f"évolution moyenne {s['avg_pct_change']:+.1f}% (4h-11h ET), "
                f"{s['positive_rate']:.0f}% ont progressé, "
                f"{s['entered_count']} ont été achetées"
            )
        return "\n".join(lines)
    except Exception as e:
        log(f"  ⚠ Stats historiques indisponibles: {e}")
        return ""


def get_learned_lessons():
    """Récupère les leçons apprises (analyse rétrospective) depuis warrior_local.py.
    Échec silencieux si indisponible."""
    if not LOCAL_WEBHOOK_URL:
        return ""
    try:
        r = requests.get(
            f"{LOCAL_WEBHOOK_URL}/lessons",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=6
        )
        if r.status_code != 200:
            return ""
        lessons = r.json().get("lessons", [])
        if not lessons:
            return ""
        recent = lessons[-10:]
        lines = []
        for l in recent:
            lines.append(
                f"- [{l.get('date')}] {l.get('symbol')} ({l.get('setup_type')}, "
                f"conviction donnée {l.get('conviction')}/10) — "
                f"justifiée: {l.get('conviction_justified')} — {l.get('lesson', '')}"
            )
        return "\n".join(lines)
    except Exception as e:
        log(f"  ⚠ Leçons apprises indisponibles: {e}")
        return ""


# ─────────────────────────────────────────────
# ÉTAPE 1 — SCANNER INTRADAY (toutes sources)
# ─────────────────────────────────────────────
def get_intraday_candidates():
    """
    Agrège 3 sources pour trouver les meilleurs setups intraday:
    1. Alpha Vantage TOP_GAINERS_LOSERS — source principale fiable
       (désactivée après 10h00 ET pour respecter le quota de 25 req/jour —
       la fenêtre 4h00-10h00 ET est jugée la plus prioritaire)
    2. Finnhub News — catalyst frais
    3. Yahoo Gainers — fallback si < 3 candidats
    Retourne une liste unifiée dédupliquée.
    """
    candidates = {}

    # ── Source 1 — Alpha Vantage TOP_GAINERS_LOSERS ────────────────────
    use_alpha_vantage = now_et().hour < 10  # coupé après 10h00 ET
    if ALPHA_VANTAGE_KEY and use_alpha_vantage:
        try:
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_KEY}"
            )
            r    = requests.get(url, timeout=10)
            data = r.json()
            log(f"Alpha Vantage → HTTP {r.status_code}")

            sources = [
                ("top_gainers",          data.get("top_gainers", [])),
                ("most_actively_traded", data.get("most_actively_traded", [])),
            ]
            for src_name, items in sources:
                for s in items:
                    sym     = s.get("ticker", "")
                    price   = float(s.get("price", 0) or 0)
                    chg_pct = s.get("change_percentage", "0%").replace("%", "")
                    change  = float(chg_pct or 0)
                    volume  = int(s.get("volume", 0) or 0)

                    if (sym and len(sym) <= 5
                            and MIN_PRIX <= price <= MAX_PRIX
                            and change >= MIN_CHANGE
                            and not any(sym.endswith(x) for x in ["W", "U", "R"])
                            and sym not in candidates):
                        candidates[sym] = {
                            "symbol": sym, "price": price,
                            "change": change, "volume": volume,
                            "source": f"Alpha Vantage ({src_name})"
                        }

            log(f"Alpha Vantage → {len(candidates)} candidats")

        except Exception as e:
            log(f"⚠ Alpha Vantage: {e}")
    elif not ALPHA_VANTAGE_KEY:
        log("⚠ ALPHA_VANTAGE_KEY manquante")
    else:
        log("⏭ Alpha Vantage désactivé après 10h00 ET (quota) — Finnhub/Yahoo seulement")

    # ── Source 2 — Finnhub News (catalyst frais) ───────────────────────
    if FINNHUB_KEY:
        try:
            url_news = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
            r_news   = requests.get(url_news, timeout=8).json()
            syms_from_news = set()
            if isinstance(r_news, list):
                for article in r_news[:30]:
                    related = article.get("related", "")
                    if related:
                        for sym in related.split(","):
                            sym = sym.strip().upper()
                            if sym and len(sym) <= 5 and sym not in candidates:
                                syms_from_news.add(sym)

            added = 0
            for sym in list(syms_from_news)[:15]:
                try:
                    url_q = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                             f"?interval=1m&range=1d&includePrePost=false")
                    rq    = requests.get(url_q, headers={"User-Agent": "Mozilla/5.0"},
                                         timeout=4).json()
                    meta  = rq.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price  = float(meta.get("regularMarketPrice", 0) or 0)
                    prev   = float(meta.get("chartPreviousClose", 0) or 0)
                    volume = int(meta.get("regularMarketVolume", 0) or 0)
                    change = round((price - prev) / prev * 100, 2) if prev else 0
                    if MIN_PRIX <= price <= MAX_PRIX and change >= MIN_CHANGE:
                        candidates[sym] = {
                            "symbol": sym, "price": price,
                            "change": change, "volume": volume,
                            "source": "Finnhub News"
                        }
                        added += 1
                except Exception:
                    pass
                time.sleep(0.05)
            log(f"Finnhub News → {added} ajoutés, {len(candidates)} total")
        except Exception as e:
            log(f"⚠ Finnhub News: {e}")

    # ── Source 3 — Yahoo Screeners (fallback, plusieurs IDs) ─────────
    if len(candidates) < 3:
        screener_ids = ["day_gainers", "small_cap_gainers", "most_actives"]
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        for scr_id in screener_ids:
            if len(candidates) >= 5:
                break
            try:
                url = (
                    f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
                    f"?formatted=false&lang=en-US&region=US&scrIds={scr_id}&count=100"
                )
                r = requests.get(url, headers=headers, timeout=10)
                log(f"Yahoo {scr_id} → HTTP {r.status_code}")
                if r.status_code != 200:
                    continue
                quotes = r.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
                added = 0
                for q in quotes:
                    sym    = q.get("symbol", "")
                    price  = float(q.get("regularMarketPrice", 0) or 0)
                    change = float(q.get("regularMarketChangePercent", 0) or 0)
                    volume = int(q.get("regularMarketVolume", 0) or 0)
                    if (sym and len(sym) <= 5 and MIN_PRIX <= price <= MAX_PRIX
                            and change >= MIN_CHANGE and sym not in candidates
                            and not any(sym.endswith(x) for x in ["W", "U", "R"])):
                        candidates[sym] = {"symbol": sym, "price": price,
                                           "change": change, "volume": volume,
                                           "source": f"Yahoo {scr_id}"}
                        added += 1
                        log(f"    ✓ {sym} +{change:.1f}% @ ${price:.2f}")
                log(f"Yahoo {scr_id} → {added} ajoutés, {len(candidates)} total")
            except Exception as e:
                log(f"⚠ Yahoo {scr_id}: {e}")

    # Trier par variation décroissante
    result = sorted(candidates.values(), key=lambda x: x["change"], reverse=True)
    log(f"📋 {len(result)} candidats totaux")
    return result[:30]


# ─────────────────────────────────────────────
# ÉTAPE 2 — DONNÉES INTRADAY YAHOO
# ─────────────────────────────────────────────
def get_intraday_data(symbol):
    """
    Récupère les données intraday complètes pour un symbole:
    - Prix, volume, RVOL, VWAP approximé
    - HOD (High of Day)
    - Float via Finnhub
    - Setup détecté (Gap & Go, ORBO, First Pullback, HOD Break, Flat Top)
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        # Données intraday 1 minute
        url_rt = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                  f"?interval=1m&range=1d&includePrePost=false")
        r_rt   = requests.get(url_rt, headers=headers, timeout=6).json()
        res_rt = r_rt.get("chart", {}).get("result", [])
        if not res_rt:
            return None

        meta    = res_rt[0].get("meta", {})
        q_rt    = res_rt[0].get("indicators", {}).get("quote", [{}])[0]

        price      = float(meta.get("regularMarketPrice", 0) or 0)
        prev_close = float(meta.get("chartPreviousClose", 0) or 0)
        volume     = int(meta.get("regularMarketVolume", 0) or 0)

        if not price or not prev_close:
            return None

        # Variation et gap
        variation  = round((price - prev_close) / prev_close * 100, 2)
        opens      = [o for o in q_rt.get("open",   []) if o is not None]
        closes     = [c for c in q_rt.get("close",  []) if c is not None]
        highs      = [h for h in q_rt.get("high",   []) if h is not None]
        lows       = [l for l in q_rt.get("low",    []) if l is not None]
        volumes    = [v for v in q_rt.get("volume", []) if v is not None]

        open_px  = float(opens[0])  if opens  else price
        hod      = max(highs)       if highs  else price
        lod      = min(lows)        if lows   else price
        gap      = round((open_px - prev_close) / prev_close * 100, 2) if prev_close else 0

        # VWAP approximé (moyenne des prix typiques pondérée par volume)
        if highs and lows and closes and volumes and len(highs) == len(volumes):
            typ_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
            cum_tpv    = sum(tp * v for tp, v in zip(typ_prices, volumes))
            cum_vol    = sum(volumes)
            vwap       = cum_tpv / cum_vol if cum_vol > 0 else price
        else:
            vwap = price

        # Volume moyen journalier (données daily)
        avg_vol_daily = 0
        try:
            url_d  = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=30d"
            r_d    = requests.get(url_d, headers=headers, timeout=5).json()
            res_d  = r_d.get("chart", {}).get("result", [])
            if res_d:
                vols_d        = [v for v in res_d[0].get("indicators", {}).get("quote", [{}])[0].get("volume", []) if v]
                avg_vol_daily = int(sum(vols_d[-11:-1]) / 10) if len(vols_d) >= 11 else 0
        except Exception:
            pass

        rvol = round(volume / avg_vol_daily, 2) if avg_vol_daily > 0 else 0.0

        # Float via Finnhub
        float_shares = 0.0
        if FINNHUB_KEY:
            try:
                fh_r = requests.get(
                    f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_KEY}",
                    timeout=4).json()
                outstanding = float(fh_r.get("shareOutstanding", 0) or 0)
                float_shares = outstanding * 1_000_000
            except Exception:
                pass

        float_m = round(float_shares / 1_000_000, 1) if float_shares else 0

        # ── DÉTECTION DES SETUPS ROSS CAMERON ─────
        setup_detected = None
        setup_details  = ""
        nb_bars        = len(closes)

        above_vwap  = price > vwap
        above_open  = price > open_px
        bull_candle = closes[-1] > opens[-1] if closes and opens else False
        rvol_ok     = rvol >= MIN_RVOL

        # 1. GAP & GO — gap fort + momentum continu + above VWAP
        if gap >= 10 and above_vwap and rvol_ok and bull_candle and variation >= 15:
            setup_detected = "Gap & Go"
            setup_details  = f"Gap {gap:+.1f}% | Prix au-dessus VWAP | Momentum continu"

        # 2. HOD BREAKOUT — cassure du plus haut du jour avec volume
        elif price >= hod * 0.998 and price > hod * 0.99 and rvol_ok and bull_candle and nb_bars > 10:
            setup_detected = "HOD Breakout"
            setup_details  = f"Cassure HOD ${hod:.2f} | RVOL {rvol:.1f}x"

        # 3. ORBO — cassure de l'Opening Range (5 premières minutes)
        elif nb_bars > 5:
            or_high = max(highs[:5]) if len(highs) >= 5 else hod
            if price > or_high and rvol_ok and bull_candle and above_vwap:
                setup_detected = "ORBO"
                setup_details  = f"Cassure Opening Range ${or_high:.2f} | VWAP supporté"

        # 4. FIRST PULLBACK — 1er recul vers VWAP après move fort
        if not setup_detected and variation >= 10 and nb_bars > 10:
            recent_high = max(highs[-10:]) if len(highs) >= 10 else hod
            near_vwap   = abs(price - vwap) / vwap < 0.015  # dans 1.5% du VWAP
            if near_vwap and bull_candle and rvol_ok and price > open_px:
                setup_detected = "First Pullback"
                setup_details  = f"1er recul VWAP ${vwap:.2f} après +{variation:.1f}%"

        # 5. FLAT TOP BREAKOUT — consolidation puis cassure
        if not setup_detected and len(highs) >= 6:
            last_highs = highs[-6:-1]
            if last_highs:
                avg_recent_high = sum(last_highs) / len(last_highs)
                flat_tolerance  = avg_recent_high * 0.005  # 0.5% de tolérance
                is_flat = all(abs(h - avg_recent_high) < flat_tolerance for h in last_highs)
                if is_flat and price > avg_recent_high * 1.003 and rvol_ok and bull_candle:
                    setup_detected = "Flat Top Breakout"
                    setup_details  = f"Cassure résistance ${avg_recent_high:.2f}"

        if not setup_detected:
            return None  # Pas de setup → pas d'alerte

        # Filtres finaux de qualité
        if volume < MIN_VOL_DAY:
            log(f"  ✗ {symbol} — volume insuffisant ({volume:,} < {MIN_VOL_DAY:,})")
            return None

        if not rvol_ok:
            log(f"  ✗ {symbol} — RVOL insuffisant ({rvol:.1f}x < {MIN_RVOL}x)")
            return None

        # Niveaux de trade (ATR approximé)
        if len(highs) >= 14 and len(lows) >= 14:
            true_ranges = [max(highs[i] - lows[i],
                               abs(highs[i] - closes[i-1]),
                               abs(lows[i]  - closes[i-1]))
                           for i in range(1, min(15, len(highs)))]
            atr = sum(true_ranges) / len(true_ranges) if true_ranges else price * 0.02
        else:
            atr = price * 0.02

        stop_loss = round(price - atr * 0.5, 2)
        target1   = round(price + (price - stop_loss) * 2.0, 2)
        target2   = round(price + (price - stop_loss) * 3.0, 2)

        return {
            "symbol":        symbol,
            "price":         price,
            "prev_close":    prev_close,
            "variation":     variation,
            "gap":           gap,
            "volume":        volume,
            "avg_vol_daily": avg_vol_daily,
            "rvol":          rvol,
            "hod":           hod,
            "lod":           lod,
            "vwap":          round(vwap, 2),
            "float_m":       float_m,
            "setup":         setup_detected,
            "setup_details": setup_details,
            "stop_loss":     stop_loss,
            "target1":       target1,
            "target2":       target2,
            "atr":           round(atr, 3),
            "nb_bars":       nb_bars,
        }

    except Exception as e:
        log(f"⚠ Yahoo intraday {symbol}: {e}")
        return None


# ─────────────────────────────────────────────
# ÉTAPE 3 — NEWS
# ─────────────────────────────────────────────
def get_news(symbol):
    news_items = []
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if FINNHUB_KEY:
        try:
            url = (f"https://finnhub.io/api/v1/company-news"
                   f"?symbol={symbol}&from={yesterday}&to={today}&token={FINNHUB_KEY}")
            r   = requests.get(url, timeout=5).json()
            if isinstance(r, list):
                for n in r[:4]:
                    title = n.get("headline", "")
                    if title:
                        news_items.append({"title": title, "source": n.get("source", "")})
        except Exception:
            pass
    return news_items[:4]


# ─────────────────────────────────────────────
# ÉTAPE 4 — ANALYSE AI (Claude)
# ─────────────────────────────────────────────
def analyze_with_ai(stock_data, news):
    if not ANTHROPIC_KEY:
        return None

    symbol = stock_data["symbol"]
    log(f"  🤖 Claude analyse {symbol}...")

    news_text = "\n".join([f"- {n['title']} ({n['source']})" for n in news]) if news else "Aucune news"

    historical_text = get_historical_setup_stats()
    historical_block = ""
    if historical_text:
        historical_block = f"""
═══ PERFORMANCE HISTORIQUE RÉELLE PAR SETUP (tes propres propositions passées) ═══
{historical_text}
Utilise ces données pour calibrer ta conviction.
"""

    lessons_text = get_learned_lessons()
    lessons_block = ""
    if lessons_text:
        lessons_block = f"""
═══ LEÇONS APPRISES (auto-critique rétrospective de tes analyses précédentes) ═══
{lessons_text}
Tiens compte de ces leçons dans ton raisonnement actuel si elles sont pertinentes.
"""

    prompt = f"""Tu es un expert en day trading momentum small cap, méthode Ross Cameron (Warrior Trading).

Il est actuellement {now_et().strftime('%H:%M')} ET — marché en cours.

Analyse ce setup INTRADAY et donne une recommandation immédiate.

═══ DONNÉES INTRADAY ═══
Symbole    : {stock_data['symbol']}
Prix       : ${stock_data['price']:.2f}
Variation  : {stock_data['variation']:+.1f}%
Gap open   : {stock_data['gap']:+.1f}%
HOD        : ${stock_data['hod']:.2f}
LOD        : ${stock_data['lod']:.2f}
VWAP       : ${stock_data['vwap']:.2f}
Volume     : {stock_data['volume']:,}
RVOL       : {stock_data['rvol']:.1f}x
Float      : {stock_data['float_m']:.1f}M (shares outstanding)
Setup      : {stock_data['setup']}
Détails    : {stock_data['setup_details']}

═══ NEWS ═══
{news_text}

═══ NIVEAUX CALCULÉS ═══
Stop Loss  : ${stock_data['stop_loss']:.2f}
Target 1   : ${stock_data['target1']:.2f} (2:1)
Target 2   : ${stock_data['target2']:.2f} (3:1)
{historical_block}{lessons_block}
═══ MISSION ═══
Évalue ce setup intraday selon Ross Cameron. Réponds UNIQUEMENT en JSON:

{{
  "conviction": 7,
  "setup_type": "Gap & Go",
  "timing": "Entrée immédiate",
  "catalyst_quality": "Fort",
  "catalyst_summary": "Résumé du catalyst ou Aucun catalyst identifié",
  "entry_zone": "5.20-5.35",
  "stop_loss": "4.80",
  "target_1": "5.80",
  "target_2": "6.20",
  "risk_reward": "2.5:1",
  "risks": "Principal risque ici",
  "recommendation": "ACHETER",
  "summary": "Résumé 2-3 phrases du setup et pourquoi agir maintenant."
}}

conviction = 1-10 | recommendation = ACHETER / SURVEILLER / ÉVITER
timing = Entrée immédiate / Attendre confirmation / Trop tard
Réponds UNIQUEMENT avec le JSON."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 800,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        log(f"  🤖 Claude API → HTTP {r.status_code}")

        if r.status_code != 200:
            log(f"  ⚠ Claude erreur: {r.text[:200]}")
            return None

        content = r.json()["content"][0]["text"].strip()
        start = content.find("{")
        end   = content.rfind("}") + 1
        if start != -1 and end > start:
            parsed = json.loads(content[start:end])
            log(f"  ✅ Claude → conviction={parsed.get('conviction')} reco={parsed.get('recommendation')}")
            return parsed
        return None

    except Exception as e:
        log(f"  ⚠ Claude {symbol}: {e}")
        return None


# ─────────────────────────────────────────────
# ÉTAPE 5 — FORMAT MESSAGE TELEGRAM
# ─────────────────────────────────────────────
def format_day_message(stock_data, news, ai):
    symbol   = stock_data["symbol"]
    price    = stock_data["price"]
    var      = stock_data["variation"]
    rvol     = stock_data["rvol"]
    hod      = stock_data["hod"]
    vwap     = stock_data["vwap"]
    float_m  = stock_data["float_m"]
    setup    = stock_data["setup"]
    vol      = stock_data["volume"]
    tv_link  = f"https://www.tradingview.com/chart/?symbol={symbol}"
    float_str = f"{float_m:.1f}M" if float_m > 0 else "N/A"
    time_str  = now_et().strftime("%H:%M")

    if ai:
        conviction = ai.get("conviction", 0)
        reco       = ai.get("recommendation", "SURVEILLER")
        timing     = escape_html(ai.get("timing", "—"))
        cat        = escape_html(ai.get("catalyst_summary", "—"))
        entry      = escape_html(ai.get("entry_zone", "—"))
        stop       = escape_html(ai.get("stop_loss", str(stock_data["stop_loss"])))
        t1         = escape_html(ai.get("target_1",  str(stock_data["target1"])))
        t2         = escape_html(ai.get("target_2",  str(stock_data["target2"])))
        rr         = escape_html(ai.get("risk_reward", "2:1"))
        risks      = escape_html(ai.get("risks", "—"))
        summary    = escape_html(ai.get("summary", ""))

        conv_emoji = "🔥🔥🔥" if conviction >= 8 else "✅✅" if conviction >= 6 else "📊" if conviction >= 4 else "⚠️"
        reco_emoji = "🟢" if reco == "ACHETER" else "🟡" if reco == "SURVEILLER" else "🔴"

        msg = (
            f"⚔️ <b>WARRIOR DAY — {setup.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{conv_emoji} <b>{symbol}</b> — Conviction <b>{conviction}/10</b>\n"
            f"{reco_emoji} <b>{reco}</b> — {timing}\n\n"
            f"<b>📊 Données :</b>\n"
            f"  💰 Prix : <b>${price:.2f}</b>\n"
            f"  📈 Var : <b>{var:+.1f}%</b>\n"
            f"  🏔 HOD : <b>${hod:.2f}</b>\n"
            f"  〰️ VWAP : <b>${vwap:.2f}</b>\n"
            f"  ⚡ RVOL : <b>{rvol:.1f}x</b>\n"
            f"  📦 Vol : <b>{vol:,}</b>\n"
            f"  🎯 Float : <b>{float_str}</b>\n\n"
            f"<b>🔬 Setup :</b> {escape_html(setup)}\n"
            f"<b>📰 Catalyst :</b> {cat}\n\n"
            f"<b>🎯 Plan de trade :</b>\n"
            f"  Entrée  : <b>${entry}</b>\n"
            f"  Stop    : <b>${stop}</b>\n"
            f"  Target1 : <b>${t1}</b>\n"
            f"  Target2 : <b>${t2}</b>\n"
            f"  R/R     : <b>{rr}</b>\n\n"
            f"<b>⚠️ Risques :</b> {risks}\n\n"
        )

        if summary:
            msg += f"<b>🤖 Analyse :</b>\n{summary}\n\n"

        if news:
            msg += "<b>📰 News :</b>\n"
            for n in news[:2]:
                msg += f"  • {escape_html(n['title'][:65])}\n"
            msg += "\n"

    else:
        # Sans analyse AI — message basique
        msg = (
            f"⚔️ <b>WARRIOR DAY — {escape_html(setup)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{symbol}</b>\n"
            f"  💰 Prix : ${price:.2f}\n"
            f"  📈 Var : {var:+.1f}%\n"
            f"  🏔 HOD : ${hod:.2f}\n"
            f"  〰️ VWAP : ${vwap:.2f}\n"
            f"  ⚡ RVOL : {rvol:.1f}x\n"
            f"  🎯 Float : {float_str}\n\n"
        )
        if news:
            msg += "<b>📰 News :</b>\n"
            for n in news[:2]:
                msg += f"  • {escape_html(n['title'][:65])}\n"
            msg += "\n"

    msg += f"📈 <a href='{tv_link}'>Voir sur TradingView</a>\n"
    msg += f"⏰ {time_str} ET"
    return msg


# ─────────────────────────────────────────────
# GESTION DES DOUBLONS
# ─────────────────────────────────────────────
def should_alert(symbol, setup, price):
    """
    Retourne True si on doit envoyer une alerte.
    Évite les doublons pour le même stock pendant 30 min,
    sauf si le setup a changé ou le prix a bougé de +5%.
    """
    now = now_et()
    if symbol not in alertes_envoyees:
        return True

    last = alertes_envoyees[symbol]
    minutes_since = (now - last["sent_at"]).total_seconds() / 60

    # Nouveau setup différent → alerter
    if last["setup"] != setup:
        return True

    # Prix a bougé de +5% depuis dernière alerte → alerter
    if last["price"] > 0 and abs(price - last["price"]) / last["price"] >= 0.05:
        return True

    # Cooldown pas écoulé
    if minutes_since < COOLDOWN_MINUTES:
        log(f"  ⏭ {symbol} — cooldown ({minutes_since:.0f}/{COOLDOWN_MINUTES} min)")
        return False

    return True

def mark_alerted(symbol, setup, price):
    alertes_envoyees[symbol] = {
        "setup":    setup,
        "sent_at":  now_et(),
        "price":    price
    }


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL (un cycle de scan)
# ─────────────────────────────────────────────
def run_scan():
    now = now_et()
    log("=" * 50)
    log(f"⚔️  WARRIOR DAY AGENT — Scan {now.strftime('%H:%M')} ET")
    log("=" * 50)

    if not is_market_open():
        log("⏸ Marché fermé — scan ignoré")
        return

    # 1. Récupérer candidats
    candidates = get_intraday_candidates()
    if not candidates:
        log("Aucun candidat trouvé")
        return

    log(f"🔍 {len(candidates)} candidats — analyse des top {min(TOP_N, len(candidates))}")
    alerts_sent = 0

    # 2. Analyser chaque candidat
    for cand in candidates[:TOP_N]:
        symbol = cand["symbol"]
        log(f"\n── {symbol} ──")

        # Données intraday complètes + détection setup
        data = get_intraday_data(symbol)
        if not data:
            log(f"  ✗ {symbol} — pas de setup détecté ou données insuffisantes")
            continue

        log(f"  ✅ Setup: {data['setup']} | Prix ${data['price']:.2f} | "
            f"Var {data['variation']:+.1f}% | RVOL {data['rvol']:.1f}x | HOD ${data['hod']:.2f}")

        # Vérifier si on doit alerter
        if not should_alert(symbol, data["setup"], data["price"]):
            continue

        # News
        news = get_news(symbol)
        log(f"  📰 {len(news)} news")

        # Analyse Claude
        ai = analyze_with_ai(data, news)

        # Filtre conviction minimum
        if ai and ai.get("conviction", 0) < 5:
            log(f"  ⏭ {symbol} — conviction trop faible ({ai.get('conviction')}/10)")
            continue

        if ai and ai.get("recommendation") == "ÉVITER":
            log(f"  ⏭ {symbol} — Claude recommande ÉVITER")
            continue

        # Envoyer le signal à warrior_local.py — c'est cet appel qui manquait
        # dans la version originale du Day Agent.
        send_webhook(data, ai)

        # Envoyer alerte Telegram
        msg = format_day_message(data, news, ai)
        if send_telegram(msg):
            mark_alerted(symbol, data["setup"], data["price"])
            alerts_sent += 1

        time.sleep(1)

    log(f"\n✅ Scan terminé — {alerts_sent} alertes envoyées")


# ─────────────────────────────────────────────
# MESSAGE DE DÉMARRAGE (une fois par jour, au premier cycle)
# ─────────────────────────────────────────────
def send_startup_message_if_first_run():
    now = now_et()
    if now.hour == 9 and now.minute < 35:
        send_telegram(
            f"⚔️ <b>WARRIOR DAY AGENT</b> — Démarré\n"
            f"📅 Scan toutes les {SCAN_INTERVAL//60} min\n"
            f"⏰ 9h30–16h00 ET\n"
            f"🔕 Alertes seulement si signal détecté"
        )


# ─────────────────────────────────────────────
# EXÉCUTION — un seul cycle de scan puis on quitte
# ─────────────────────────────────────────────
# NOTE: ce script est lancé en sous-processus toutes les 5 min par
# scheduler.py (le vrai scheduler tourne côté Railway, dans scheduler.py,
# qui gère lui-même son propre serveur keepalive). Ce script ne doit donc
# PAS boucler ni ouvrir de serveur keepalive lui-même — l'ancienne version
# le faisait (thread + socketserver.TCPServer en écoute permanente sur le
# port Railway), ce qui empêchait tout relancement ultérieur de prendre
# le port ("OSError: Address already in use") et crashait la quasi-totalité
# des cycles de 5 min toute la journée.
if __name__ == "__main__":
    log("🚀 Warrior Day Agent — cycle de scan")
    send_startup_message_if_first_run()
    try:
        run_scan()
    except Exception as e:
        log(f"⚠ Erreur scan: {e}")
    finally:
        save_alertes(alertes_envoyees)
    log("✅ Cycle terminé — le prochain sera relancé par scheduler.py dans 5 min")
