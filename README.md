[README.md](https://github.com/user-attachments/files/29227625/README.md)
# ⚔️ Warrior AI Agent — Pre-Market Edition

Agent d'intelligence artificielle spécialisé dans le trading momentum small cap, basé sur la méthode **Ross Cameron (Warrior Trading)**.

Chaque matin en pre-market, l'agent scanne le marché, analyse les meilleurs gappers avec Claude AI, et envoie des recommandations complètes directement sur **Telegram**.

---

## 🚀 Ce que fait l'agent

**Chaque matin automatiquement à :**
- 4h00 ET — Ouverture pre-market
- 6h00 ET — Milieu pre-market
- 8h00 ET — 1h30 avant l'ouverture ⭐ meilleur moment
- 8h30 ET — 1h avant l'ouverture
- 9h00 ET — 30 min avant l'ouverture

**Pour chaque stock qualifié, Claude AI analyse :**

| Source | Données |
|---|---|
| FMP Pre-Market | Prix, gap, volume pre-market |
| Yahoo Finance | RVOL, float, historique 60 jours |
| Finnhub + FMP | News et catalysts du jour |
| FMP Insider | Achats/ventes des dirigeants |
| FMP Short Interest | % float vendu à découvert |

**Et génère un plan de trade complet :**
- Setup détecté (Gap & Go, Bull Flag, ORBO...)
- Qualité du catalyst (FDA, earnings, news...)
- Signal insider trading
- Squeeze potential
- Zone d'entrée, stop loss, target 1 et 2
- Ratio risk/reward
- Score de conviction 1-10
- Recommandation : ACHETER / SURVEILLER / ÉVITER

---

## 📱 Exemple d'alerte Telegram

```
⚔️ WARRIOR AI — PRE-MARKET
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥🔥🔥 SMTK — Conviction 9/10
🟢 ACHETER

📊 Données :
  💰 Prix : $2.45
  📈 Gap : +85.0%  Var : +85.0%
  ⚡ RVOL : 12.0x
  🎯 Float : 3.2M actions

🔬 Setup : Gap & Go

📰 Catalyst : Fort
FDA approval Phase 3 — très bullish

🏛️ Insider Trading :
  🟢 Purchase: 50,000 @ $2.10 (CEO)

📉 Short Squeeze : Élevé — 45% short interest

🎯 Plan de trade :
  Entrée  : $2.50-2.60
  Stop    : $2.20
  Target1 : $3.00
  Target2 : $3.50
  R/R     : 2.5:1

⚠️ Risques : Float bas, spikes violents possibles

🤖 Analyse AI :
Setup Gap & Go classique Ross Cameron avec catalyst
FDA fort. Float de 3.2M = explosive. Entrée sur
consolidation au-dessus de $2.50.

📈 Voir sur TradingView
⏰ 08:00 ET
```

---

## ⚙️ Critères de filtrage

| Critère | Valeur |
|---|---|
| Prix | $0.50 – $20.00 |
| Gap minimum | +5% pre-market |
| Volume minimum | 50,000 actions |
| Float maximum | 50M actions |
| Top analysés | 5 meilleurs gappers |

---

## 🛠️ Architecture

```
Railway Cloud
     │
     ▼
scheduler.py          ← tourne 24/7, lance le scan aux bonnes heures
     │
     ▼
warrior_ai_agent.py   ← pipeline complet
     │
     ├── FMP Pre-Market API    → gappers du matin
     ├── Yahoo Finance         → RVOL, float, historique
     ├── Finnhub + FMP News    → catalyst du jour
     ├── FMP Insider Trading   → transactions dirigeants
     ├── FMP Short Interest    → squeeze potential
     │
     ▼
Claude AI (claude-sonnet-4-6)  → analyse et recommandation
     │
     ▼
📱 Telegram                    → alerte sur ton téléphone
```

---

## 🔑 Variables d'environnement (Railway)

| Variable | Description |
|---|---|
| `FMP_KEY` | Clé API Financial Modeling Prep |
| `FINNHUB_KEY` | Clé API Finnhub |
| `TG_TOKEN` | Token du bot Telegram (@WarriorScannerAlertBot) |
| `TG_CHAT_ID` | Ton Chat ID Telegram |
| `ANTHROPIC_KEY` | Clé API Anthropic (Claude AI) |

---

## 📦 Installation

### 1. Cloner le repo
```bash
git clone https://github.com/bionicfrog-inc/warrior-scanner-.git
```

### 2. Variables d'environnement sur Railway
```
FMP_KEY=ta_cle_fmp
FINNHUB_KEY=ta_cle_finnhub
TG_TOKEN=ton_token_telegram
TG_CHAT_ID=ton_chat_id
ANTHROPIC_KEY=ta_cle_anthropic
```

### 3. Déploiement Railway
Railway détecte automatiquement le `Procfile` et lance `scheduler.py`.

### 4. Clé Anthropic
Obtenir ta clé sur **console.anthropic.com** → API Keys → Create Key.

---

## 📁 Fichiers

| Fichier | Description |
|---|---|
| `warrior_ai_agent.py` | Agent principal — scan + analyse AI + Telegram |
| `scheduler.py` | Lance l'agent aux heures pre-market |
| `requirements.txt` | Dépendances Python |
| `Procfile` | Commande de démarrage Railway |

---

## ⏰ Fenêtre optimale

**8h00 – 9h30 ET (14h00 – 15h30 MTL)**

C'est pendant cette fenêtre que les setups pre-market sont les plus clairs et que les catalysts sont confirmés. Ross Cameron commence toujours son analyse vers 8h00 ET.

---

## ⚠️ Disclaimer

Cet outil est à des fins **éducatives et analytiques uniquement**. Les recommandations de l'AI ne constituent pas des conseils financiers. Le trading de penny stocks comporte des risques élevés — ne jamais risquer plus que ce qu'on peut se permettre de perdre.

---

*Inspiré de la méthode Ross Cameron / Warrior Trading*
