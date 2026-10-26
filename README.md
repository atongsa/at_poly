# at_poly — Polymarket 15-min Crypto Copy-Top-Holder Bot

Auto-trades Polymarket **15-minute Up/Down** markets for **BTC, ETH, SOL, HYPE**.

## Strategy

1. Every ~15 minutes, locate the live 15m Up/Down market for each asset.
2. Query top holders (Data API `/v2/holders`).
3. Identify the wallet that holds the **most shares** on that market (regardless of Up or Down).
4. Copy that side: buy the same outcome the max holder is long.
5. Risk **4% of total collateral** per asset → max ~16% of bankroll across the 4 markets.

## Requirements

- Python 3.10+
- Polygon wallet with pUSD on Polymarket
- Environment variables (never hard-code keys)

```bash
export PRIVATE_KEY="0x..."          # your EOA private key (required)
# optional – if omitted the bot derives API creds from the private key
export CLOB_API_KEY="..."
export CLOB_SECRET="..."
export CLOB_PASS_PHRASE="..."
# optional funder / signature type for proxy wallets
export FUNDER_ADDRESS="0x..."       # proxy/deposit wallet if you use one
export SIGNATURE_TYPE="0"           # 0=EOA, 1=Magic, 2=proxy
```

## Install & Run

```bash
pip install -r requirements.txt
python bot.py
```

Dry-run mode (no real orders):

```bash
export DRY_RUN=1
python bot.py
```

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Main loop |
| `market_finder.py` | Resolve current 15m market + token IDs |
| `holders.py` | Fetch top holders & pick max-share wallet |
| `trader.py` | CLOB client + order placement |
| `requirements.txt` | Dependencies |

## Disclaimer

This is experimental software. You can lose money. Use at your own risk. Not financial advice.
