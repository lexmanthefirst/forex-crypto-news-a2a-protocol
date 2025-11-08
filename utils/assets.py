from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Iterable

# Centralized lookup tables for supported crypto assets and forex currencies.
# The alias map intentionally prefers well known assets to avoid matching obscure tokens.

_CRYPTO_ALIAS_SOURCE: dict[str, str] = {
    # Major Cryptocurrencies
    "BTC": "bitcoin",
    "BITCOIN": "bitcoin",
    "XBT": "bitcoin",
    "ETH": "ethereum",
    "ETHEREUM": "ethereum",
    "XRP": "ripple",
    "RIPPLE": "ripple",
    "LTC": "litecoin",
    "LITECOIN": "litecoin",
    "BCH": "bitcoin-cash",
    "BITCOIN CASH": "bitcoin-cash",
    "SOL": "solana",
    "SOLANA": "solana",
    "ADA": "cardano",
    "CARDANO": "cardano",
    "DOT": "polkadot",
    "POLKADOT": "polkadot",
    "DOGE": "dogecoin",
    "DOGECOIN": "dogecoin",
    "MATIC": "matic-network",
    "POLYGON": "matic-network",
    "AVAX": "avalanche-2",
    "AVALANCHE": "avalanche-2",
    "LINK": "chainlink",
    "CHAINLINK": "chainlink",
    "UNI": "uniswap",
    "UNISWAP": "uniswap",
    "ATOM": "cosmos",
    "COSMOS": "cosmos",
    "BNB": "binancecoin",
    "BINANCE COIN": "binancecoin",
    "USDT": "tether",
    "TETHER": "tether",
    "USDC": "usd-coin",
    "TRX": "tron",
    "TRON": "tron",
    "TON": "the-open-network",
    "XLM": "stellar",
    "STELLAR": "stellar",
    "SHIB": "shiba-inu",
    "SHIBA INU": "shiba-inu",
    "APT": "aptos",
    "APTOS": "aptos",
    "ARB": "arbitrum",
    "ARBITRUM": "arbitrum",
    "OP": "optimism",
    "OPTIMISM": "optimism",
    "INJ": "injective-protocol",
    "INJECTIVE": "injective-protocol",
    "SUI": "sui",
    "NEAR": "near",
    "FET": "fetch-ai",
    "FETCH": "fetch-ai",
    "PEPE": "pepe",
    "WIF": "dogwifcoin",
    "DOGWIFCOIN": "dogwifcoin",
    "BONK": "bonk",
    "FTM": "fantom",
    "FANTOM": "fantom",
    "ALGO": "algorand",
    "ALGORAND": "algorand",
    "VET": "vechain",
    "VECHAIN": "vechain",
    "ICP": "internet-computer",
    "INTERNET COMPUTER": "internet-computer",
    "FIL": "filecoin",
    "FILECOIN": "filecoin",
    "HBAR": "hedera-hashgraph",
    "HEDERA": "hedera-hashgraph",
    "APE": "apecoin",
    "APECOIN": "apecoin",
    "SAND": "the-sandbox",
    "THE SANDBOX": "the-sandbox",
    "MANA": "decentraland",
    "DECENTRALAND": "decentraland",
    "AXS": "axie-infinity",
    "AXIE": "axie-infinity",
    "THETA": "theta-token",
    "XTZ": "tezos",
    "TEZOS": "tezos",
    "EOS": "eos",
    "AAVE": "aave",
    "MKR": "maker",
    "MAKER": "maker",
    "GRT": "the-graph",
    "THE GRAPH": "the-graph",
    "SNX": "synthetix-network-token",
    "SYNTHETIX": "synthetix-network-token",
    "CRV": "curve-dao-token",
    "CURVE": "curve-dao-token",
    "LDO": "lido-dao",
    "LIDO": "lido-dao",
    "QNT": "quant-network",
    "QUANT": "quant-network",
    "STX": "blockstack",
    "STACKS": "blockstack",
    "IMX": "immutable-x",
    "IMMUTABLE": "immutable-x",
    "RUNE": "thorchain",
    "THORCHAIN": "thorchain",
    "KAVA": "kava",
    "KAVA": "kava",
    "ZEC": "zcash",
    "ZCASH": "zcash",
    "DASH": "dash",
    "XMR": "monero",
    "MONERO": "monero",
    "ETC": "ethereum-classic",
    "ETHEREUM CLASSIC": "ethereum-classic",
    "GALA": "gala",
    "GALA GAMES": "gala",
}

