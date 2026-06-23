"""
⚔️ WARRIOR AI AGENT — Pre-Market Edition
Scan pre-market → AI analysis → Telegram recommendations
Ross Cameron methodology
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
FMP_KEY       = os.environ.get("FMP_KEY",       "U87EgtNaQOdshmSkc0IgEtCFcgqTDjvy")
FINNHUB_KEY   = os.environ.get("FINNHUB_KEY",   "d8cf7k9r01qidic7msv0d8cf7k9r01qidic7msvg")
TG_TOKEN      = os.environ.get("TG_TOKEN",      "")
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID",    "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")

ET = pytz.timezone("America/New_York")
now_et = datetime.now(ET)

# Critères pre-market
MIN_PRIX  = 0.50
MAX_PRIX  = 20.0
MIN_GAP   = 5.0      # Gap minimum +5%
MIN_VOL   = 50_000   # Volume minimum (appliqué sur données Yahoo, pas FMP Gainers)
MAX_FLOAT = 50.0     # Float max 50M
TOP_N     = 5        # Top 5 stocks analysés

print("=" * 60)
print("  ⚔️  WARRIOR AI AGENT — PRE-MARKET")
print(f"  {now_et.strftime('%Y-%m-%d %H:%M')} ET")
print("=" * 60)


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram(message, parse_mode="HTML"):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("  ⚠ Telegram non configuré")
        print(f"  MESSAGE:\n{message}\n")
        return
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
            print("  ✅ Telegram envoyé")
        else:
            print(f"  ⚠ Telegram erreur {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  ⚠ Telegram: {e}")


# ─────────────────────────────────────────────
# ÉTAPE 1 — SCANNER PRE-MARKET
# ─────────────────────────────────────────────
def get_premarket_gappers():
    """
    Trouve les meilleurs gappers pre-market.
    Sources (toutes gratuites, sans FMP) :
      1. Yahoo Finance screener — gainers pre-market
      2. Finnhub — top symbols avec variation élevée
      3. Yahoo Finance screener — most active (fallback)
    """
    print("\n  📡 Scan pre-market en cours...")
    candidates = []

    # ── Source 1 — Yahoo Finance Screener (gainers) ────────────────────
    # Pas de clé API requise. Retourne les plus grands gagnants du jour
    # incluant la session pre-market quand appelé avant 9h30 ET.
    try:
        url = (
            "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            "?formatted=false&lang=en-US&region=US&scrIds=day_gainers"
            "&count=50&start=0"
        )
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=10)
        print(f"  Yahoo Screener Gainers → HTTP {r.status_code}")

        data = r.json()
        quotes = (
            data.get("finance", {})
                .get("result", [{}])[0]
                .get("quotes", [])
        )
        print(f"  Yahoo Screener raw → {len(quotes)} entrées")

        for q in quotes:
            symbol = q.get("symbol", "")
            price  = float(q.get("regularMarketPrice", 0) or 0)
            change = float(q.get("regularMarketChangePercent", 0) or 0)
            volume = int(q.get("regularMarketVolume", 0) or 0)
            # Pre-market price si dispo
            pre_px = float(q.get("preMarketPrice", 0) or 0)
            pre_ch = float(q.get("preMarketChangePercent", 0) or 0)
            if pre_px and pre_ch:
                price  = pre_px
                change = pre_ch

            passed = (
                symbol
                and len(symbol) <= 5
                and MIN_PRIX <= price <= MAX_PRIX
                and change >= MIN_GAP
                and not any(symbol.endswith(x) for x in ["W", "U", "R"])
            )
            if passed:
                candidates.append({
                    "symbol": symbol,
                    "price":  price,
                    "change": change,
                    "volume": volume,
                    "source": "Yahoo Gainers"
                })
            else:
                print(f"    ✗ {symbol or '?'} — price={price:.2f} chg={change:.1f}%")

        print(f"  Yahoo Gainers → {len(candidates)} gappers après filtres")

    except Exception as e:
        print(f"  ⚠ Yahoo Screener Gainers exception: {e}")

    # ── Source 2 — Finnhub Stock Screener ─────────────────────────────
    # Utilise la clé Finnhub existante pour compléter si < 3 candidats
    if FINNHUB_KEY and len(candidates) < 5:
        try:
            url = f"https://finnhub.io/api/v1/stock/symbol?exchange=US&token={FINNHUB_KEY}"
            # Finnhub n'a pas de screener direct gratuit — on utilise
            # les quotes sur une watchlist statique de symboles actifs
            # connue pour le momentum (approche: indices small cap)
            # Alternative: on va chercher les news récentes pour détecter
            # les stocks avec catalysts aujourd'hui
            today = datetime.now().strftime("%Y-%m-%d")
            url_news = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
            r_news = requests.get(url_news, timeout=8).json()
            print(f"  Finnhub news → {len(r_news) if isinstance(r_news, list) else 0} articles")

            # Extraire les symboles mentionnés dans les news financières
            import re
            existing = {c["symbol"] for c in candidates}
            symbols_from_news = set()
            if isinstance(r_news, list):
                for article in r_news[:30]:
                    related = article.get("related", "")
                    if related:
                        for sym in related.split(","):
                            sym = sym.strip().upper()
                            if (sym and len(sym) <= 5
                                    and sym not in existing
                                    and not any(sym.endswith(x) for x in ["W", "U", "R"])):
                                symbols_from_news.add(sym)

            print(f"  Finnhub → {len(symbols_from_news)} symboles extraits des news")

            # Vérifier le prix/variation de ces symboles via Yahoo
            for sym in list(symbols_from_news)[:20]:
                try:
                    url_q = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1m&range=1d&includePrePost=true"
                    rq = requests.get(url_q, headers={"User-Agent": "Mozilla/5.0"}, timeout=4).json()
                    meta = rq.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price  = float(meta.get("preMarketPrice", 0) or meta.get("regularMarketPrice", 0) or 0)
                    prev   = float(meta.get("chartPreviousClose", 0) or 0)
                    volume = int(meta.get("regularMarketVolume", 0) or 0)
                    change = round((price - prev) / prev * 100, 2) if prev else 0

                    if (MIN_PRIX <= price <= MAX_PRIX
                            and change >= MIN_GAP
                            and sym not in existing):
                        candidates.append({
                            "symbol": sym,
                            "price":  price,
                            "change": change,
                            "volume": volume,
                            "source": "Finnhub News"
                        })
                        existing.add(sym)
                        print(f"    ✓ {sym} +{change:.1f}% @ ${price:.2f}")
                except Exception:
                    pass
                time.sleep(0.1)

            print(f"  Finnhub → {len(candidates)} total après enrichissement")

        except Exception as e:
            print(f"  ⚠ Finnhub exception: {e}")

    # ── Source 3 — Yahoo Most Active (fallback) ────────────────────────
    if len(candidates) < 3:
        try:
            url = (
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
                "?formatted=false&lang=en-US&region=US&scrIds=most_actives"
                "&count=50&start=0"
            )
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r = requests.get(url, headers=headers, timeout=10)
            print(f"  Yahoo Most Active → HTTP {r.status_code}")

            data   = r.json()
            quotes = (
                data.get("finance", {})
                    .get("result", [{}])[0]
                    .get("quotes", [])
            )
            existing = {c["symbol"] for c in candidates}
            added = 0
            for q in quotes:
                symbol = q.get("symbol", "")
                price  = float(q.get("regularMarketPrice", 0) or 0)
                change = float(q.get("regularMarketChangePercent", 0) or 0)
                volume = int(q.get("regularMarketVolume", 0) or 0)
                pre_px = float(q.get("preMarketPrice", 0) or 0)
                pre_ch = float(q.get("preMarketChangePercent", 0) or 0)
                if pre_px and pre_ch:
                    price  = pre_px
                    change = pre_ch

                if (symbol
                        and symbol not in existing
                        and len(symbol) <= 5
                        and MIN_PRIX <= price <= MAX_PRIX
                        and change >= MIN_GAP
                        and not any(symbol.endswith(x) for x in ["W", "U", "R"])):
                    candidates.append({
                        "symbol": symbol,
                        "price":  price,
                        "change": change,
                        "volume": volume,
                        "source": "Yahoo Most Active"
                    })
                    added += 1
            print(f"  Yahoo Most Active → {added} ajoutés, {len(candidates)} total")

        except Exception as e:
            print(f"  ⚠ Yahoo Most Active exception: {e}")

    # Trier par variation décroissante
    candidates.sort(key=lambda x: x["change"], reverse=True)
    print(f"\n  📋 Candidats retenus ({len(candidates)}):")
    for c in candidates[:10]:
        print(f"    {c['symbol']:6s} +{c['change']:.1f}% vol={c['volume']:,} [{c['source']}]")

    return candidates[:20]


# ─────────────────────────────────────────────
# ÉTAPE 2 — DONNÉES YAHOO FINANCE
# ─────────────────────────────────────────────
def get_yahoo_data(symbol):
    """Données complètes Yahoo Finance pour un stock."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        # Daily pour RVOL et historique
        url_d = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=60d"
        r_d   = requests.get(url_d, headers=headers, timeout=5).json()
        res_d = r_d.get("chart", {}).get("result", [])
        if not res_d:
            print(f"  ⚠ Yahoo daily vide pour {symbol}")
            return None

        meta_d       = res_d[0].get("meta", {})
        q_d          = res_d[0].get("indicators", {}).get("quote", [{}])[0]
        closes       = [c for c in q_d.get("close",  []) if c is not None]
        vols_d       = [v for v in q_d.get("volume", []) if v is not None]
        avg_vol_10   = int(sum(vols_d[-11:-1]) / 10) if len(vols_d) >= 11 else 0
        float_shares = float(meta_d.get("floatShares", 0) or 0)
        market_cap   = float(meta_d.get("marketCap",   0) or 0)
        year_high    = float(meta_d.get("fiftyTwoWeekHigh", 0) or (max(closes) if closes else 0))
        year_low     = float(meta_d.get("fiftyTwoWeekLow",  0) or (min(closes) if closes else 0))

        # Fallback FMP pour float
        if float_shares == 0:
            try:
                fmp_url = f"https://financialmodelingprep.com/api/v3/shares_float?symbol={symbol}&apikey={FMP_KEY}"
                fmp_r   = requests.get(fmp_url, timeout=3).json()
                if isinstance(fmp_r, list) and fmp_r:
                    float_shares = float(fmp_r[0].get("floatShares", 0) or 0)
            except Exception:
                pass

        # Intraday temps réel + pre-market
        url_rt = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?interval=1m&range=1d&includePrePost=true"
        )
        r_rt   = requests.get(url_rt, headers=headers, timeout=5).json()
        res_rt = r_rt.get("chart", {}).get("result", [])
        if not res_rt:
            print(f"  ⚠ Yahoo intraday vide pour {symbol}")
            return None

        meta_rt    = res_rt[0].get("meta", {})
        prix       = float(meta_rt.get("regularMarketPrice", 0) or 0)
        prev_close = float(meta_rt.get("chartPreviousClose", 0) or 0)
        volume     = int(meta_rt.get("regularMarketVolume", 0) or 0)

        # Prix pre-market
        pre_px  = float(meta_rt.get("preMarketPrice",  0) or 0)
        post_px = float(meta_rt.get("postMarketPrice", 0) or 0)

        if pre_px and abs(pre_px - prix) > 0.01:
            current_price = pre_px
            variation = round((pre_px - prev_close) / prev_close * 100, 2) if prev_close else 0
            mode = "Pre-Market"
        elif post_px and abs(post_px - prix) > 0.01:
            current_price = post_px
            variation = round((post_px - prev_close) / prev_close * 100, 2) if prev_close else 0
            mode = "After-Hours"
        else:
            current_price = prix
            variation = round((prix - prev_close) / prev_close * 100, 2) if prev_close else 0
            mode = "Marché"

        # Gap overnight
        q_rt    = res_rt[0].get("indicators", {}).get("quote", [{}])[0]
        opens   = [o for o in q_rt.get("open", []) if o is not None]
        open_px = float(opens[0]) if opens else 0.0
        gap     = round((open_px - prev_close) / prev_close * 100, 2) if (open_px and prev_close) else 0.0

        rvol = round(volume / avg_vol_10, 2) if avg_vol_10 > 0 else 0.0

        # FIX: filtre volume appliqué ici, sur les vraies données Yahoo
        # (pas sur le volume=0 du fallback FMP Gainers)
        if volume < MIN_VOL and avg_vol_10 > 0:
            print(f"  ✗ {symbol} rejeté — volume Yahoo trop faible ({volume:,} < {MIN_VOL:,})")
            return None

        return {
            "symbol":       symbol,
            "price":        current_price,
            "prev_close":   prev_close,
            "variation":    variation,
            "gap":          gap,
            "volume":       volume,
            "avg_vol_10":   avg_vol_10,
            "rvol":         rvol,
            "float_shares": float_shares,
            "float_m":      round(float_shares / 1_000_000, 2) if float_shares else 0,
            "market_cap":   market_cap,
            "year_high":    year_high,
            "year_low":     year_low,
            "mode":         mode,
        }
    except Exception as e:
        print(f"  ⚠ Yahoo {symbol}: {e}")
        return None


