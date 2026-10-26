"""Locate the active 15-minute Up/Down market for a crypto asset."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import requests

log = logging.getLogger("market_finder")

GAMMA_HOST = "https://gamma-api.polymarket.com"

# slug prefixes used by Polymarket for 15m windows
ASSET_SLUG = {
    "btc": "btc",
    "eth": "eth",
    "sol": "sol",
    "hype": "hype",  # Hyperliquid
}


def current_window_start(window_seconds: int = 900) -> int:
    """Unix timestamp of the start of the current 15-minute window (UTC)."""
    return int(time.time()) // window_seconds * window_seconds


def _slug_candidates(asset: str, window_ts: int) -> list[str]:
    prefix = ASSET_SLUG.get(asset.lower(), asset.lower())
    return [
        f"{prefix}-updown-15m-{window_ts}",
        f"{prefix}-up-or-down-15-minute-windows-{window_ts}",
        f"{prefix}-up-or-down-15m-{window_ts}",
    ]


def _parse_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    markets = event.get("markets") or []
    if not markets:
        return None
    m = markets[0]

    # outcomes are usually ["Up", "Down"]
    outcomes_raw = m.get("outcomes")
    if isinstance(outcomes_raw, str):
        try:
            outcomes = json.loads(outcomes_raw)
        except Exception:
            outcomes = ["Up", "Down"]
    else:
        outcomes = outcomes_raw or ["Up", "Down"]

    token_ids_raw = m.get("clobTokenIds")
    if isinstance(token_ids_raw, str):
        try:
            token_ids = json.loads(token_ids_raw)
        except Exception:
            token_ids = []
    else:
        token_ids = token_ids_raw or []

    if len(token_ids) < 2:
        return None

    # Map outcome name -> token_id
    up_idx = 0
    down_idx = 1
    for i, o in enumerate(outcomes):
        if str(o).lower() in ("up", "yes"):
            up_idx = i
        elif str(o).lower() in ("down", "no"):
            down_idx = i

    return {
        "slug": event.get("slug") or m.get("slug"),
        "condition_id": m.get("conditionId") or m.get("condition_id"),
        "question": m.get("question") or event.get("title"),
        "up_token": str(token_ids[up_idx]),
        "down_token": str(token_ids[down_idx]),
        "tick_size": str(
            m.get("minimum_tick_size") or m.get("orderPriceMinTickSize") or "0.01"
        ),
        "neg_risk": bool(m.get("negRisk") or m.get("neg_risk") or False),
        "active": bool(m.get("active", True)) and not bool(m.get("closed", False)),
        "end_date": m.get("endDate") or event.get("endDate"),
    }


def fetch_market_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(
            f"{GAMMA_HOST}/events",
            params={"slug": slug},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        events = data if isinstance(data, list) else data.get("events", [])
        if not events:
            return None
        return _parse_event(events[0])
    except Exception as e:
        log.debug("slug fetch failed %s: %s", slug, e)
        return None


def get_15m_market(
    asset: str, window_ts: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Return market info for the current (or given) 15-minute window.

    Keys: slug, condition_id, up_token, down_token, tick_size, neg_risk, ...
    """
    if window_ts is None:
        window_ts = current_window_start()

    for slug in _slug_candidates(asset, window_ts):
        info = fetch_market_by_slug(slug)
        if info and info.get("up_token") and info.get("down_token"):
            log.info("Found %s market: %s", asset.upper(), info["slug"])
            return info

    # Fallback: try previous window (in case we are right at the boundary)
    prev_ts = window_ts - 900
    for slug in _slug_candidates(asset, prev_ts):
        info = fetch_market_by_slug(slug)
        if info and info.get("active") and info.get("up_token"):
            log.info(
                "Found %s market (prev window): %s", asset.upper(), info["slug"]
            )
            return info

    log.warning("No 15m market found for %s around ts=%s", asset, window_ts)
    return None
