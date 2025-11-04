"""
A2A Market Intelligence Agent - Main Application

This FastAPI application provides a JSON-RPC 2.0 endpoint for market analysis
of cryptocurrencies and forex pairs using the Agent-to-Agent (A2A) protocol.

Architecture:
- Request parsing & validation layer
- Synchronous request handling (blocking mode)
- Background scheduled analysis jobs
- Market intelligence agent integration
- Redis session storage

Endpoints:
- POST /a2a/agent/market: Main A2A protocol endpoint
- GET /health: Health check with dependency status
"""
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
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from agents.market_agent import MarketAgent
from models.a2a import (
    A2AMessage,
    ExecuteParams,
    JSONRPCRequest,
    JSONRPCResponse,
    MessageConfiguration,
    MessageParams,
    MessagePart,
    TaskResult,
)
from utils.errors import A2AErrorCode, create_error_response
from utils.redis_client import redis_store

app = FastAPI(title="Market Intelligence A2A", version="1.0.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
scheduler = AsyncIOScheduler()
market_agent: MarketAgent | None = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    global market_agent

    await redis_store.initialize()
    market_agent = MarketAgent()

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


# ===========================
# Request Parsing & Validation
# ===========================

async def _parse_request_body(request: Request) -> dict[str, Any] | JSONResponse:
    """Parse and log incoming request body."""
    content_type = request.headers.get("content-type", "")
    print(f"DEBUG: Content-Type={content_type}")
    
    raw_body = await request.body()
    print(f"DEBUG: Body length={len(raw_body)}, first 200 chars={raw_body[:200]}")
    
    try:
        body = await request.json()
        print(f"DEBUG: Parsed JSON successfully")
        return body
    except Exception as exc:
        print(f"DEBUG: JSON parse failed: {exc}")
        error_response = create_error_response(
            request_id=None,
            code=A2AErrorCode.PARSE_ERROR,
            message="Parse error",
            data={"details": str(exc)}
        )
        return JSONResponse(status_code=400, content=error_response)


async def _validate_jsonrpc_request(body: dict[str, Any]) -> JSONRPCRequest | JSONResponse:
    """Validate JSON-RPC request structure."""
    try:
        rpc = JSONRPCRequest(**body)
        print(f"DEBUG: Valid JSON-RPC request, method={rpc.method}")
        return rpc
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


def _create_internal_error_response(request_id: str, exc: Exception) -> JSONResponse:
    """Create internal error response with traceback."""
    tb = traceback.format_exc()
    error_response = create_error_response(
        request_id=request_id,
        code=A2AErrorCode.INTERNAL_ERROR,
        message="Internal error",
        data={"details": str(exc), "trace": tb}
    )
    return JSONResponse(status_code=500, content=error_response)


# ===========================
# Request Handlers
# ===========================

async def _handle_message_send(request_id: str, params: MessageParams) -> JSONResponse:
    """Handle message/send JSON-RPC method."""
    messages = [params.message]
    config = params.configuration
    
    # ALWAYS use blocking mode (synchronous response) like the working examples
    # This avoids webhook issues with Telex.im
    return await _handle_blocking_request(request_id, messages, config)


async def _handle_execute(request_id: str, params: ExecuteParams) -> JSONResponse:
    """Handle execute JSON-RPC method."""
    result = await _process_with_agent(
        params.messages,
        context_id=params.contextId,
        task_id=params.taskId,
    )
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    # Explicitly include all fields, exclude None values except for result/error
    return JSONResponse(content=response.model_dump(mode='json', exclude_none=False))


async def _handle_blocking_request(
    request_id: str,
    messages: list[A2AMessage],
    config: MessageConfiguration
) -> JSONResponse:
    """Handle blocking request - return result directly."""
    result = await _process_with_agent(messages, config=config)
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    # Explicitly include all fields with proper JSON serialization
    return JSONResponse(content=response.model_dump(mode='json', exclude_none=False))


@app.post("/a2a/agent/market")
async def a2a_endpoint(request: Request):
    """Main A2A protocol endpoint for market analysis requests."""
    # Parse and validate request
    body = await _parse_request_body(request)
    if isinstance(body, JSONResponse):
        return body  # Error response
    
    rpc = await _validate_jsonrpc_request(body)
    if isinstance(rpc, JSONResponse):
        return rpc  # Error response
    
    # Process the request
    try:
        params = rpc.params
        
        if isinstance(params, MessageParams):
            return await _handle_message_send(rpc.id, params)
        elif isinstance(params, ExecuteParams):
            return await _handle_execute(rpc.id, params)
        else:
            raise ValueError("Unsupported params payload")
            
    except Exception as exc:
        return _create_internal_error_response(rpc.id, exc)

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


# ===========================
# Agent Processing
# ===========================

async def _process_with_agent(
    messages: list[A2AMessage],
    *,
    context_id: str | None = None,
    task_id: str | None = None,
    config: Any | None = None,
) -> TaskResult:
    """Process messages with the market agent."""
    if market_agent is None:
        raise RuntimeError("MarketAgent is not initialized")

    processed_config = config.dict() if (config is not None and hasattr(config, "dict")) else config

    return await market_agent.process_messages(
        messages=messages,
        context_id=context_id,
        task_id=task_id,
        config=processed_config,
    )


