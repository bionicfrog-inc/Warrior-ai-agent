"""
⚔️ WARRIOR AI AGENT — Pre-Market Edition
Scan pre-market → AI analysis → Telegram recommendations + Webhook local
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
FMP_KEY           = os.environ.get("FMP_KEY",           "U87EgtNaQOdshmSkc0IgEtCFcgqTDjvy")
FINNHUB_KEY       = os.environ.get("FINNHUB_KEY",       "d8cf7k9r01qidic7msv0d8cf7k9r01qidic7msvg")
TG_TOKEN          = os.environ.get("TG_TOKEN",          "")
TG_CHAT_ID        = os.environ.get("TG_CHAT_ID",        "")
ANTHROPIC_KEY     = os.environ.get("ANTHROPIC_KEY",     "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
LOCAL_WEBHOOK_URL = os.environ.get("LOCAL_WEBHOOK_URL", "")

ET = pytz.timezone("America/New_York")
now_et = datetime.now(ET)

# Critères pre-market
MIN_PRIX  = 0.50
MAX_PRIX  = 20.0
MIN_GAP   = 5.0      # Gap minimum +5%
MIN_VOL   = 50_000   # Volume minimum (appliqué sur données Yahoo, pas FMP Gainers)
MAX_FLOAT = 500.0     # Shares outstanding Finnhub — Claude filtre la qualité du float
TOP_N     = 5        # Top 5 stocks analysés

print("=" * 60)
print("  ⚔️  WARRIOR AI AGENT — PRE-MARKET")
print(f"  {now_et.strftime('%Y-%m-%d %H:%M')} ET")
print("=" * 60)


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def escape_html(text):
    """Échappe les caractères HTML pour Telegram."""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


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
# WEBHOOK LOCAL (PC via ngrok)
# ─────────────────────────────────────────────
def send_webhook(stock_data, ai_analysis):
    """Envoie le signal JSON au PC local (warrior_local.py) via ngrok pour exécution."""
    if not LOCAL_WEBHOOK_URL:
        print("  ⚠ LOCAL_WEBHOOK_URL non configuré — webhook ignoré")
        return
    if not ai_analysis:
        print("  ⚠ Pas d'analyse AI — webhook ignoré")
        return

    conviction = ai_analysis.get("conviction", 0)
    if conviction < 5:
        print(f"  ⏭ Conviction {conviction}/10 < 5 — webhook non envoyé")
        return

    payload = {
        "symbol":         stock_data["symbol"],
        "price":          stock_data["price"],
        "gap":            stock_data["gap"],
        "variation":      stock_data["variation"],
        "rvol":           stock_data["rvol"],
        "float_m":        stock_data["float_m"],
        "conviction":     ai_analysis.get("conviction", 0),
        "recommendation": ai_analysis.get("recommendation", "SURVEILLER"),
        "setup_type":     ai_analysis.get("setup_type", ""),
        "entry_zone":     ai_analysis.get("entry_zone", ""),
        "stop_loss":      ai_analysis.get("stop_loss", ""),
        "target_1":       ai_analysis.get("target_1", ""),
        "target_2":       ai_analysis.get("target_2", ""),
        "risk_reward":    ai_analysis.get("risk_reward", ""),
        "timestamp":      now_et.isoformat(),
    }

    try:
        r = requests.post(
            f"{LOCAL_WEBHOOK_URL}/signal",
            json=payload,
            timeout=8
        )
        if r.status_code == 200:
            print(f"  ✅ Webhook envoyé → {stock_data['symbol']}")
        else:
            print(f"  ⚠ Webhook erreur {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"  ⚠ Webhook exception: {e}")


# ─────────────────────────────────────────────
# ÉTAPE 1 — SCANNER PRE-MARKET
# ─────────────────────────────────────────────
def get_premarket_gappers():
    """
    Trouve les meilleurs gappers pre-market.
    Sources par priorité:
      1. Alpha Vantage TOP_GAINERS_LOSERS — vraie API, données fiables
      2. Finnhub News — symbols mentionnés dans les news du jour
      3. Yahoo Finance screener — fallback si < 3 candidats
    """
    print("\n  📡 Scan pre-market en cours...")
    candidates = {}  # dict pour dédupliquer par symbol

    # ── Source 1 — Alpha Vantage TOP_GAINERS_LOSERS ────────────────────
    # Endpoint dédié aux gainers/losers/most active — le meilleur pour
    # trouver les vrais movers pre-market. 25 req/jour gratuit.
    if ALPHA_VANTAGE_KEY:
        try:
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=TOP_GAINERS_LOSERS&apikey={ALPHA_VANTAGE_KEY}"
            )
            r = requests.get(url, timeout=10)
            print(f"  Alpha Vantage → HTTP {r.status_code}")

            data = r.json()

            # Vérifier si c'est un message d'erreur/info
            if 'Information' in data or 'Note' in data:
                print(f'  ⚠ Alpha Vantage limite: {str(data)[:150]}')
            else:
                # Combiner gainers + most_actively_traded
                pass

            # Combiner gainers + most_actively_traded
            sources = [
                ("top_gainers",          data.get("top_gainers", [])),
                ("most_actively_traded", data.get("most_actively_traded", [])),
            ]

            for src_name, items in sources:
                for s in items:
                    symbol  = s.get("ticker", "")
                    price   = float(s.get("price", 0) or 0)
                    chg_pct = s.get("change_percentage", "0%").replace("%", "")
                    change  = float(chg_pct or 0)
                    volume  = int(s.get("volume", 0) or 0)

                    passed = (
                        symbol
                        and len(symbol) <= 5
                        and MIN_PRIX <= price <= MAX_PRIX
                        and change >= MIN_GAP
                        and not any(symbol.endswith(x) for x in ["W", "U", "R"])
                    )
                    if passed and symbol not in candidates:
                        candidates[symbol] = {
                            "symbol": symbol,
                            "price":  price,
                            "change": change,
                            "volume": volume,
                            "source": f"Alpha Vantage ({src_name})"
                        }
                        print(f"    ✓ {symbol:6s} +{change:.1f}% vol={volume:,} [{src_name}]")

            print(f"  Alpha Vantage → {len(candidates)} candidats après filtres")

        except Exception as e:
            print(f"  ⚠ Alpha Vantage exception: {e}")
    else:
        print("  ⚠ ALPHA_VANTAGE_KEY non configurée — source principale indisponible")

    # ── Source 2 — Finnhub News (catalyst frais) ───────────────────────
    # Extrait les symboles mentionnés dans les news du jour
    if FINNHUB_KEY and len(candidates) < 5:
        try:
            url_news = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
            r_news   = requests.get(url_news, timeout=8).json()
            print(f"  Finnhub news → {len(r_news) if isinstance(r_news, list) else 0} articles")

            symbols_from_news = set()
            if isinstance(r_news, list):
                for article in r_news[:30]:
                    related = article.get("related", "")
                    if related:
                        for sym in related.split(","):
                            sym = sym.strip().upper()
                            if (sym and len(sym) <= 5
                                    and sym not in candidates
                                    and not any(sym.endswith(x) for x in ["W", "U", "R"])):
                                symbols_from_news.add(sym)

            print(f"  Finnhub → {len(symbols_from_news)} symboles extraits des news")

            for sym in list(symbols_from_news)[:20]:
                try:
                    url_q = (
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                        f"?interval=1m&range=1d&includePrePost=true"
                    )
                    rq   = requests.get(url_q, headers={"User-Agent": "Mozilla/5.0"}, timeout=4).json()
                    meta = rq.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price  = float(meta.get("preMarketPrice", 0) or meta.get("regularMarketPrice", 0) or 0)
                    prev   = float(meta.get("chartPreviousClose", 0) or 0)
                    volume = int(meta.get("regularMarketVolume", 0) or 0)
                    change = round((price - prev) / prev * 100, 2) if prev else 0

                    if MIN_PRIX <= price <= MAX_PRIX and change >= MIN_GAP:
                        candidates[sym] = {
                            "symbol": sym,
                            "price":  price,
                            "change": change,
                            "volume": volume,
                            "source": "Finnhub News"
                        }
                        print(f"    ✓ {sym} +{change:.1f}% @ ${price:.2f}")
                except Exception:
                    pass
                time.sleep(0.1)

            print(f"  Finnhub → {len(candidates)} total après enrichissement")

        except Exception as e:
            print(f"  ⚠ Finnhub exception: {e}")

    # ── Source 3 — Yahoo Finance Screener (fallback) ───────────────────
    if len(candidates) < 3:
        try:
            url = (
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
                "?formatted=false&lang=en-US&region=US&scrIds=day_gainers&count=100"
            )
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            r       = requests.get(url, headers=headers, timeout=10)
            print(f"  Yahoo Gainers fallback → HTTP {r.status_code}")

            if r.status_code == 200:
                quotes = (
                    r.json().get("finance", {})
                            .get("result", [{}])[0]
                            .get("quotes", [])
                )
                added = 0
                for q in quotes:
                    symbol = q.get("symbol", "")
                    price  = float(q.get("regularMarketPrice", 0) or 0)
                    change = float(q.get("regularMarketChangePercent", 0) or 0)
                    volume = int(q.get("regularMarketVolume", 0) or 0)
                    pre_px = float(q.get("preMarketPrice", 0) or 0)
                    pre_ch = float(q.get("preMarketChangePercent", 0) or 0)
                    if pre_px and pre_ch:
                        price, change = pre_px, pre_ch

                    if (symbol and symbol not in candidates
                            and len(symbol) <= 5
                            and MIN_PRIX <= price <= MAX_PRIX
                            and change >= MIN_GAP
                            and not any(symbol.endswith(x) for x in ["W", "U", "R"])):
                        candidates[symbol] = {
                            "symbol": symbol, "price": price,
                            "change": change, "volume": volume,
                            "source": "Yahoo Gainers"
                        }
                        added += 1
                print(f"  Yahoo fallback → {added} ajoutés")

        except Exception as e:
            print(f"  ⚠ Yahoo fallback exception: {e}")

    # Trier par variation décroissante
    result = sorted(candidates.values(), key=lambda x: x["change"], reverse=True)
    print(f"\n  📋 {len(result)} candidats retenus:")
    for c in result[:10]:
        print(f"    {c['symbol']:6s} +{c['change']:.1f}% vol={c['volume']:,} [{c['source']}]")

    return result[:20]


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

        # Fallback 1 — Yahoo Finance quote (v10) pour float
        if float_shares == 0:
            try:
                url_q = (
                    f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
                    f"?modules=defaultKeyStatistics"
                )
                rq = requests.get(url_q, headers=headers, timeout=4).json()
                ks = (
                    rq.get("quoteSummary", {})
                      .get("result", [{}])[0]
                      .get("defaultKeyStatistics", {})
                )
                float_shares = float(ks.get("floatShares", {}).get("raw", 0) or 0)
                if float_shares:
                    print(f"  ✓ Float Yahoo quoteSummary: {float_shares/1e6:.1f}M")
            except Exception:
                pass

        # Fallback 2 — Finnhub profile2 (gratuit, pas de 403)
        if float_shares == 0 and FINNHUB_KEY:
            try:
                fh_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_KEY}"
                fh_r   = requests.get(fh_url, timeout=4).json()
                # shareOutstanding est en millions chez Finnhub
                outstanding = float(fh_r.get("shareOutstanding", 0) or 0)
                if outstanding:
                    float_shares = outstanding * 1_000_000
                    print(f"  ✓ Float Finnhub profile2: {outstanding:.1f}M")
            except Exception:
                pass

        if float_shares == 0:
            print(f"  ⚠ Float introuvable pour {symbol} — sera affiché N/A")

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
def get_learned_lessons():
    """
    Récupère les leçons apprises (analyse rétrospective) depuis warrior_local.py.
    Échec silencieux si indisponible — ne bloque jamais un scan.
    """
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

        # FIX (22 juillet): ne garder que les leçons issues du pipeline
        # automatisé réel ("source": "railway"). Les entrées "manuel"
        # viennent de tests/saisies manuelles avec des convictions 10/10
        # mal calibrées au départ (ex: AAPL, SNES, BGDE, LILA, ZCMD, MDCX,
        # INM) — leurs adjustment_suggestion ("plafonner à 3/10", "0/10",
        # etc.) polluaient le scoring du vrai pipeline et créaient un
        # effet de cliquet qui compressait toute conviction vers le bas
        # au fil des jours, sans rapport avec la qualité réelle des
        # setups Gap & Go automatisés.
        lessons = [l for l in lessons if l.get("source") == "railway"]
        # FIX (22 juillet, suite): écarter aussi les leçons construites sur le
        # fallback Yahoo ("candle_source": "yahoo_fallback") côté warrior_local.py
        # — Yahoo peut afficher V:0 par artefact sur le pre-market des small
        # caps, ce qui a généré plusieurs diagnostics "marché mort" erronés
        # (BGDE, MDCX, ATPC...). Ne garder que les leçons basées sur des
        # chandelles OpenD/Moomoo (LV3), fiables sur le volume réel.
        # Les leçons antérieures à ce correctif n'ont pas de champ
        # "candle_source" (absent = None) — traitées comme non fiables,
        # donc exclues par défaut jusqu'à accumulation de nouvelles leçons
        # basées sur OpenD.
        lessons = [l for l in lessons if l.get("candle_source") == "opend"]
        if not lessons:
            return ""

        # Les 10 leçons les plus récentes suffisent — évite un prompt trop long
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
        print(f"  ⚠ Leçons apprises indisponibles: {e}")
        return ""


def get_historical_setup_stats():
    """
    Récupère les stats de performance par setup depuis warrior_local.py (PC).
    Retourne un texte prêt à insérer dans le prompt, ou une chaîne vide
    si indisponible (PC éteint, ngrok down, pas encore de données, etc.)
    — échec silencieux voulu pour ne jamais bloquer un scan.
    """
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
        data  = r.json()
        stats = data.get("setup_stats", {})
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
        print(f"  ⚠ Stats historiques indisponibles: {e}")
        return ""


def analyze_with_ai(stock_data, news, insiders, short_interest):
    """Claude analyse le stock et génère une recommandation Warrior — Gap & Go uniquement (pre-market)."""
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

    historical_text = get_historical_setup_stats()
    historical_block = ""
    if historical_text:
        historical_block = f"""
