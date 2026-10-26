#!/usr/bin/env python3
"""
Polymarket 15-minute crypto copy-top-holder bot.

Logic:
  - For BTC / ETH / SOL / HYPE 15m Up-Down markets
  - Find the wallet holding the most shares (any side)
  - Bet the same side
  - Size = 4% of total collateral per market

All secrets come from environment variables.
"""

from __future__ import annotations

import logging
import os
import time
from typing import List

from dotenv import load_dotenv

from holders import get_max_holder_side
from market_finder import current_window_start, get_15m_market
from trader import Trader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")

ASSETS: List[str] = ["btc", "eth", "sol", "hype"]
RISK_PCT = 0.04  # 4% of total collateral per asset
POLL_SECONDS = 30  # how often to check for a new window


def seconds_until_next_window(window_seconds: int = 900) -> int:
    now = int(time.time())
    next_start = (now // window_seconds + 1) * window_seconds
    return max(0, next_start - now)


def run_once(trader: Trader) -> None:
    balance = trader.get_collateral_balance()
    log.info("Collateral balance: $%.2f", balance)
    if balance <= 1:
        log.warning("Balance too low – skipping")
        return

    size_per_market = balance * RISK_PCT
    log.info(
        "Target size per market: $%.2f (%.0f%% of bankroll)",
        size_per_market,
        RISK_PCT * 100,
    )

    window_ts = current_window_start()
    log.info("Trading window start ts=%s", window_ts)

    for asset in ASSETS:
        try:
            market = get_15m_market(asset, window_ts)
            if not market:
                log.warning("[%s] no market found – skip", asset.upper())
                continue

            condition_id = market["condition_id"]
            up_token = market["up_token"]
            down_token = market["down_token"]

            decision = get_max_holder_side(condition_id, up_token, down_token)
            if not decision:
                log.warning("[%s] no max holder – skip", asset.upper())
                continue

            side = decision["side"]
            token_id = decision["token_id"]
            log.info(
                "[%s] following max holder → %s (shares=%.1f, wallet=%s)",
                asset.upper(),
                side,
                decision["amount"],
                (decision.get("wallet") or "?")[:14],
            )

            trader.place_market_buy(
                token_id=token_id,
                usdc_amount=size_per_market,
                tick_size=market.get("tick_size", "0.01"),
                neg_risk=market.get("neg_risk", False),
            )
        except Exception as e:
            log.exception("[%s] error: %s", asset.upper(), e)


def main() -> None:
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        log.info("*** DRY_RUN mode – no real orders will be sent ***")

    trader = Trader(dry_run=dry_run)
    last_window = None

    log.info("Bot started. Assets=%s  risk=%.0f%% each", ASSETS, RISK_PCT * 100)

    while True:
        try:
            window = current_window_start()
            # Trade once per window, a few seconds after it opens
            if window != last_window:
                # small delay so holders have time to appear
                elapsed = int(time.time()) - window
                if elapsed < 20:
                    time.sleep(20 - elapsed)
                run_once(trader)
                last_window = window

            # sleep until next poll or near next window
            wait = min(POLL_SECONDS, seconds_until_next_window() + 5)
            time.sleep(max(5, wait))
        except KeyboardInterrupt:
            log.info("Stopped by user")
            break
        except Exception as e:
            log.exception("Main loop error: %s", e)
            time.sleep(30)


if __name__ == "__main__":
    main()
