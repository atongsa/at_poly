"""Fetch top holders for a market and pick the wallet with the largest share position."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

log = logging.getLogger("holders")

DATA_API = "https://data-api.polymarket.com"


def fetch_top_holders(
    condition_id: str,
    limit: int = 50,
    min_balance: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Return list of holder rows from /v2/holders.

    Each row has at least: amount, outcome_index (or token_id), proxy_wallet, ...
    """
    params = {
        "condition": condition_id,
        "limit": limit,
        "min_balance": min_balance,
    }
    try:
        resp = requests.get(f"{DATA_API}/v2/holders", params=params, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) else body
        if not data:
            return []

        holders: List[Dict[str, Any]] = []
        # Response shape: [{ "token_id": "...", "holders": [ {...}, ... ] }, ...]
        for group in data:
            token_id = group.get("token_id") or group.get("token")
            for h in group.get("holders") or []:
                row = dict(h)
                if token_id and "token_id" not in row:
                    row["token_id"] = token_id
                holders.append(row)
        return holders
    except Exception as e:
        log.error("Failed to fetch holders for %s: %s", condition_id, e)
        return []


def pick_max_share_holder(
    holders: List[Dict[str, Any]],
    up_token: str,
    down_token: str,
) -> Optional[Tuple[str, str, float]]:
    """
    Among all holders, find the one with the largest `amount` (shares).

    Returns (side, token_id, amount) where side is "Up" or "Down".
    """
    if not holders:
        return None

    best = None
    best_amount = -1.0

    for h in holders:
        try:
            amount = float(h.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= best_amount:
            continue

        token_id = str(h.get("token_id") or h.get("asset") or "")
        outcome_index = h.get("outcome_index")

        # Determine side
        side = None
        if token_id == up_token:
            side = "Up"
        elif token_id == down_token:
            side = "Down"
        elif outcome_index is not None:
            # 0 usually Up, 1 Down
            side = "Up" if int(outcome_index) == 0 else "Down"
            token_id = up_token if side == "Up" else down_token

        if side is None:
            continue

        best = (side, token_id, amount)
        best_amount = amount

    return best


def get_max_holder_side(
    condition_id: str,
    up_token: str,
    down_token: str,
) -> Optional[Dict[str, Any]]:
    """
    Convenience: fetch holders + pick max share holder.

    Returns dict with keys: side, token_id, amount, wallet (if available)
    """
    holders = fetch_top_holders(condition_id)
    picked = pick_max_share_holder(holders, up_token, down_token)
    if not picked:
        log.warning("No holders found for condition %s", condition_id)
        return None

    side, token_id, amount = picked

    # try to attach wallet for logging
    wallet = None
    for h in holders:
        try:
            if float(h.get("amount") or 0) == amount:
                wallet = (
                    h.get("proxy_wallet")
                    or h.get("proxyWallet")
                    or h.get("name")
                )
                break
        except (TypeError, ValueError):
            pass

    log.info(
        "Max holder: side=%s amount=%.2f wallet=%s",
        side,
        amount,
        (wallet or "?")[:12],
    )
    return {
        "side": side,
        "token_id": token_id,
        "amount": amount,
        "wallet": wallet,
    }
