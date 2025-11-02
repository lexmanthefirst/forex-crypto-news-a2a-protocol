from __future__ import annotations

import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from typing import Any, Awaitable, cast

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

from agents.market_agent import MarketAgent
from models.a2a import (
    A2AMessage,
    ExecuteParams,
    JSONRPCRequest,
    JSONRPCResponse,
    MessageParams,
    MessagePart,
    TaskResult,
)
from utils.errors import A2AErrorCode, create_error_response
from utils.redis_client import redis_store

app = FastAPI(title="Market Intelligence A2A", version="1.0.0", docs_url="/docs")

scheduler = AsyncIOScheduler()
market_agent: MarketAgent | None = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    global market_agent

    await redis_store.initialize()
    market_agent = MarketAgent(notifier_webhook=os.getenv("NOTIFIER_WEBHOOK"))

    poll_minutes = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
    scheduler.add_job(_scheduled_analysis_job, "interval", minutes=poll_minutes)
    scheduler.start()
    yield
    shutdown_result = scheduler.shutdown()
    if asyncio.iscoroutine(shutdown_result):
        await cast(Awaitable[Any], shutdown_result)
    await redis_store.close()
    market_agent = None

app.router.lifespan_context = lifespan

async def _scheduled_analysis_job() -> None:
    if market_agent is None:
        return

    watchlist = [symbol.strip() for symbol in os.getenv("WATCHLIST", "BTC,ETH,EUR/USD").split(",") if symbol.strip()]
    tasks = []
    for item in watchlist:
        message = A2AMessage(role="system", parts=[MessagePart(kind="text", text=f"Analyze {item}")])
        tasks.append(
            asyncio.create_task(
                market_agent.process_messages(
                    [message],
                    context_id=f"scheduled-{item}",
                    task_id=f"task-scheduled-{item}",
                )
            )
        )

    if not tasks:
        return

    for task in asyncio.as_completed(tasks):
        try:
            await task
        except Exception:  # pragma: no cover - logging fallback
            traceback.print_exc()

@app.post("/a2a/market")
async def a2a_endpoint(request: Request):
    # Log request details for debugging
    content_type = request.headers.get("content-type", "")
    print(f"DEBUG: Content-Type={content_type}")
    
    raw_body = await request.body()
    print(f"DEBUG: Body length={len(raw_body)}, first 200 chars={raw_body[:200]}")
    
    try:
        body = await request.json()
        print(f"DEBUG: Parsed JSON successfully: {body}")
    except Exception as exc:
        print(f"DEBUG: JSON parse failed: {exc}")
        error_response = create_error_response(
            request_id=None,
            code=A2AErrorCode.PARSE_ERROR,
            message="Parse error",
            data={"details": str(exc)}
        )
        return JSONResponse(status_code=400, content=error_response)

    try:
        rpc = JSONRPCRequest(**body)
        print(f"DEBUG: Valid JSON-RPC request, method={rpc.method}")
    except Exception as exc:
        print(f"DEBUG: Pydantic validation failed: {exc}")
        request_id = body.get("id") if isinstance(body, dict) else None
        error_response = create_error_response(
            request_id=request_id,
            code=A2AErrorCode.INVALID_REQUEST,
            message="Invalid Request",
            data={"details": str(exc)}
        )
        return JSONResponse(status_code=400, content=error_response)

    try:
        params = rpc.params
        if isinstance(params, MessageParams):
            messages = [params.message]
            config = params.configuration
            result = await _process_with_agent(messages, config=config)
        elif isinstance(params, ExecuteParams):
            result = await _process_with_agent(
                params.messages,
                context_id=params.contextId,
                task_id=params.taskId,
            )
        else:  # pragma: no cover - defensive
            raise ValueError("Unsupported params payload")

        resp = JSONRPCResponse(jsonrpc="2.0", id=rpc.id, result=result)
        return JSONResponse(content=resp.model_dump())
    except Exception as exc:
        tb = traceback.format_exc()
        error_response = create_error_response(
            request_id=rpc.id,
            code=A2AErrorCode.INTERNAL_ERROR,
            message="Internal error",
            data={"details": str(exc), "trace": tb}
        )
        return JSONResponse(status_code=500, content=error_response)

@app.get("/health")
async def health_check():
    ok: dict[str, Any] = {"status": "healthy", "dependencies": {}}
    try:
        redis = redis_store.client
        await redis.ping()  # type: ignore[func-returns-value]
        ok["dependencies"]["redis"] = "ok"
    except Exception as exc:
        ok["dependencies"]["redis"] = f"error: {exc}"
    return ok

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)


async def _process_with_agent(
    messages: list[A2AMessage],
    *,
    context_id: str | None = None,
    task_id: str | None = None,
    config: Any | None = None,
) -> TaskResult:
    if market_agent is None:
        raise RuntimeError("MarketAgent is not initialized")

    processed_config = config.dict() if (config is not None and hasattr(config, "dict")) else config

    return await market_agent.process_messages(
        messages=messages,
        context_id=context_id,
        task_id=task_id,
        config=processed_config,
    )
