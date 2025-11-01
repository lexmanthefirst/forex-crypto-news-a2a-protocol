from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any

from models.a2a import A2AMessage, Artifact, MessagePart, TaskResult, TaskStatus
from utils.gemini_client import analyze_sync
from utils.news_fetcher import fetch_combined_news, fetch_crypto_prices, fetch_forex_rate
from utils.notifier import send_console_notification, send_webhook_notification
from utils.redis_client import redis_store
from utils.technical_analysis import get_technical_summary

# small regex to extract currency pair or coin symbol
PAIR_RE = re.compile(r"([A-Za-z]{3,5})\s*[/\-]\s*([A-Za-z]{3,5})")
SYMBOL_RE = re.compile(r"\b(BTC|ETH|LTC|DOGE|XRP)\b", re.IGNORECASE)


class MarketAgent:
    def __init__(self, notifier_webhook: str | None = None, enable_notifications: bool | None = None):
        self.notifier_webhook = notifier_webhook or os.getenv("NOTIFIER_WEBHOOK")
        if enable_notifications is None:
            env_value = os.getenv("ENABLE_NOTIFICATIONS", "true").strip().lower()
            enable_notifications = env_value in {"1", "true", "yes", "on"}
        self.enable_notifications = enable_notifications
        self.notification_cooldown = int(os.getenv("NOTIFICATION_COOLDOWN_SECONDS", "900"))
        self.last_notified: dict[str, float] = {}

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
        text_parts = [part.text for part in user_msg.parts if part.kind == "text" and part.text]
        text = " ".join(text_parts)

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
                    asyncio.create_task(send_webhook_notification(self.notifier_webhook, payload))
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

        status_state = "input-required"
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
        m = SYMBOL_RE.search(text)
        return m.group(1).upper() if m else None

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
                    return part.data
        # Fallback to status message data part
        if task.status.message:
            for part in task.status.message.parts:
                if part.kind == "data" and part.data:
                    return part.data
        return {}