# The alias map is case-insensitive, but we keep both upper and lower case versions for speed.
CRYPTO_ALIAS_MAP: dict[str, str] = {
    alias.upper(): coin_id for alias, coin_id in _CRYPTO_ALIAS_SOURCE.items()
}
CRYPTO_LOWER_MAP: dict[str, str] = {
    alias.lower(): coin_id for alias, coin_id in _CRYPTO_ALIAS_SOURCE.items()
}

# Common fiat currency codes used when parsing forex pairs.
KNOWN_CURRENCY_CODES: set[str] = {
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD",
    "CNY", "SEK", "NOK", "DKK", "SGD", "HKD", "KRW", "INR",
    "MXN", "ZAR", "TRY", "BRL", "RUB", "PLN", "THB", "MYR",
}


def get_coin_id(value: str | None) -> str | None:
    """Resolve a coin identifier from any known alias.

    Args:
        value: Symbol, name, or alias (case-insensitive).

    Returns:
        CoinGecko identifier (e.g. ``bitcoin``) or ``None`` if unknown.
    """
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None

    upper = candidate.upper()
    if upper in CRYPTO_ALIAS_MAP:
        return CRYPTO_ALIAS_MAP[upper]

    lower = candidate.lower()
    return CRYPTO_LOWER_MAP.get(lower)


def iter_coin_aliases() -> Iterable[tuple[str, str]]:
    """Iterate over alias → coin id pairs (uppercase keys)."""
    return CRYPTO_ALIAS_MAP.items()


@lru_cache(maxsize=1)
def get_coin_metadata() -> list[dict[str, str]]:
    """Return metadata for supported coins (id, symbol, name)."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for alias, coin_id in _CRYPTO_ALIAS_SOURCE.items():
        if alias not in grouped[coin_id]:
            grouped[coin_id].append(alias)

    metadata: list[dict[str, str]] = []
    for coin_id, aliases in grouped.items():
        symbol = _select_symbol(aliases)
        name = _select_name(coin_id, aliases)
        metadata.append({
            "id": coin_id,
            "symbol": symbol,
            "name": name,
        })
    metadata.sort(key=lambda item: item["symbol"])  # deterministic ordering
    return metadata


def _select_symbol(aliases: list[str]) -> str:
    """Pick the most plausible trading symbol from known aliases."""
    symbol_candidates = [alias for alias in aliases if alias.isalpha() and alias.upper() == alias and len(alias) <= 5]
    if symbol_candidates:
        # Keep deterministic order: aliases come from insertion order, so pick first
        return symbol_candidates[0].upper()
    # Fallback: prefer alias without spaces
    no_space = [alias.replace(" ", "") for alias in aliases]
    if no_space:
        chosen = sorted(no_space, key=len)[0]
        return chosen[:5].upper()
    # Last resort: derive from coin id
    return next(iter(aliases)).upper()[:5]


def _select_name(coin_id: str, aliases: list[str]) -> str:
    """Pick a human readable name for the coin."""
    for alias in aliases:
        if " " in alias or alias.title() == alias:
            return alias.title()
    return coin_id.replace("-", " ").title()


__all__ = [
    "CRYPTO_ALIAS_MAP",
    "CRYPTO_LOWER_MAP",
    "KNOWN_CURRENCY_CODES",
    "get_coin_id",
    "get_coin_metadata",
    "iter_coin_aliases",
]
