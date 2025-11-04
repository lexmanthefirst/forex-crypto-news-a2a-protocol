from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

from models.a2a import A2AMessage, Artifact, MessagePart, TaskResult, TaskStatus
from utils.gemini_client import analyze_sync
from utils.market_summary import get_comprehensive_market_summary, format_market_summary_text
from utils.news_fetcher import fetch_combined_news, fetch_crypto_prices, fetch_forex_rate
from utils.notifier import send_console_notification, send_webhook_notification
from utils.redis_client import redis_store
from utils.technical_analysis import get_technical_summary

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

    async def process_messages(
        self,
        messages: list[A2AMessage],
        context_id: str | None = None,
        task_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> TaskResult:
        """Main handler invoked by JSON-RPC endpoint. Accepts one or more messages."""
        _ = config  # reserved for future options

        now = datetime.now(timezone.utc)
        context_id = context_id or f"context-{int(now.timestamp())}"
        task_id = task_id or f"task-{int(now.timestamp())}"
        if not messages:
            raise ValueError("No messages provided")

        user_msg = messages[-1]
        # Extract only text parts, ignoring conversation history in data parts
        text_parts = [
            part.text for part in user_msg.parts 
            if part.kind == "text" and part.text and part.text.strip()
        ]
        text = " ".join(text_parts)
        
        # Strip HTML tags from text (for platforms like Telex.im)
        text = self._strip_html(text)
        
        # If empty after stripping, return early
        if not text.strip():
            raise ValueError("No analyzable text found in message")

        # Check if this is a market summary/overview request
        if self._is_market_summary_request(text):
            return await self._handle_market_summary(messages, context_id, task_id)

        pair = self._extract_pair(text)
        symbol = self._extract_symbol(text)

        price_snapshot: dict[str, Any] = {}
        technical_data: dict[str, Any] = {}
        
        if pair:
            try:
                forex = await fetch_forex_rate(pair)
                price_snapshot["pair"] = forex
            except Exception:
                price_snapshot["pair"] = {"pair": pair, "rate": None}
        if symbol:
            try:
                prices = await fetch_crypto_prices([symbol])
                price_snapshot["crypto"] = prices
                # Fetch technical indicators
                technical_data = await get_technical_summary(symbol)
            except Exception:
                price_snapshot["crypto"] = {symbol: None}

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
        reasons_str = ", ".join(reasons[:3]) if isinstance(reasons, list) else str(reasons)
        direction = analysis.get("direction", "neutral")
        agent_text = (
            f"Analysis for {key}: direction={direction} "
            f"confidence={confidence:.2f}. Top reasons: {reasons_str}"
        )
        agent_msg = A2AMessage(role="agent", parts=[MessagePart(kind="text", text=agent_text)], taskId=task_id)

        artifacts: list[Artifact] = [
            Artifact(name="analysis", parts=[MessagePart(kind="data", data=analysis)]),
        ]
        if price_snapshot:
            artifacts.append(Artifact(name="price_snapshot", parts=[MessagePart(kind="data", data=price_snapshot)]))
        if technical_data:
            artifacts.append(Artifact(name="technical_indicators", parts=[MessagePart(kind="data", data=technical_data)]))

        status_state = "completed"
        if (pair and price_snapshot.get("pair", {}).get("rate") is None) and (not symbol):
            status_state = "failed"

        task_status = TaskStatus(state=status_state, message=agent_msg)

        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=messages + [agent_msg],
        )

    def _extract_pair(self, text: str) -> str | None:
        m = PAIR_RE.search(text)
        if m:
            a, b = m.groups()
            return f"{a.upper()}/{b.upper()}"
        # allow "BTCUSD" or "EURUSD"
        m2 = re.search(r"\b([A-Za-z]{6})\b", text)
        if m2:
            s = m2.group(1)
            return f"{s[:3].upper()}/{s[3:].upper()}"
        return None

    def _extract_symbol(self, text: str) -> str | None:
        """Extract cryptocurrency symbol from text.
        Looks for common crypto symbols and keywords like 'Bitcoin', 'Ethereum', etc.
        """
        # First try direct regex match for crypto symbols
        m = SYMBOL_RE.search(text.upper())
        if m:
            symbol = m.group(1).upper()
            # Filter out common English words that might match
            excluded_words = {"TO", "THE", "AND", "OR", "FOR", "IN", "ON", "AT", "BY", "IS", "ARE", "WAS", "IT"}
            if symbol not in excluded_words:
                return symbol
        
        # Try to match common cryptocurrency names
        crypto_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "litecoin": "LTC",
            "ripple": "XRP",
            "dogecoin": "DOGE",
            "cardano": "ADA",
            "polkadot": "DOT",
            "solana": "SOL",
            "polygon": "MATIC",
            "chainlink": "LINK",
            "avalanche": "AVAX",
            "uniswap": "UNI",
            "cosmos": "ATOM",
            "binance coin": "BNB",
            "bnb": "BNB",
            "tether": "USDT",
            "usdc": "USDC",
        }
        
        text_lower = text.lower()
        for name, symbol in crypto_map.items():
            if name in text_lower:
                return symbol
        
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
        print("DEBUG: Handling market summary request")
        
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
        
        task_status = TaskStatus(state="completed", message=agent_msg)
        
        return TaskResult(
            id=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=messages + [agent_msg],
        )
