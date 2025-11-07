from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

from models.a2a import A2AMessage, Artifact, MessagePart, TaskResult, TaskStatus
from utils.coin_aliases import resolve_coin_alias
from utils.gemini_client import analyze_sync
from utils.market_summary import get_comprehensive_market_summary, format_market_summary_text
from utils.news_fetcher import fetch_combined_news, fetch_crypto_prices, fetch_forex_rate
from utils.notifier import send_console_notification, send_webhook_notification
from utils.prompt_extraction import extract_coin_with_llm
from utils.redis_client import redis_store
from utils.session_store import session_store
from utils.technical_analysis import get_technical_summary
from utils.telex_parser import extract_text_from_telex_message

logger = logging.getLogger(__name__)

# Regex to extract currency pair or coin symbol
# Matches forex pairs like EUR/USD, EUR-USD, or EURUSD
PAIR_RE = re.compile(r"([A-Za-z]{3,5})\s*[/\-]\s*([A-Za-z]{3,5})")
# Matches any crypto symbol (2-5 uppercase letters) as a standalone word
# Common patterns: BTC, ETH, USDT, BNB, SOL, ADA, MATIC, etc.
SYMBOL_RE = re.compile(r"\b([A-Z]{2,5})\b")


class MarketAgent:
    def __init__(self, notifier_webhook: str | None = None, notifier_webhook_token: str | None = None, enable_notifications: bool | None = None):
        self.notifier_webhook = notifier_webhook or os.getenv("NOTIFIER_WEBHOOK")
        self.notifier_webhook_token = notifier_webhook_token or os.getenv("NOTIFIER_WEBHOOK_TOKEN")
        if enable_notifications is None:
            env_value = os.getenv("ENABLE_NOTIFICATIONS", "true").strip().lower()
            enable_notifications = env_value in {"1", "true", "yes", "on"}
        self.enable_notifications = enable_notifications
        self.notification_cooldown = int(os.getenv("NOTIFICATION_COOLDOWN_SECONDS", "900"))
        self.last_notified: dict[str, float] = {}

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and decode HTML entities from text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities (&amp; -> &, &lt; -> <, etc.)
        text = unescape(text)
        # Clean up extra whitespace
        text = ' '.join(text.split())
        return text

    @staticmethod
    def _extract_text_from_message(message: A2AMessage) -> str:
        """
        Robust text extraction from A2A message with multiple fallback strategies.
        
        Handles various message structures from different platforms (Telex, etc.):
        1. Direct text parts (kind="text")
        2. Nested data parts with text fields
        3. File content extraction (if applicable)
        
        Returns:
            Extracted and cleaned text string
        """
        text_parts: list[str] = []
        
        # Strategy 1: Extract from text parts directly
        for part in message.parts:
            if part.kind == "text" and part.text and part.text.strip():
                text_parts.append(part.text.strip())
        
        # Strategy 2: Check data parts for nested text
        if not text_parts:
            for part in message.parts:
                if part.kind == "data" and part.data:
                    # Handle case where data is a dict with text field
                    if isinstance(part.data, dict):
                        if "text" in part.data and part.data["text"]:
                            text_parts.append(str(part.data["text"]).strip())
                        # Check for nested message structures
                        elif "message" in part.data and isinstance(part.data["message"], str):
                            text_parts.append(part.data["message"].strip())
                        # Check for content field
                        elif "content" in part.data and isinstance(part.data["content"], str):
                            text_parts.append(part.data["content"].strip())
                        # Handle nested list in data
                        elif "items" in part.data and isinstance(part.data["items"], list):
                            for item in part.data["items"]:
                                if isinstance(item, str) and item.strip():
                                    text_parts.append(item.strip())
                                elif isinstance(item, dict) and "text" in item:
                                    text_parts.append(str(item["text"]).strip())
                    # Handle case where data is a list directly (Telex compatibility)
                    elif isinstance(part.data, list):
                        for item in part.data:
                            if isinstance(item, str) and item.strip():
                                text_parts.append(item.strip())
                            elif isinstance(item, dict) and "text" in item:
                                text_parts.append(str(item["text"]).strip())
        
        # Combine all extracted text
        combined_text = " ".join(text_parts)
        
        # Strip HTML and clean up
        if combined_text:
            combined_text = MarketAgent._strip_html(combined_text)
        
        return combined_text

    async def process_messages(
        self,
        messages: list[A2AMessage],
        context_id: str | None = None,
        task_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> TaskResult:
        """Main handler invoked by JSON-RPC endpoint. Accepts one or more messages."""
        now = datetime.now(timezone.utc)
        context_id = context_id or f"context-{int(now.timestamp())}"
        task_id = task_id or f"task-{int(now.timestamp())}"
        if not messages:
            raise ValueError("No messages provided")

        user_msg = messages[-1]
        
        # Try enhanced Telex extraction first (if config has params structure)
        text: str | None = None
        conversation_history: list[str] = []
        extraction_debug: dict[str, Any] = {}
        
        if config and isinstance(config, dict):
            # Try Telex-style extraction from params
            text, conversation_history, extraction_debug = extract_text_from_telex_message(config)
            if text:
                logger.info(f"Telex extraction: {extraction_debug.get('source')}, history: {len(conversation_history)} msgs")
        
        # Fallback to standard extraction if Telex extraction failed
        if not text:
            text = self._extract_text_from_message(user_msg)
            extraction_debug = {"source": "fallback_message_extraction"}
        
        # If empty after extraction, return early with helpful error
        if not text or not text.strip():
            raise ValueError("No analyzable text found in message. Please provide a query with cryptocurrency symbol, name, or forex pair (e.g., 'BTC price', 'Bitcoin analysis', 'EUR/USD rate').")

        # Store conversation history if available
        if conversation_history and context_id:
            try:
                for hist_text in conversation_history[-5:]:  # Store last 5 for context
                    hist_msg = A2AMessage(
                        role="user",
                        parts=[MessagePart(kind="text", text=hist_text)]
                    )
                    await session_store.append_message(context_id, hist_msg)
            except Exception as e:
                logger.warning(f"Failed to store conversation history: {e}")
        
        # Store current user message
        try:
            await session_store.append_message(context_id, user_msg)
        except Exception as e:
            logger.warning(f"Failed to store user message: {e}")

        # Check if this is a market summary/overview request
        if self._is_market_summary_request(text):
            return await self._handle_market_summary(messages, context_id, task_id)

        pair = self._extract_pair(text)
        symbol = self._extract_symbol(text)

        price_snapshot: dict[str, Any] = {}
        technical_data: dict[str, Any] = {}
        error_messages: list[str] = []
        
        if pair:
            try:
                forex = await fetch_forex_rate(pair)
                price_snapshot["pair"] = forex
            except Exception as e:
                price_snapshot["pair"] = {"pair": pair, "rate": None}
                error_messages.append(f"Unable to fetch forex rate for {pair}. The API may be unavailable or the pair may not be supported.")
        if symbol:
            try:
                prices = await fetch_crypto_prices([symbol])
                price_snapshot["crypto"] = prices
                # Fetch technical indicators
                technical_data = await get_technical_summary(symbol)
            except Exception as e:
                price_snapshot["crypto"] = {symbol: None}
                error_messages.append(f"Unable to fetch price data for {symbol}. Please verify the coin name/symbol is correct.")

        combined_news = await fetch_combined_news(limit=10)
        relevant = self._filter_relevant_news(combined_news, pair, symbol)
        news_summary = (
            "\n".join(f"• {item.get('title')} ({item.get('source')})" for item in relevant[:5])
            or "No recent headlines found."
        )
        
        # Add technical analysis to context
        if technical_data:
            tech_summary = (
                f"\n\n**Technical Analysis (7-day):**\n"
                f"• Trend: {technical_data.get('trend', 'N/A')}\n"
                f"• Price change: {technical_data.get('change_pct', 0):.2f}%\n"
                f"• Signal: {technical_data.get('signal', 'neutral')}\n"
                f"• Position vs SMA: {technical_data.get('price_position', 'N/A')}"
            )
            news_summary += tech_summary

        loop = asyncio.get_running_loop()
        subject = pair or symbol or "market"
        analysis_result = await loop.run_in_executor(None, analyze_sync, subject, price_snapshot, news_summary)

        analysis_data = self._extract_analysis_data(analysis_result)
        raw_analysis = analysis_data.get("analysis", {})
        analysis = dict(raw_analysis) if isinstance(raw_analysis, dict) else {}
        analysis_ts = analysis_data.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        analysis["ts"] = analysis_ts

        key = (pair or symbol or "market").upper()
        await redis_store.set_latest_analysis(
            key,
            {"analysis": analysis, "news": relevant, "price_snapshot": price_snapshot},
            ex=3600,
        )

        impact = float(analysis.get("impact_score", 0.0) or 0.0)
        if self.enable_notifications and abs(impact) >= float(os.getenv("ANALYSIS_IMPACT_THRESHOLD", "0.5")):
            last = self.last_notified.get(key)
            now_ts = datetime.now(timezone.utc).timestamp()
            if not last or (now_ts - last) >= self.notification_cooldown:
                payload = {
                    "key": key,
                    "impact": impact,
                    "analysis": analysis,
                    "news": relevant[:3],
                    "price_snapshot": price_snapshot,
                }
                asyncio.create_task(send_console_notification(str(payload)))
                if self.notifier_webhook:
                    asyncio.create_task(send_webhook_notification(
                        self.notifier_webhook, 
                        payload, 
                        token=self.notifier_webhook_token
                    ))
                self.last_notified[key] = now_ts

        confidence = float(analysis.get("confidence", 0.0) or 0.0)
        reasons = analysis.get("reasoning") or []
        direction = analysis.get("direction", "neutral")
        
        # Format the analysis message using Markdown
        agent_text = self._format_analysis_message(
            key=key,
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            price_snapshot=price_snapshot,
            technical_data=technical_data,
            news=relevant[:3],
            pair=pair,
            symbol=symbol,
            error_messages=error_messages
        )
        
        # Create agent message with text part only (for Telex display compatibility)
        agent_msg = A2AMessage(
            role="agent", 
            parts=[
                MessagePart(kind="text", text=agent_text),
            ], 
            taskId=task_id
        )

        # Store structured data in artifacts (not in message parts)
        artifacts: list[Artifact] = [
            Artifact(name="analysis", parts=[MessagePart(kind="data", data=analysis)]),
        ]
        if price_snapshot:
            artifacts.append(Artifact(name="price_snapshot", parts=[MessagePart(kind="data", data=price_snapshot)]))
        if technical_data:
            artifacts.append(Artifact(name="technical_indicators", parts=[MessagePart(kind="data", data=technical_data)]))
        # Always include recent_news artifact, even if empty
        artifacts.append(Artifact(name="recent_news", parts=[MessagePart(kind="data", data={"items": relevant[:3] if relevant else []})]))


        status_state = "completed"
        if (pair and price_snapshot.get("pair", {}).get("rate") is None) and (not symbol):
            status_state = "failed"

        task_status = TaskStatus(status=status_state, message=agent_msg)
        
        # Store agent response in session history
        try:
            await session_store.append_message(context_id, agent_msg)
        except Exception as e:
            logger.warning(f"Failed to store agent message: {e}")

        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=messages + [agent_msg],
        )

    def _extract_pair(self, text: str) -> str | None:
        """Extract forex pair from text.
        
        Matches explicit pairs like EUR/USD, EUR-USD first.
        For 6-letter patterns like EURUSD, only accept if it looks like a valid forex pair
        (both halves are common currency codes, not random words like LATEST).
        """
        # Try explicit pair format first (EUR/USD, EUR-USD)
        m = PAIR_RE.search(text)
        if m:
            a, b = m.groups()
            return f"{a.upper()}/{b.upper()}"
        
        # For 6-letter words, validate they look like currency codes
        # Common forex currencies: USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD, CNY, etc.
        valid_currencies = {
            "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", 
            "CNY", "SEK", "NOK", "DKK", "SGD", "HKD", "KRW", "INR",
            "MXN", "ZAR", "TRY", "BRL", "RUB", "PLN", "THB", "MYR"
        }
        
        m2 = re.search(r"\b([A-Za-z]{6})\b", text)
        if m2:
            s = m2.group(1).upper()
            first_half = s[:3]
            second_half = s[3:]
            # Only treat as forex pair if both parts are known currency codes
            if first_half in valid_currencies and second_half in valid_currencies:
                return f"{first_half}/{second_half}"
        
        return None

    def _extract_symbol(self, text: str) -> str | None:
        """Extract cryptocurrency symbol from text using LLM-based extraction.
        
        Uses a prompt-based approach that intelligently:
        - Understands context and ignores command words
        - Handles various coin name formats (BTC, bitcoin, Bitcoin)
        - Avoids false matches with random words
        
        Returns the CoinGecko ID (e.g., "bitcoin") for compatibility with price APIs.
        """
        # Try LLM-based extraction first (most accurate)
        coin_query = extract_coin_with_llm(text)
        if coin_query:
            # Filter out garbage responses (placeholders, weird patterns)
            if "TICKER" in coin_query.upper() or len(coin_query) > 20 or "-" in coin_query:
                logger.warning(f"[LLM] Invalid extraction '{coin_query}', falling back to regex")
                coin_query = None  # Force fallback
            else:
                # Try to resolve to CoinGecko ID
                coin_id = resolve_coin_alias(coin_query)
                if coin_id:
                    logger.info(f"[LLM] Extracted '{coin_query}' -> resolved to '{coin_id}'")
                    return coin_id
                # If not in alias map, use as-is (lowercase)
                logger.info(f"[LLM] Extracted '{coin_query}' (no alias, using lowercase)")
                return coin_query.lower()
        
        # Fallback to legacy crypto_map for common coins
        crypto_map = {
            "bitcoin": "bitcoin",
            "ethereum": "ethereum",
            "litecoin": "litecoin",
            "ripple": "ripple",
            "dogecoin": "dogecoin",
            "cardano": "cardano",
            "polkadot": "polkadot",
            "solana": "solana",
            "polygon": "matic-network",
            "chainlink": "chainlink",
            "avalanche": "avalanche-2",
            "uniswap": "uniswap",
            "cosmos": "cosmos",
            "binance coin": "binancecoin",
            "bnb": "binancecoin",
            "tether": "tether",
            "usdc": "usd-coin",
        }
        
        text_lower = text.lower()
        for name, coin_id in crypto_map.items():
            if name in text_lower:
                logger.info(f"[Fallback] Matched '{name}' -> '{coin_id}'")
                return coin_id
        
        logger.warning(f"Could not extract valid coin symbol from: {text}")
        return None

    def _filter_relevant_news(
        self,
        news: list[dict[str, Any]],
        pair: str | None,
        symbol: str | None,
    ) -> list[dict[str, Any]]:
        if not news:
            return []
        if symbol:
            ticker = symbol.upper()
            return [n for n in news if ticker in (n.get("symbols") or []) or ticker in (n.get("title") or "").upper()]
        if pair:
            base = pair.split("/")[0].upper()
            return [
                n
                for n in news
                if base in (n.get("title") or "").upper() or base in (n.get("source") or "").upper()
            ]
        return news

    def _extract_analysis_data(self, task: TaskResult) -> dict[str, Any]:
        # Prefer artifact data
        for artifact in task.artifacts:
            for part in artifact.parts:
                if part.kind == "data" and part.data:
                    # Only use dict data, skip list (conversation history)
                    if isinstance(part.data, dict):
                        return part.data
        # Fallback to status message data part
        if task.status.message:
            for part in task.status.message.parts:
                if part.kind == "data" and part.data:
                    if isinstance(part.data, dict):
                        return part.data
        return {}

    def _is_market_summary_request(self, text: str) -> bool:
        """Detect if the request is asking for a market summary/overview."""
        text_lower = text.lower()
        
        # Keywords that indicate market summary requests
        summary_keywords = [
            "summarize",
            "summary",
            "overview",
            "what's happening",
            "market update",
            "today's market",
            "movements today",
            "market movements",
            "how are markets",
            "market status",
            "market snapshot",
            "best performing",
            "worst performing",
            "top gainers",
            "top losers",
            "trending",
            "newly added",
            "new coins",
            "market overview",
        ]
        
        # Check if any keyword is present and no specific symbol is being requested
        has_summary_keyword = any(keyword in text_lower for keyword in summary_keywords)
        
        # If it has summary keywords, it's likely a market summary request
        return has_summary_keyword

    async def _handle_market_summary(
        self,
        messages: list[A2AMessage],
        context_id: str,
        task_id: str,
    ) -> TaskResult:
        """Handle market summary requests with comprehensive market data."""
        
        # Fetch comprehensive market data
        summary = await get_comprehensive_market_summary()
        
        # Format as human-readable text
        summary_text = format_market_summary_text(summary)
        
        # Create agent response message
        agent_msg = A2AMessage(
            role="agent",
            parts=[
                MessagePart(kind="text", text=summary_text),
                MessagePart(kind="data", data=summary),
            ],
        )
        
        # Build artifacts
        artifacts = [
            Artifact(
                name="market_summary",
                parts=[MessagePart(kind="data", data=summary)]
            ),
            Artifact(
                name="top_performers",
                parts=[MessagePart(kind="data", data=summary.get("crypto", {}).get("best_performers_24h", []))]
            ),
            Artifact(
                name="worst_performers",
                parts=[MessagePart(kind="data", data=summary.get("crypto", {}).get("worst_performers_24h", []))]
            ),
            Artifact(
                name="trending_coins",
                parts=[MessagePart(kind="data", data=summary.get("crypto", {}).get("trending", []))]
            ),
        ]
        
        task_status = TaskStatus(status="completed", message=agent_msg)
        
        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=messages + [agent_msg],
        )

    @staticmethod
    def _format_analysis_message(
        key: str,
        direction: str,
        confidence: float,
        reasons: list | str,
        price_snapshot: dict[str, Any],
        technical_data: dict[str, Any],
        news: list[dict[str, Any]] | None = None,
        pair: str | None = None,
        symbol: str | None = None,
        error_messages: list[str] | None = None,
    ) -> str:
        """Format analysis results as a user-friendly Markdown message with error handling."""
        
        # Build message sections
        sections = []
        
        # Header
        sections.append(f"**{key} Market Analysis**\n")
        
        # Display errors prominently if present
        if error_messages:
            sections.append("⚠️ **Notices:**")
            for error in error_messages:
                sections.append(f"- {error}")
            sections.append("")  # Add blank line
        
        # Outlook
        sections.append(f"**Outlook:** {direction.capitalize()} (Confidence: {confidence:.0%})")
        
        # Price information
        if symbol and price_snapshot.get("crypto"):
            crypto_price = price_snapshot["crypto"].get(symbol)
            if crypto_price:
                price_str = f"${crypto_price:,.8f}".rstrip('0').rstrip('.')
                sections.append(f"**Current Price:** {price_str}")
            elif error_messages:
                sections.append(f"**Current Price:** Unavailable")
        elif pair and price_snapshot.get("pair"):
            rate = price_snapshot["pair"].get("rate")
            if rate:
                sections.append(f"**Exchange Rate:** {rate:.4f}")
            elif error_messages:
                sections.append(f"**Exchange Rate:** Unavailable")
        
        # Technical indicators
        if technical_data:
            change_pct = technical_data.get("change_pct", 0)
            trend = technical_data.get("trend", "unknown")
            sections.append(f"**7-Day Change:** {change_pct:+.2f}%")
            sections.append(f"**Trend:** {trend.capitalize()}")
        
        # Key factors/reasoning
        reasons_list = reasons if isinstance(reasons, list) else [str(reasons)]
        if reasons_list and reasons_list[0]:
            sections.append("\n**Key Factors:**")
            for reason in reasons_list[:3]:
                sections.append(f"- {reason}")
        
        # Recent news headlines
        if news:
            sections.append("\n**Recent News:**")
            for item in news[:3]:
                title = item.get("title", "")
                source = item.get("source", "")
                if title:
                    sections.append(f"- {title} ({source})")
        
        # Add helpful tip if there were errors
        if error_messages:
            sections.append("\n💡 **Tip:** Try common coin symbols (BTC, ETH, SOL) or forex pairs (EUR/USD, GBP/USD).")
        
        return "\n".join(sections)