# ─────────────────────────────────────────────
# ÉTAPE 3 — NEWS ET CATALYST
# ─────────────────────────────────────────────
def get_news(symbol):
    """Récupère les news du jour pour un stock."""
    news_items = []
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Finnhub news
    if FINNHUB_KEY:
        try:
            url = (
                f"https://finnhub.io/api/v1/company-news"
                f"?symbol={symbol}&from={yesterday}&to={today}&token={FINNHUB_KEY}"
            )
            r = requests.get(url, timeout=5).json()
            if isinstance(r, list):
                for n in r[:5]:
                    news_items.append({
                        "title":  n.get("headline", ""),
                        "source": n.get("source", ""),
                        "url":    n.get("url", ""),
                        "time":   n.get("datetime", 0)
                    })
        except Exception:
            pass

    # FMP news
    try:
        url = f"https://financialmodelingprep.com/stable/news/stock?symbols={symbol}&limit=5&apikey={FMP_KEY}"
        r   = requests.get(url, timeout=5).json()
        if isinstance(r, list):
            for n in r[:3]:
                title = n.get("title", "")
                if title and not any(title == x["title"] for x in news_items):
                    news_items.append({
                        "title":  title,
                        "source": n.get("site", "FMP"),
                        "url":    n.get("url", ""),
                        "time":   0
                    })
    except Exception:
        pass

    return news_items[:6]


