"""
Intent Classification for Market Analysis Queries

Classifies user queries into specific intent categories using regex patterns
and extracts relevant parameters (coin names, counts, etc.).

Intent Categories:
- price: Get current price of a specific coin
- news: Get news about a specific coin or market
- top: Get top N coins by market cap
- worst: Get worst performing coins
- trending: Get trending coins
- detail: Get detailed information about a coin
- summary: Get market overview/summary
- unknown: Unable to classify

Examples:
    "What's the price of Bitcoin?" → (IntentType.PRICE, {"coin": "bitcoin"})
    "Show me top 10 coins" → (IntentType.TOP, {"count": 10})
    "Latest news about ETH" → (IntentType.NEWS, {"coin": "ethereum"})
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any

from utils.coin_aliases import resolve_coin_alias


class IntentType(str, Enum):
    """Intent categories for market analysis queries."""
    PRICE = "price"
    NEWS = "news"
    TOP = "top"
    WORST = "worst"
    TRENDING = "trending"
    DETAIL = "detail"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class IntentClassifier:
    """Classifies user queries into intent categories."""
    
    # Regex patterns for intent classification
    PATTERNS = {
        IntentType.PRICE: [
            r"\b(?:what(?:'s| is)?|show|get|tell me|check)\s+(?:the\s+)?(?:current\s+)?price\s+(?:of\s+)?(\w+)",
            r"\b(?:how much|price)\s+(?:is\s+)?(\w+)",
            r"\b(\w+)\s+price\b",
        ],
        IntentType.NEWS: [
            r"\b(?:news|headlines?|articles?)\s+(?:about|on|for)\s+(\w+)",
            r"\b(?:latest|recent)\s+(?:news|updates?)\s+(?:about|on|for)?\s*(\w+)?",
            r"\b(\w+)\s+news\b",
        ],
        IntentType.TOP: [
            r"\b(?:top|best)\s+(\d+)?\s*(?:coins?|cryptocurrencies|crypto)",
            r"\b(?:show|get|list)\s+(?:me\s+)?(?:the\s+)?top\s+(\d+)?\s*(?:coins?|cryptocurrencies)?",
        ],
        IntentType.WORST: [
            r"\b(?:worst|bottom)\s+(\d+)?\s*(?:coins?|cryptocurrencies|crypto)",
            r"\b(?:show|get|list)\s+(?:me\s+)?(?:the\s+)?worst\s+(\d+)?\s*(?:coins?|cryptocurrencies)?",
        ],
        IntentType.TRENDING: [
            r"\btrending\s+(?:coins?|cryptocurrencies|crypto)",
            r"\b(?:what(?:'s| is)?|show)\s+trending",
            r"\bhot\s+coins?\b",
        ],
        IntentType.DETAIL: [
            r"\b(?:details?|information|info)\s+(?:about|on|for)\s+(\w+)",
            r"\btell me (?:about|more about)\s+(\w+)",
            r"\b(\w+)\s+(?:details?|information|info)\b",
        ],
        IntentType.SUMMARY: [
            r"\b(?:market|crypto|cryptocurrency)\s+(?:summary|overview|status|update)",
            r"\b(?:summarize|overview of)\s+(?:the\s+)?market",
            r"\b(?:what(?:'s| is)?|how(?:'s| is)?)\s+(?:the\s+)?market\s+(?:doing|looking|today)",
        ],
    }
    
    @staticmethod
    def extract_coin_from_text(text: str) -> str | None:
        """
        Extract coin name/symbol from text and resolve to CoinGecko ID.
        
        Args:
            text: User query text
        
        Returns:
            CoinGecko ID if found, None otherwise
        """
        # Try common crypto names first
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
        for word in words:
            coin_id = resolve_coin_alias(word)
            if coin_id:
                return coin_id
        
        return None
    
    @staticmethod
    def extract_count(text: str, default: int = 10) -> int:
        """
        Extract count/number from text (for "top N coins" queries).
        
        Args:
            text: User query text
            default: Default count if none found
        
        Returns:
            Extracted count or default
        """
        match = re.search(r'\b(\d+)\b', text)
        if match:
            try:
                count = int(match.group(1))
                # Reasonable limits
                return min(max(count, 1), 100)
            except ValueError:
                pass
        return default
    
    def classify(self, text: str) -> tuple[IntentType, dict[str, Any]]:
        """
        Classify user query into intent type and extract parameters.
        
        Args:
            text: User query text
        
        Returns:
            Tuple of (intent_type, params_dict)
        
        Examples:
            >>> classifier = IntentClassifier()
            >>> classifier.classify("What's the price of Bitcoin?")
            (IntentType.PRICE, {"coin": "bitcoin", "query": "What's the price of Bitcoin?"})
            
            >>> classifier.classify("Show me top 10 coins")
            (IntentType.TOP, {"count": 10, "query": "Show me top 10 coins"})
        """
        text_lower = text.lower()
        params: dict[str, Any] = {"query": text}
        
        # Try each intent pattern
        for intent_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    # Extract parameters based on intent
                    if intent_type == IntentType.PRICE:
                        coin_text = match.group(1) if match.groups() else None
                        if coin_text:
                            coin_id = resolve_coin_alias(coin_text)
                            if coin_id:
                                params["coin"] = coin_id
                                return (intent_type, params)
                    
                    elif intent_type == IntentType.NEWS:
                        coin_text = match.group(1) if match.groups() else None
                        if coin_text:
                            coin_id = resolve_coin_alias(coin_text)
                            if coin_id:
                                params["coin"] = coin_id
                        return (intent_type, params)
                    
                    elif intent_type in (IntentType.TOP, IntentType.WORST):
                        count_text = match.group(1) if match.groups() else None
                        count = int(count_text) if count_text else 10
                        params["count"] = min(max(count, 1), 100)
                        return (intent_type, params)
                    
                    elif intent_type == IntentType.DETAIL:
                        coin_text = match.group(1) if match.groups() else None
                        if coin_text:
                            coin_id = resolve_coin_alias(coin_text)
                            if coin_id:
                                params["coin"] = coin_id
                                return (intent_type, params)
                    
                    else:
                        # Trending, Summary - no extra params needed
                        return (intent_type, params)
        
        # Fallback: try to extract any coin mention
        coin_id = self.extract_coin_from_text(text)
        if coin_id:
            params["coin"] = coin_id
            # Guess intent based on presence of other keywords
            if any(word in text_lower for word in ["news", "headlines", "articles", "updates"]):
                return (IntentType.NEWS, params)
            elif any(word in text_lower for word in ["details", "information", "info", "about"]):
                return (IntentType.DETAIL, params)
            else:
                # Default to price if coin is mentioned
                return (IntentType.PRICE, params)
        
        # No clear intent found
        return (IntentType.UNKNOWN, params)
    
    def get_suggested_queries(self, intent_type: IntentType) -> list[str]:
        """
        Get example queries for a given intent type.
        
        Args:
            intent_type: The intent category
        
        Returns:
            List of example query strings
        """
        examples = {
            IntentType.PRICE: [
                "What's the price of Bitcoin?",
                "Show me ETH price",
                "How much is Solana?",
            ],
            IntentType.NEWS: [
                "Latest news about Bitcoin",
                "Show me ETH news",
                "Cryptocurrency headlines",
            ],
            IntentType.TOP: [
                "Top 10 coins",
                "Show me the best cryptocurrencies",
                "List top 5 crypto",
            ],
            IntentType.WORST: [
                "Worst performing coins",
                "Bottom 10 cryptocurrencies",
                "Show me the worst crypto",
            ],
            IntentType.TRENDING: [
                "Trending coins",
                "What's trending in crypto?",
                "Hot cryptocurrencies",
            ],
            IntentType.DETAIL: [
                "Details about Bitcoin",
                "Tell me about Ethereum",
                "Info on Solana",
            ],
            IntentType.SUMMARY: [
                "Market summary",
                "Crypto market overview",
                "How's the market doing?",
            ],
            IntentType.UNKNOWN: [
                "Try asking about specific coins or market trends",
            ],
        }
        return examples.get(intent_type, [])


# Global intent classifier instance
intent_classifier = IntentClassifier()