═══ PERFORMANCE HISTORIQUE RÉELLE PAR SETUP (tes propres propositions passées) ═══
Ces chiffres viennent du suivi réel de tes analyses précédentes (achetées ou non) :
{historical_text}
Utilise ces données pour calibrer ta conviction — si un setup a historiquement bien
performé pour ce système, c'est un bon signe ; s'il performe mal, sois plus prudent.
"""

    lessons_text = get_learned_lessons()
    lessons_block = ""
    if lessons_text:
        lessons_block = f"""
═══ LEÇONS APPRISES (auto-critique rétrospective de tes analyses précédentes) ═══
Après chaque journée, une analyse rétrospective compare tes prédictions au
comportement réel des chandelles (4h00-11h00 ET). Voici tes leçons récentes :
{lessons_text}
Tiens compte de ces leçons dans ton raisonnement actuel si elles sont pertinentes.
"""

    # FIX (22 juillet) : ce scan tourne exclusivement en pre-market (4h-9h ET),
    # avant l'ouverture. Sur les 6 setups Warrior, seul le Gap & Go est
    # observable/vérifiable à ce stade — les 5 autres (ORBO, EMA9 Pullback,
    # HOD Breakout, Flat Top, First Pullback) exigent une séance déjà en
    # cours (range d'ouverture, tendance établie, plus haut de la séance,
    # etc.) qui n'existe pas encore. Présenter ces 6 setups à Claude
    # l'amenait à conclure systématiquement "setup incomplet" → conviction
    # compressée vers le bas. Le prompt ne présente donc plus que le
    # Gap & Go, avec la grille complète de calibration adaptée au pre-market.
    prompt = f"""Tu es un expert en trading momentum small cap, spécialisé dans la méthode Ross Cameron (Warrior Trading).

