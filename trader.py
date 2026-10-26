"""Polymarket CLOB trading helpers – credentials from env only."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from py_clob_client_v2 import (
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
    ClobClient,
    OrderArgs,
    OrderType,
    PartialCreateOrderOptions,
    Side,
)

log = logging.getLogger("trader")

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def _load_client() -> ClobClient:
    pk = os.environ.get("PRIVATE_KEY") or os.environ.get("PK")
    if not pk:
        raise RuntimeError("PRIVATE_KEY (or PK) environment variable is required")

    funder = os.environ.get("FUNDER_ADDRESS") or None
    sig_type = int(os.environ.get("SIGNATURE_TYPE", "0"))

    # Prefer pre-exported API creds; otherwise derive them
    api_key = os.environ.get("CLOB_API_KEY")
    api_secret = os.environ.get("CLOB_SECRET")
    api_pass = os.environ.get("CLOB_PASS_PHRASE")

    if api_key and api_secret and api_pass:
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_pass,
        )
        client = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=pk,
            creds=creds,
            signature_type=sig_type,
            funder=funder,
        )
    else:
        # L1 → L2 derivation
        temp = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=pk,
            signature_type=sig_type,
            funder=funder,
        )
        creds = temp.create_or_derive_api_key()
        client = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=pk,
            creds=creds,
            signature_type=sig_type,
            funder=funder,
        )
        log.info("Derived CLOB API credentials from private key")

    return client


class Trader:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.client = _load_client()

    def get_collateral_balance(self) -> float:
        """Return available pUSD balance (float)."""
        try:
            result = self.client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            # balance is in micro-units (1e6)
            bal = int(result.get("balance") or 0) / 1e6
            return bal
        except Exception as e:
            log.error("get_balance_allowance failed: %s", e)
            return 0.0

    def place_market_buy(
        self,
        token_id: str,
        usdc_amount: float,
        tick_size: str = "0.01",
        neg_risk: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Buy approximately `usdc_amount` of the given outcome token
        using an aggressive limit order near the best ask.
        """
        if usdc_amount <= 0:
            log.warning("Skipping zero-size order")
            return None

        if self.dry_run:
            log.info(
                "[DRY_RUN] Would buy ~$%.2f of token %s...",
                usdc_amount,
                token_id[:16],
            )
            return {
                "status": "dry_run",
                "amount": usdc_amount,
                "token_id": token_id,
            }

        try:
            # Get current best ask to size the order
            book = self.client.get_order_book(token_id)
            asks = getattr(book, "asks", None) or (
                book.get("asks") if isinstance(book, dict) else []
            )
            if not asks:
                log.warning(
                    "No asks for token %s – cannot market buy", token_id[:16]
                )
                return None

            def _price(a):
                if hasattr(a, "price"):
                    return float(a.price)
                return float(a.get("price", 1))

            best_ask = min((_price(a) for a in asks), default=0.99)
            if best_ask <= 0 or best_ask >= 1:
                best_ask = 0.99

            # size in shares ≈ usdc / price
            size = round(usdc_amount / best_ask, 2)
            if size < 1:
                size = 1.0

            # Slightly aggressive limit to increase fill chance
            price = min(round(best_ask + 0.01, 2), 0.99)

            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=Side.BUY,
            )
            options = PartialCreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            )

            resp = self.client.create_and_post_order(
                order_args=order_args,
                options=options,
                order_type=OrderType.GTC,
            )
            log.info("Order placed: %s", resp)
            return resp if isinstance(resp, dict) else {"raw": str(resp)}
        except Exception as e:
            log.error("place_market_buy failed: %s", e)
            return None