# ─────────────────────────────────────────────
# ÉTAPE 4 — INSIDER TRADING
# ─────────────────────────────────────────────
def get_insider_trading(symbol):
    """Récupère les transactions d'initiés récentes."""
    insiders = []

    # FMP Insider Trading
    try:
        url = f"https://financialmodelingprep.com/api/v4/insider-trading?symbol={symbol}&limit=10&apikey={FMP_KEY}"
        r   = requests.get(url, timeout=5).json()
        if isinstance(r, list):
            for t in r[:5]:
                transaction_type = t.get("transactionType", "")
                shares = t.get("securitiesTransacted", 0)
                price  = t.get("price", 0)
                name   = t.get("reportingName", "")
                title  = t.get("typeOfOwner", "")
                date   = t.get("transactionDate", "")
                if transaction_type and shares:
                    insiders.append({
                        "type":   transaction_type,
                        "shares": int(shares or 0),
                        "price":  float(price or 0),
                        "name":   name,
                        "title":  title,
                        "date":   date,
                        "value":  int((shares or 0) * (price or 0))
                    })
    except Exception as e:
        print(f"  ⚠ Insider FMP {symbol}: {e}")

    # OpenInsider
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        url = (
            f"https://openinsider.com/screener?s={symbol}&o=&pl=&ph=&ll=&lh="
            f"&fd=7&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xs=1&vl=&vh="
            f"&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil="
            f"&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=10&action=Filter"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        import re
        purchases = re.findall(r'P - Purchase.*?(\d[\d,]+)', r.text)
        if purchases:
            insiders.append({
                "type":   "Purchase (OpenInsider)",
                "shares": int(purchases[0].replace(",", "")),
                "price":  0,
                "name":   "Insider",
                "title":  "",
                "date":   today,
                "value":  0
            })
    except Exception:
        pass

    return insiders


# ─────────────────────────────────────────────
# ÉTAPE 5 — SHORT INTEREST
# ─────────────────────────────────────────────
def get_short_interest(symbol):
    """Récupère le short interest pour évaluer le squeeze potential."""
    try:
        url = (
            f"https://financialmodelingprep.com/api/v4/short-interest"
            f"?symbol={symbol}&date={datetime.now().strftime('%Y-%m-%d')}&apikey={FMP_KEY}"
        )
        r = requests.get(url, timeout=5).json()
        if isinstance(r, list) and r:
            si = r[0]
            return {
                "short_interest":  si.get("shortInterest", 0),
                "short_pct_float": si.get("shortPercentOfFloat", 0),
                "days_to_cover":   si.get("daysToCover", 0),
            }
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# ÉTAPE 6 — ANALYSE AI (Claude)
# ─────────────────────────────────────────────
def analyze_with_ai(stock_data, news, insiders, short_interest):
    """Claude analyse le stock et génère une recommandation Warrior."""
    if not ANTHROPIC_KEY:
        print("  ⚠ Pas de clé Anthropic — analyse basique")
        return None

    symbol = stock_data["symbol"]
    print(f"  🤖 Claude analyse {symbol}...")

    news_text = "\n".join([f"- {n['title']} ({n['source']})" for n in news]) if news else "Aucune news trouvée"

    insider_text = "Aucune transaction récente"
    if insiders:
        insider_text = "\n".join([
            f"- {i['type']}: {i['shares']:,} shares @ ${i['price']:.2f} par {i['name']} ({i['title']}) le {i['date']}"
            for i in insiders[:3]
        ])

    si_text = "Non disponible"
    if short_interest:
        si_text = f"{short_interest.get('short_pct_float', 0):.1f}% du float vendu à découvert"

    prompt = f"""Tu es un expert en trading momentum small cap, spécialisé dans la méthode Ross Cameron (Warrior Trading).

Analyse ce stock pre-market et donne une recommandation de trading claire.

═══ DONNÉES DU STOCK ═══
Symbole    : {symbol}
Prix       : ${stock_data['price']:.2f}
Variation  : +{stock_data['variation']:.1f}%
Gap        : +{stock_data['gap']:.1f}%
Volume     : {stock_data['volume']:,}
RVOL       : {stock_data['rvol']:.1f}x
Float      : {stock_data['float_m']:.1f}M actions
Mode       : {stock_data['mode']}

═══ NEWS ET CATALYST ═══
{news_text}

═══ INSIDER TRADING ═══
{insider_text}

═══ SHORT INTEREST ═══
{si_text}

═══ TA MISSION ═══
Analyse ce setup selon la méthode Ross Cameron et réponds en JSON avec EXACTEMENT cette structure :

{{
  "conviction": 8,
  "setup_type": "Gap & Go",
  "catalyst_quality": "Fort",
  "catalyst_summary": "FDA approval Phase 3 — très bullish",
  "insider_signal": "Positif — CEO achète",
  "squeeze_potential": "Élevé — 45% short interest",
  "entry_zone": "2.50-2.60",
  "stop_loss": "2.20",
  "target_1": "3.00",
  "target_2": "3.50",
  "risk_reward": "2.5:1",
  "risks": "Float bas, peut faire des spikes violents",
  "recommendation": "ACHETER",
  "summary": "Setup Gap & Go classique Ross Cameron avec catalyst FDA fort. Float de 3.2M = explosive. Entrée sur consolidation au-dessus de $2.50."
}}

conviction = 1-10 (10 = meilleur setup possible)
recommendation = ACHETER, SURVEILLER, ou ÉVITER
Réponds UNIQUEMENT avec le JSON, rien d'autre."""

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
                "max_tokens": 1000,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        if r.status_code == 200:
            content = r.json()["content"][0]["text"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        else:
            print(f"  ⚠ Claude API {r.status_code}: {r.text[:100]}")
            return None
    except Exception as e:
        print(f"  ⚠ Analyse AI {symbol}: {e}")
        return None


# ─────────────────────────────────────────────
# ÉTAPE 7 — FORMAT MESSAGE TELEGRAM
# ─────────────────────────────────────────────
def format_telegram_message(stock_data, news, insiders, ai_analysis):
    """Formate le message Telegram avec l'analyse complète."""
    symbol  = stock_data["symbol"]
    price   = stock_data["price"]
    var     = stock_data["variation"]
    gap     = stock_data["gap"]
    rvol    = stock_data["rvol"]
    float_m = stock_data["float_m"]
    tv_link = f"https://www.tradingview.com/chart/?symbol={symbol}"

    if ai_analysis:
        conviction  = ai_analysis.get("conviction", 0)
        setup_type  = ai_analysis.get("setup_type", "—")
        cat_quality = ai_analysis.get("catalyst_quality", "—")
        cat_summary = ai_analysis.get("catalyst_summary", "—")
        insider_sig = ai_analysis.get("insider_signal", "—")
        squeeze     = ai_analysis.get("squeeze_potential", "—")
        entry       = ai_analysis.get("entry_zone", "—")
        stop        = ai_analysis.get("stop_loss", "—")
        t1          = ai_analysis.get("target_1", "—")
        t2          = ai_analysis.get("target_2", "—")
        rr          = ai_analysis.get("risk_reward", "—")
        risks       = ai_analysis.get("risks", "—")
        reco        = ai_analysis.get("recommendation", "SURVEILLER")
        summary     = ai_analysis.get("summary", "")

        conv_emoji = "🔥🔥🔥" if conviction >= 8 else "✅✅" if conviction >= 6 else "📊" if conviction >= 4 else "⚠️"
        reco_emoji = "🟢" if reco == "ACHETER" else "🟡" if reco == "SURVEILLER" else "🔴"

        msg = (
            f"⚔️ <b>WARRIOR AI — PRE-MARKET</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{conv_emoji} <b>{symbol}</b> — Conviction <b>{conviction}/10</b>\n"
            f"{reco_emoji} <b>{reco}</b>\n\n"
            f"<b>📊 Données :</b>\n"
            f"  💰 Prix : <b>${price:.2f}</b>\n"
            f"  📈 Gap : <b>+{gap:.1f}%</b>  Var : <b>+{var:.1f}%</b>\n"
            f"  ⚡ RVOL : <b>{rvol:.1f}x</b>\n"
            f"  🎯 Float : <b>{float_m:.1f}M</b> actions\n\n"
            f"<b>🔬 Setup :</b> {setup_type}\n\n"
            f"<b>📰 Catalyst :</b> {cat_quality}\n{cat_summary}\n\n"
        )

        if insiders:
            insider_lines = []
            for ins in insiders[:2]:
                emoji = "🟢" if "Purchase" in ins["type"] or "Buy" in ins["type"] else "🔴"
                insider_lines.append(
                    f"  {emoji} {ins['type']}: {ins['shares']:,} @ ${ins['price']:.2f}"
                    f" ({ins['name'][:20]})"
                )
            msg += f"<b>🏛️ Insider Trading :</b>\n" + "\n".join(insider_lines) + "\n\n"
        else:
            msg += f"<b>🏛️ Insider :</b> {insider_sig}\n\n"

        msg += (
            f"<b>📉 Short Squeeze :</b> {squeeze}\n\n"
            f"<b>🎯 Plan de trade :</b>\n"
            f"  Entrée  : <b>${entry}</b>\n"
            f"  Stop    : <b>${stop}</b>\n"
            f"  Target1 : <b>${t1}</b>\n"
            f"  Target2 : <b>${t2}</b>\n"
            f"  R/R     : <b>{rr}</b>\n\n"
            f"<b>⚠️ Risques :</b> {risks}\n\n"
        )

        if summary:
            msg += f"<b>🤖 Analyse AI :</b>\n{summary}\n\n"

    else:
        msg = (
            f"⚔️ <b>WARRIOR PRE-MARKET</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>{symbol}</b>\n"
            f"  💰 Prix : ${price:.2f}\n"
            f"  📈 Gap : +{gap:.1f}%  Var : +{var:.1f}%\n"
            f"  ⚡ RVOL : {rvol:.1f}x\n"
            f"  🎯 Float : {float_m:.1f}M\n\n"
        )
        if news:
            msg += "<b>📰 News :</b>\n"
            for n in news[:3]:
                msg += f"  • {n['title'][:70]}\n"
            msg += "\n"

    if news and ai_analysis:
        msg += "<b>📰 Headlines :</b>\n"
        for n in news[:2]:
            msg += f"  • {n['title'][:60]}\n"
        msg += "\n"

    msg += f"📈 <a href='{tv_link}'>Voir sur TradingView</a>\n"
    msg += f"⏰ {now_et.strftime('%H:%M')} ET"

    return msg


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

send_telegram(
    f"⚔️ <b>WARRIOR AI AGENT</b> — Démarrage scan pre-market\n"
    f"⏰ {now_et.strftime('%H:%M')} ET\n"
    f"🔍 Recherche des meilleurs gappers..."
)

# 1. Scanner
gappers = get_premarket_gappers()

if not gappers:
    send_telegram(
        f"⚔️ <b>WARRIOR AI</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"😴 Aucun gapper significatif ce matin.\n"
        f"⏰ {now_et.strftime('%H:%M')} ET\n"
        f"Relance dans 30 minutes."
    )
    print("\n  Aucun gapper trouvé.")
    exit(0)

print(f"\n  {len(gappers)} gappers trouvés — analyse des top {min(TOP_N, len(gappers))}")

# 2. Analyser chaque gapper
analyses = []

for stock in gappers[:TOP_N]:
    symbol = stock["symbol"]
    print(f"\n  ── {symbol} ──")

    yahoo_data = get_yahoo_data(symbol)
    if not yahoo_data:
        print(f"  ⚠ Pas de données Yahoo pour {symbol}")
        continue

    if yahoo_data["float_m"] > MAX_FLOAT and yahoo_data["float_m"] > 0:
        print(f"  ✗ Float trop élevé ({yahoo_data['float_m']:.1f}M)")
        continue

    print(
        f"  Prix: ${yahoo_data['price']:.2f} | "
        f"Gap: +{yahoo_data['gap']:.1f}% | "
        f"RVOL: {yahoo_data['rvol']:.1f}x | "
        f"Float: {yahoo_data['float_m']:.1f}M | "
        f"Vol: {yahoo_data['volume']:,}"
    )

    news          = get_news(symbol)
    insiders      = get_insider_trading(symbol)
    short_interest = get_short_interest(symbol)
    print(f"  📰 {len(news)} news | 🏛️ {len(insiders)} insiders")

    ai_analysis = analyze_with_ai(yahoo_data, news, insiders, short_interest)

    analyses.append({
        "stock":    yahoo_data,
        "news":     news,
        "insiders": insiders,
        "short":    short_interest,
        "ai":       ai_analysis,
    })

    time.sleep(1)

# 3. Trier par conviction
analyses.sort(
    key=lambda x: x["ai"].get("conviction", 0) if x["ai"] else 0,
    reverse=True
)

# 4. Envoyer
if not analyses:
    send_telegram(
        f"⚔️ <b>WARRIOR AI</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"😴 Aucun stock ne passe les filtres Warrior ce matin.\n"
        f"⏰ {now_et.strftime('%H:%M')} ET"
    )
else:
    summary_lines = []
    for a in analyses:
        s    = a["stock"]
        ai   = a["ai"]
        conv = ai.get("conviction", 0) if ai else 0
        reco = ai.get("recommendation", "?") if ai else "?"
        emoji = "🔥" if conv >= 8 else "✅" if conv >= 6 else "📊"
        summary_lines.append(
            f"{emoji} <b>{s['symbol']}</b> — {conv}/10 — {reco}\n"
            f"   +{s['variation']:.1f}% | RVOL {s['rvol']:.1f}x | Float {s['float_m']:.1f}M"
        )

    send_telegram(
        f"⚔️ <b>WARRIOR AI — RÉSUMÉ PRE-MARKET</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 {len(analyses)} stocks analysés\n"
        f"⏰ {now_et.strftime('%H:%M')} ET\n\n"
        + "\n\n".join(summary_lines)
        + "\n\n🔍 Analyses détaillées en cours..."
    )

    time.sleep(2)

    for a in analyses:
        msg = format_telegram_message(a["stock"], a["news"], a["insiders"], a["ai"])
        send_telegram(msg)
        time.sleep(2)

print(f"\n  ✅ Warrior AI Agent terminé — {len(analyses)} analyses envoyées")
print("=" * 60)

# Keepalive Railway
import http.server
import socketserver
PORT_WEB = int(os.environ.get("PORT", 8080))

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Warrior AI Agent - Online")
    def log_message(self, format, *args):
        pass

with socketserver.TCPServer(("", PORT_WEB), Handler) as httpd:
    print(f"  🌐 Serveur actif sur port {PORT_WEB}")
    httpd.serve_forever()
