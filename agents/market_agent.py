from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from uuid import uuid4

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
from utils.assets import get_coin_id, CRYPTO_LOWER_MAP, get_coin_metadata

logger = logging.getLogger(__name__)

PAIR_RE = re.compile(r"([A-Za-z]{3,5})\s*[/\-]\s*([A-Za-z]{3,5})")
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
        
        # Context storage (in-memory for fast lookup, like MoodMatch)
        self.contexts: dict[str, list[A2AMessage]] = {}

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and decode entities."""
        text = re.sub(r'<[^>]+>', '', text)
        text = unescape(text)
        text = ' '.join(text.split())
        return text

    @staticmethod
    def _extract_text_from_message(message: A2AMessage) -> str:
        """Extract text from A2A message with multiple fallback strategies."""
        text_parts: list[str] = []
        
        for part in message.parts:
            if part.kind == "text" and part.text and part.text.strip():
                text_parts.append(part.text.strip())
        
        if not text_parts:
            for part in message.parts:
                if part.kind == "data" and part.data:
                    if isinstance(part.data, dict):
                        if "text" in part.data and part.data["text"]:
                            text_parts.append(str(part.data["text"]).strip())
                        elif "message" in part.data and isinstance(part.data["message"], str):
                            text_parts.append(part.data["message"].strip())
                        elif "content" in part.data and isinstance(part.data["content"], str):
                            text_parts.append(part.data["content"].strip())
                        elif "items" in part.data and isinstance(part.data["items"], list):
                            for item in part.data["items"]:
                                if isinstance(item, str) and item.strip():
                                    text_parts.append(item.strip())
                                elif isinstance(item, dict) and "text" in item:
                                    text_parts.append(str(item["text"]).strip())
                    elif isinstance(part.data, list):
                        for item in part.data:
                            if isinstance(item, str) and item.strip():
                                text_parts.append(item.strip())
                            elif isinstance(item, dict) and "text" in item:
                                text_parts.append(str(item["text"]).strip())
        
        combined_text = " ".join(text_parts)
        
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
        
        text: str | None = None
        conversation_history: list[str] = []
        extraction_debug: dict[str, Any] = {}
        
        if config and isinstance(config, dict):
            text, conversation_history, extraction_debug = extract_text_from_telex_message(config)
            if text:
                logger.info(f"Telex extraction: {extraction_debug.get('source')}, history: {len(conversation_history)} msgs")
        
        if not text:
            text = self._extract_text_from_message(user_msg)
            extraction_debug = {"source": "fallback_message_extraction"}
        
        if not text or not text.strip():
            raise ValueError("No analyzable text found in message. Please provide a query with cryptocurrency symbol, name, or forex pair (e.g., 'BTC price', 'Bitcoin analysis', 'EUR/USD rate').")

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
        
        try:
            await session_store.append_message(context_id, user_msg)
        except Exception as e:
            logger.warning(f"Failed to store user message: {e}")

        if self._is_market_summary_request(text):
            return await self._handle_market_summary(messages, context_id, task_id)

        pair = self._extract_pair(text)
        symbol = self._extract_symbol(text)  # coingecko id, e.g. 'bitcoin'

        # Derive a display ticker (e.g., 'BTC') from local metadata for nicer output
        display_ticker: str | None = None
        if symbol:
            try:
                meta_list = get_coin_metadata()
                id_to_symbol = {m["id"]: m["symbol"].upper() for m in meta_list}
                display_ticker = id_to_symbol.get(symbol, symbol.upper())
            except Exception:
                display_ticker = symbol.upper()

        # Parallel fetch all data to reduce latency
        fetch_tasks = []
        
        if pair:
            fetch_tasks.append(("forex", fetch_forex_rate(pair)))
        
        if symbol:
            # Fetch prices by ticker for human-friendly keys (BTC -> price)
            ticker_to_fetch = display_ticker or symbol.upper()
            fetch_tasks.append(("crypto_price", fetch_crypto_prices([ticker_to_fetch])))
            fetch_tasks.append(("technical", get_technical_summary(symbol)))
        
        # Always fetch news in parallel
        fetch_tasks.append(("news", fetch_combined_news(limit=5)))  # Reduced from 10 to 5
        
        # Execute all fetches in parallel
        results = {}
        if fetch_tasks:
            task_results = await asyncio.gather(
                *[task for _, task in fetch_tasks],
                return_exceptions=True
            )
            for i, (name, _) in enumerate(fetch_tasks):
                results[name] = task_results[i]
        
        # Process results
        price_snapshot: dict[str, Any] = {}
        technical_data: dict[str, Any] = {}
        error_messages: list[str] = []
        
        if pair and "forex" in results:
            result = results["forex"]
            if isinstance(result, Exception):
                price_snapshot["pair"] = {"pair": pair, "rate": None}
                error_messages.append(f"Unable to fetch forex rate for {pair}.")
            else:
                price_snapshot["pair"] = result
                
        if symbol:
            if "crypto_price" in results:
                result = results["crypto_price"]
                if isinstance(result, Exception):
                    ticker_to_fetch = display_ticker or symbol.upper()
                    price_snapshot["crypto"] = {ticker_to_fetch: None}
                    error_messages.append(f"Unable to fetch price data for {ticker_to_fetch}.")
                else:
                    price_snapshot["crypto"] = result
                    
            if "technical" in results:
                result = results["technical"]
                if not isinstance(result, Exception):
                    technical_data = result

        combined_news = results.get("news", [])
        if isinstance(combined_news, Exception):
            combined_news = []

        ticker_for_news = (display_ticker or symbol.upper()) if symbol else None
        relevant = self._filter_relevant_news(combined_news, pair, ticker_for_news)
        news_summary = (
            "\n".join(f"• {item.get('title')} ({item.get('source')})" for item in relevant[:5])
            or "No recent headlines found."
        )
        
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
        
        # Add timeout to prevent hanging on slow LLM responses
        try:
            analysis_result = await asyncio.wait_for(
                loop.run_in_executor(None, analyze_sync, subject, price_snapshot, news_summary),
                timeout=25.0  # 25 second max for LLM analysis
            )
            analysis_data = self._extract_analysis_data(analysis_result)
            raw_analysis = analysis_data.get("analysis", {})
            analysis = dict(raw_analysis) if isinstance(raw_analysis, dict) else {}
            analysis_ts = analysis_data.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            analysis["ts"] = analysis_ts
        except asyncio.TimeoutError:
            logger.warning(f"Gemini analysis timed out for {subject}")
            # Fallback to basic analysis without LLM
            analysis = {
                "direction": "neutral",
                "confidence": 0.5,
                "impact_score": 0.0,
                "reasoning": ["Analysis timed out - using fallback"],
                "timeframe": "short-term",
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }

        key = (pair or symbol or "market").upper()
        try:
            await redis_store.set_latest_analysis(
                key,
                {"analysis": analysis, "news": relevant, "price_snapshot": price_snapshot},
                ex=3600,
            )
        except Exception as e:
            logger.warning(f"Failed to store analysis in Redis: {e}")

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
        
        agent_text = self._format_analysis_message(
            key=key,
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            price_snapshot=price_snapshot,
            technical_data=technical_data,
            news=relevant[:3],
            pair=pair,
            symbol=display_ticker,
            error_messages=error_messages
        )
        
        # Step 1: Build response message (for conversation history display)
        response_message = A2AMessage(
            role="agent",
            parts=[MessagePart(kind="text", text=agent_text)],
            messageId=str(uuid4()),
            taskId=None,  # Set to None in history like working agent
            metadata=None  # Set to None in history like working agent
        )

        # Step 2: Create artifacts (match working agent format)
        # Working agents use ONE artifact with kind="text" containing the response
        artifacts: list[Artifact] = [
            Artifact(
                name="assistantResponse",
                parts=[MessagePart(kind="text", text=agent_text)]
            )
        ]

        # Step 3: Build conversation history (includes response_message)
        history = self._build_history(messages, response_message)
        
        # Step 4: Store context (like MoodMatch)
        self.contexts[context_id] = history
        
        # Also persist to Redis for durability
        try:
            await session_store.append_message(context_id, response_message)
        except Exception as e:
            logger.warning(f"Failed to store agent message: {e}")

        # Step 5: Create status message (A2A protocol compliance)
        status_state = "completed"
        if (pair and price_snapshot.get("pair", {}).get("rate") is None) and (not symbol):
            status_state = "failed"
        
        status_message = A2AMessage(
            role="agent",
            parts=[MessagePart(
                kind="text",
                text="Analysis completed successfully" if status_state == "completed" else "Analysis failed"
            )],
            messageId=str(uuid4()),
            taskId=None,  # Set to None like working agent
            metadata=None  # Set to None like working agent
        )

        task_status = TaskStatus(state=status_state, message=status_message)

        # Step 6: Create successful task result
        result = TaskResult(
            taskId=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=history,
        )
        # Set user's messageId for result.id field (Telex compatibility)
        result._user_message_id = user_msg.messageId
        return result

    def _extract_pair(self, text: str) -> str | None:
        """Extract forex pair from text.
        
        Matches explicit pairs like EUR/USD, EUR-USD first.
        For 6-letter patterns like EURUSD, only accept if it looks like a valid forex pair
        (both halves are common currency codes, not random words like LATEST).
        """
        text_lower = text.lower()
        natural_language_pairs = {
            "euro dollar": "EUR/USD",
            "euro usd": "EUR/USD",
            "pound dollar": "GBP/USD",
            "pound usd": "GBP/USD",
            "dollar yen": "USD/JPY",
            "usd yen": "USD/JPY",
            "aussie dollar": "AUD/USD",
            "aud usd": "AUD/USD",
            "euro pound": "EUR/GBP",
            "euro yen": "EUR/JPY",
            "dollar cad": "USD/CAD",
            "dollar canadian": "USD/CAD",
        }
        
        for phrase, pair in natural_language_pairs.items():
            if phrase in text_lower:
                logger.info(f"[Natural language] Matched '{phrase}' -> '{pair}'")
                return pair
        
        m = PAIR_RE.search(text)
        if m:
            a, b = m.groups()
            return f"{a.upper()}/{b.upper()}"
        
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
            if first_half in valid_currencies and second_half in valid_currencies:
                return f"{first_half}/{second_half}"
        
        return None

    def _extract_symbol(self, text: str) -> str | None:
        """Extract cryptocurrency symbol using hierarchical matching strategies.

        Priority order:
        1. Check centralized alias map (fast, deterministic)
        2. Match common full coin names in the text
        3. Use a curated fallback dictionary of popular assets
        4. Ask the LLM extractor as a last resort

        Returns the CoinGecko ID (e.g., "bitcoin") for compatibility with price APIs.
        """
        text_upper = text.upper()
        text_lower = text.lower()
        
        # Skip common English words to avoid false matches
        skip_words = {
            "analyze", "check", "what", "about", "tell", "me", "price", "of", "the",
            "is", "are", "was", "were", "have", "has", "had", "do", "does", "did",
            "will", "would", "should", "could", "can", "may", "might", "must",
            "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "from",
            "with", "by", "as", "this", "that", "these", "those", "it", "its",
            "show", "get", "give", "take", "make", "go", "come", "see", "know",
            "think", "say", "tell", "ask", "use", "find", "want", "need", "try"
        }
        
        # Priority 1: Direct match using centralized alias table (very fast)
        words = text_upper.replace(",", " ").replace(".", " ").split()
        for word in words:
            if word in skip_words or len(word) < 2:
                continue

            # Use assets.get_coin_id to resolve common aliases/symbols/names
            coin_id = get_coin_id(word)
            if coin_id:
                logger.info(f"[Direct Match] '{word}' -> '{coin_id}'")
                return coin_id
        
        # Priority 2: Check for full coin names in text (FAST)
        for key, coin_id in CRYPTO_LOWER_MAP.items():
            if len(key) > 3 and key in text_lower:  # Full names like "bitcoin", "ethereum"
                logger.info(f"[Name Match] Found '{key}' -> '{coin_id}'")
                return coin_id
        
        # Priority 3: Fallback hardcoded common names (FAST)
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
        
        for name, coin_id in crypto_map.items():
            if name in text_lower:
                logger.info(f"[Fallback] Matched '{name}' -> '{coin_id}'")
                return coin_id
        
        # Priority 4: ONLY use LLM if nothing matched (SLOW, last resort)
        # This is expensive and should rarely be needed with the expanded map
        logger.debug(f"No quick match found, trying LLM extraction (slow)...")
        coin_query = extract_coin_with_llm(text)
        if coin_query:
            # Filter out garbage responses
            if "TICKER" in coin_query.upper() or len(coin_query) > 20 or "-" in coin_query:
                logger.warning(f"[LLM] Invalid extraction '{coin_query}', skipping")
            else:
                # Prefer the fast local alias resolver for the LLM result
                coin_id = get_coin_id(coin_query)
                if coin_id:
                    logger.info(f"[LLM+Map] '{coin_query}' -> '{coin_id}'")
                    return coin_id

                logger.info(f"[LLM] Extracted '{coin_query}' (no map match, using lowercase)")
                return coin_query.lower()
        
        logger.warning(f"Could not extract valid coin symbol from: {text}")
        return None

    def _filter_relevant_news(
        self,
        news: list[dict[str, Any]],
        pair: str | None,
        ticker: str | None,
    ) -> list[dict[str, Any]]:
        if not news:
            return []
        if ticker:
            upper_ticker = ticker.upper()
            return [
                n
                for n in news
                if upper_ticker in (n.get("symbols") or []) or upper_ticker in (n.get("title") or "").upper()
            ]
        if pair:
            base = pair.split("/")[0].upper()
            return [
                n
                for n in news
                if base in (n.get("title") or "").upper() or base in (n.get("source") or "").upper()
            ]
        return news

    def _build_history(
        self,
        incoming_messages: list[A2AMessage],
        agent_message: A2AMessage
    ) -> list[A2AMessage]:
        """Build conversation history.
        """
        history = []
        
        # Add ONLY cleaned user message (text only, no complex data parts)
        if incoming_messages:
            last_user_msg = incoming_messages[-1]
            # Extract just the text from the user message
            user_text = self._extract_text_from_message(last_user_msg)
            
            # Create simplified user message for history
            clean_user_msg = A2AMessage(
                role="user",
                parts=[MessagePart(kind="text", text=user_text)],
                messageId=str(uuid4()),
                taskId=None,
                metadata=None
            )
            history.append(clean_user_msg)
        
        return history

    def _extract_analysis_data(self, task: TaskResult) -> dict[str, Any]:
        for artifact in task.artifacts:
            for part in artifact.parts:
                if part.kind == "data" and part.data:
                    if isinstance(part.data, dict):
                        return part.data
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
        
        has_summary_keyword = any(keyword in text_lower for keyword in summary_keywords)
        
        return has_summary_keyword

    async def _handle_market_summary(
        self,
        messages: list[A2AMessage],
        context_id: str,
        task_id: str,
    ) -> TaskResult:
        """Handle market summary requests with comprehensive market data."""
        
        summary = await get_comprehensive_market_summary()
        
        summary_text = format_market_summary_text(summary)
        
        # Step 1: Build response message (for conversation history display)
        response_message = A2AMessage(
            role="agent",
            parts=[MessagePart(kind="text", text=summary_text)],
            messageId=str(uuid4()),
            taskId=None,  # Set to None in history like working agent
            metadata=None  # Set to None in history like working agent
        )
        
        # Step 2: Build artifacts (match working agent format)
        # Working agents use ONE artifact with kind="text" containing the response
        artifacts = [
            Artifact(
                name="assistantResponse",
                parts=[MessagePart(kind="text", text=summary_text)]
            )
        ]
        
        # Step 3: Build conversation history
        history = self._build_history(messages, response_message)
        
        # Step 4: Store context (like MoodMatch)
        self.contexts[context_id] = history
        
        # Step 5: Create status message (A2A protocol compliance)
        status_message = A2AMessage(
            role="agent",
            parts=[MessagePart(
                kind="text",
                text="Market summary generated successfully"
            )],
            messageId=str(uuid4()),
            taskId=None,  # Set to None like working agent
            metadata=None  # Set to None like working agent
        )
        
        task_status = TaskStatus(state="completed", message=status_message)
        
        # Step 6: Create successful task result
        result = TaskResult(
            taskId=task_id,
            contextId=context_id,
            status=task_status,
            artifacts=artifacts,
            history=history,
        )
        # Set user's messageId for result.id field (Telex compatibility)
        if messages:
            result._user_message_id = messages[-1].messageId
        return result

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
        """Format comprehensive analysis as user-friendly Markdown with all data sections."""
        
        sections = []
        
        # Header
        sections.append(f"**{key} Market Analysis**\n")
        
        # Display errors prominently if present
        if error_messages:
            sections.append("⚠️ **Notices:**")
            for error in error_messages:
                sections.append(f"- {error}")
            sections.append("")
        
        # === MARKET OUTLOOK ===
        sections.append("**📊 Market Outlook**")
        sections.append(f"- **Direction:** {direction.capitalize()}")
        sections.append(f"- **Confidence Level:** {confidence:.0%}")
        sections.append("")
        
        # === PRICE DATA ===
        sections.append("**💰 Price Information**")
        if symbol and price_snapshot.get("crypto"):
            crypto_price = price_snapshot["crypto"].get(symbol)
            if crypto_price:
                price_str = f"${crypto_price:,.8f}".rstrip('0').rstrip('.')
                sections.append(f"- **Current Price:** {price_str}")
            else:
                sections.append(f"- **Current Price:** Data unavailable")
        elif pair and price_snapshot.get("pair"):
            rate = price_snapshot["pair"].get("rate")
            if rate:
                sections.append(f"- **Exchange Rate:** {rate:.4f}")
            else:
                sections.append(f"- **Exchange Rate:** Data unavailable")
        else:
            sections.append("- Price data not available")
        sections.append("")
        
        # === TECHNICAL ANALYSIS ===
        if technical_data:
            sections.append("**📈 Technical Analysis (7-Day)**")
            change_pct = technical_data.get("change_pct", 0)
            trend = technical_data.get("trend", "unknown")
            signal = technical_data.get("signal", "neutral")
            price_position = technical_data.get("price_position", "N/A")
            
            sections.append(f"- **Trend:** {trend.capitalize()}")
            sections.append(f"- **Price Change:** {change_pct:+.2f}%")
            sections.append(f"- **Signal:** {signal.capitalize()}")
            sections.append(f"- **Position vs SMA:** {price_position.replace('_', ' ').title()}")
            
            # Add support/resistance if available
            if technical_data.get("support") and technical_data.get("resistance"):
                support = technical_data["support"]
                resistance = technical_data["resistance"]
                sections.append(f"- **Support Level:** ${support:,.2f}")
                sections.append(f"- **Resistance Level:** ${resistance:,.2f}")
            
            sections.append("")
        
        # === AI ANALYSIS ===
        reasons_list = reasons if isinstance(reasons, list) else [str(reasons)]
        if reasons_list and reasons_list[0] and reasons_list[0] != "rule-based fallback":
            sections.append("**🤖 AI Insights**")
            for reason in reasons_list[:5]:  # Show up to 5 key factors
                sections.append(f"- {reason}")
            sections.append("")
        
        # === NEWS HEADLINES ===
        sections.append("**📰 Recent News**")
        if news and len(news) > 0:
            for item in news[:3]:  # Top 3 headlines
                title = item.get("title", "")
                source = item.get("source", "Unknown")
                if title:
                    sections.append(f"- {title} ({source})")
        else:
            sections.append("- News are not currently available for this asset")
        sections.append("")
        
        # === FOOTER ===
        if error_messages:
            sections.append("💡 **Tip:** Try common symbols like BTC, ETH, SOL or forex pairs like EUR/USD, GBP/USD")
        else:
            sections.append("---")
            sections.append("*This analysis is for informational purposes only and does not constitute financial advice.*")
        
        return "\n".join(sections)