Ce scan tourne en PRE-MARKET (avant 9h30 ET). À ce stade, le seul setup Warrior
observable et vérifiable est le GAP & GO — les autres setups (ORBO, EMA9 Pullback,
HOD Breakout, Flat Top, First Pullback) nécessitent une séance déjà en cours et ne
peuvent pas être évalués maintenant. N'essaie pas de les identifier ou de les
pénaliser pour ne pas être remplis : ce n'est pas pertinent à ce stade.

Analyse ce stock pre-market et donne une recommandation de trading claire.

═══ DONNÉES DU STOCK ═══
Symbole    : {symbol}
Prix       : ${stock_data['price']:.2f}
Variation  : +{stock_data['variation']:.1f}%
Gap        : +{stock_data['gap']:.1f}%
Volume     : {stock_data['volume']:,}
RVOL       : {stock_data['rvol']:.1f}x
Float      : {stock_data['float_m']:.1f}M actions (shares outstanding — float réel probablement plus bas)
Mode       : {stock_data['mode']}

═══ NEWS ET CATALYST ═══
{news_text}

═══ INSIDER TRADING ═══
{insider_text}

═══ SHORT INTEREST ═══
{si_text}

═══ RÉFÉRENCE — LE SETUP GAP & GO (le seul jouable en pre-market) ═══
- Gap pre-market ≥ 4% avec catalyst identifiable (earnings, FDA, PR, upgrade)
- Volume pre-market déjà élevé par rapport à la moyenne (signe d'intérêt réel, pas juste un drift léger)
- Se joue typiquement dans les 30 premières minutes après l'ouverture (9h30-10h00 ET)
- Entrée classique : cassure du plus haut pre-market ou du plus haut de la 1ère bougie 1 min après 9h30
- Un gap sans catalyst clair est plus à risque de se refermer ("gap fill") — pénaliser la conviction en conséquence, mais un gap avec catalyst solide et volume réel mérite une conviction franche (7-9), pas systématiquement plafonnée

═══ GRILLE DE CALIBRATION (utilise-la comme référence, pas comme plafond automatique) ═══
- 8-10 : gap ≥8%, catalyst news dur et récent (FDA, earnings, PR majeur), volume pre-market réel et soutenu, float compatible avec un squeeze
- 6-7  : gap solide avec catalyst identifiable mais moins spectaculaire, ou volume correct sans catalyst hard news
- 4-5  : gap présent mais catalyst faible/absent ou volume pre-market incertain — surveiller, pas encore une conviction d'entrée
- 1-3  : gap sans catalyst ni volume réel, probable gap fill ou faux signal
{historical_block}{lessons_block}
═══ TA MISSION ═══
Analyse ce setup Gap & Go selon la méthode Ross Cameron et réponds en JSON avec EXACTEMENT cette structure :

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

conviction = 1-10 (10 = meilleur setup possible), utilise toute l'échelle — ne réserve pas les scores élevés à des cas exceptionnels quand la grille de calibration ci-dessus les justifie
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
        print(f"  🤖 Claude API → HTTP {r.status_code}")

        if r.status_code != 200:
            print(f"  ⚠ Claude API erreur {r.status_code}: {r.text[:300]}")
            return None

        raw_json = r.json()
        if not raw_json.get("content"):
            print(f"  ⚠ Claude réponse vide: {str(raw_json)[:200]}")
            return None

        content = raw_json["content"][0]["text"].strip()
        print(f"  🤖 Claude réponse brute ({len(content)} chars): {content[:120]}...")

        # Nettoyage robuste des backticks markdown
        if "```" in content:
            parts = content.split("```")
            # Chercher le bloc JSON entre backticks
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    content = part
                    break

        # Trouver le JSON même si du texte précède/suit
        start = content.find("{")
        end   = content.rfind("}") + 1
        if start != -1 and end > start:
            content = content[start:end]

        parsed = json.loads(content)
        print(f"  ✅ Claude analyse OK — conviction={parsed.get('conviction')} reco={parsed.get('recommendation')}")
        return parsed

    except json.JSONDecodeError as e:
        print(f"  ⚠ Claude JSON invalide pour {symbol}: {e}")
        print(f"  ⚠ Contenu reçu: {content[:300] if 'content' in dir() else 'N/A'}")
        return None
    except Exception as e:
        print(f"  ⚠ Analyse AI {symbol}: {type(e).__name__}: {e}")
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
    tv_link   = f"https://www.tradingview.com/chart/?symbol={symbol}"
    float_str = f"{float_m:.1f}M" if float_m > 0 else "N/A"

    if ai_analysis:
        conviction  = ai_analysis.get("conviction", 0)
        setup_type  = escape_html(ai_analysis.get("setup_type", "—"))
        cat_quality = escape_html(ai_analysis.get("catalyst_quality", "—"))
        cat_summary = escape_html(ai_analysis.get("catalyst_summary", "—"))
        insider_sig = escape_html(ai_analysis.get("insider_signal", "—"))
        squeeze     = escape_html(ai_analysis.get("squeeze_potential", "—"))
        entry       = escape_html(ai_analysis.get("entry_zone", "—"))
        stop        = escape_html(ai_analysis.get("stop_loss", "—"))
        t1          = escape_html(ai_analysis.get("target_1", "—"))
        t2          = escape_html(ai_analysis.get("target_2", "—"))
        rr          = escape_html(ai_analysis.get("risk_reward", "—"))
        risks       = escape_html(ai_analysis.get("risks", "—"))
        reco        = ai_analysis.get("recommendation", "SURVEILLER")
        summary     = escape_html(ai_analysis.get("summary", ""))

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
            f"  🎯 Float : <b>{float_str}</b> actions\n\n"
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
            f"  🎯 Float : {float_str}\n\n"
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

    # Envoi du signal au PC local (paper trading / exécution) via ngrok
    send_webhook(yahoo_data, ai_analysis)

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
        float_disp = f"{s['float_m']:.1f}M" if s['float_m'] > 0 else "N/A"
        summary_lines.append(
            f"{emoji} <b>{s['symbol']}</b> — {conv}/10 — {reco}\n"
            f"   +{s['variation']:.1f}% | RVOL {s['rvol']:.1f}x | Float {float_disp}"
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

# NOTE: aucun serveur keepalive ici — ce script est lancé en sous-processus
# par scheduler.py (toutes les 20 min entre 4h00 et 9h00 ET), qui gère lui
# -même le seul serveur keepalive nécessaire côté Railway. L'ancienne
# version ouvrait ici aussi un socketserver.TCPServer().serve_forever() sur
# le même port que scheduler.py, ce qui empêchait le script de jamais
# se terminer et entrait en conflit de port avec les lancements suivants.
