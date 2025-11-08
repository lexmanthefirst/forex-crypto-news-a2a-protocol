"""Lightweight alias helpers that delegate to the centralized assets list.

This module keeps the original public API used by tests and other
modules (resolve_coin_alias, fetch_coin_list) but uses the fast,
in-memory `utils.assets` mapping rather than fetching the full
CoinGecko list on startup. This avoids heavy network calls and keeps
alias resolution deterministic and fast.
"""
from __future__ import annotations

from typing import Any

from utils.assets import get_coin_id, get_coin_metadata


def fetch_coin_list() -> list[dict[str, Any]]:
    """Return a lightweight local coin metadata list.

    Previously this fetched CoinGecko's /coins/list and cached it. For our
    use-case we keep a small, deterministic metadata set derived from
    `utils.assets` which is fast and reliable in constrained environments.
    """
    return get_coin_metadata()


def resolve_coin_alias(query: str) -> str | None:
    """Resolve an alias/symbol/name to a CoinGecko ID using `utils.assets`.

    This keeps the original function name for compatibility while delegating
    to the single source of truth in `utils.assets`.
    """
    return get_coin_id(query)


__all__ = ["fetch_coin_list", "resolve_coin_alias"]
