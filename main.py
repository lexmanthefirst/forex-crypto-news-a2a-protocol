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
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, cast

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)

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
    TaskStatus,
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

# Create routers for organized endpoint management
a2a_router = APIRouter(prefix="/a2a/agent", tags=["A2A Protocol"])
system_router = APIRouter(tags=["System"])

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



# Request Parsing & Validation
async def _parse_request_body(request: Request) -> dict[str, Any] | JSONResponse:
    """Parse incoming request body."""
    try:
        body = await request.json()
        return body
    except Exception as exc:
        error_response = create_error_response(
            request_id=None,
            code=A2AErrorCode.PARSE_ERROR,
            message="Parse error",
            data={"details": str(exc)}
        )
        return JSONResponse(status_code=400, content=error_response)


async def _validate_jsonrpc_request(body: dict[str, Any], lenient: bool = False) -> JSONRPCRequest | JSONResponse:
    """
    Validate JSON-RPC request structure.
    
    Args:
        body: Request body
        lenient: If True, returns error as JSON-RPC response (HTTP 200) instead of HTTP 400
    """
    try:
        rpc = JSONRPCRequest(**body)
        return rpc
    except Exception as exc:
        request_id = body.get("id") if isinstance(body, dict) else None
        
        if lenient:
            # Return error as successful JSON-RPC response (HTTP 200)
            error_payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": A2AErrorCode.INVALID_REQUEST,
                    "message": "Invalid Request",
                    "data": {"details": str(exc)}
                }
            }
            return JSONResponse(status_code=200, content=error_payload)
        else:
            # Return HTTP error
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



# Request Handlers
async def _process_and_push_webhook(
    messages: list[A2AMessage],
    task_id: str,
    context_id: str,
    request_id: str,
    config: MessageConfiguration | None,
    push_url: str,
    push_token: str,
) -> None:
    """Process messages in background and push result to Telex webhook.
    
    This implements the non-blocking A2A pattern from the PRRover example.
    """
    try:
        # Process with agent
        result = await _process_with_agent(
            messages,
            context_id=context_id,
            task_id=task_id,
            config=config.model_dump(mode='json') if config else None,
        )
        
        # Build webhook payload - must match format of initial 202 response
        # Use JSONRPCResponse model for consistency with other endpoints
        response_obj = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
        webhook_payload = response_obj.model_dump(mode='json', exclude_none=False)
        
        # Log webhook attempt
        logger.info("[webhook] Sending to %s (task_id=%s, state=%s)", 
                   push_url, task_id, result.status.state)
        logger.debug("[webhook] Payload preview: jsonrpc=%s id=%s result.status.state=%s", 
                    webhook_payload.get("jsonrpc"), 
                    webhook_payload.get("id"),
                    webhook_payload.get("result", {}).get("status", {}).get("state"))
        
        # Push to Telex webhook
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {push_token}"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                push_url,
                json=webhook_payload,
                headers=headers
            )
            response.raise_for_status()
            logger.info("[webhook] ✓ Delivered successfully: status=%s task_id=%s", 
                       response.status_code, task_id)
            
    except httpx.HTTPStatusError as e:
        logger.error("[webhook] ✗ HTTP error %s: %s (task_id=%s)", 
                    e.response.status_code, e.response.text, task_id)
    except Exception as e:
        logger.error("[webhook] ✗ Failed: %s (task_id=%s)", e, task_id, exc_info=True)


async def _handle_message_send(request_id: str, params: MessageParams) -> JSONResponse:
    """Handle message/send JSON-RPC method.
    
    Supports both blocking and non-blocking modes:
    - Blocking: Process and return completed result immediately
    - Non-blocking: Return 'accepted' status, process in background, push to webhook
    """
    messages = [params.message]
    config = params.configuration
    
    # Log incoming message details
    user_message = messages[0] if messages else None
    if user_message and user_message.parts:
        text_preview = next((p.text[:50] for p in user_message.parts if p.text), "")
        logger.info("[message/send] Processing message: text=%r...", text_preview)
    
    # Check if non-blocking mode is requested
    is_blocking = True
    push_config = None
    
    if config:
        # Check blocking flag (default to True if not specified)
        is_blocking = config.blocking if hasattr(config, 'blocking') and config.blocking is not None else True
        push_config = config.pushNotificationConfig if hasattr(config, 'pushNotificationConfig') else None
    
    logger.info("[message/send] Mode: %s, webhook_configured: %s", 
               "blocking" if is_blocking else "non-blocking",
               bool(push_config and push_config.url))
    
    # Non-blocking mode: return accepted, process in background
    if not is_blocking and push_config and push_config.url and push_config.token:
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        
        logger.info("[message/send] Non-blocking: returning 'submitted' (task_id=%s)", task_id)
        
        # Return accepted status immediately
        accepted_result = TaskResult(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(
                state="submitted",
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=A2AMessage(
                    role="agent",
                    parts=[MessagePart(kind="text", text="🔄 Analyzing your request! Results coming shortly...")],
                ),
            ),
            artifacts=[],
            history=messages,
            kind="task"
        )
        
        # Start background processing
        asyncio.create_task(_process_and_push_webhook(
            messages=messages,
            task_id=task_id,
            context_id=context_id,
            request_id=request_id,
            config=config,
            push_url=push_config.url,
            push_token=push_config.token
        ))
        
        response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=accepted_result)
        logger.info("[message/send] Accepted response sent (task_id=%s)", task_id)
        return JSONResponse(content=response.model_dump(mode='json', exclude_none=False))
    
    # Blocking mode: process synchronously and return complete result
    logger.info("[message/send] Blocking: processing synchronously")
    result = await _process_with_agent(messages, config=config)
    logger.info("[message/send] Processing complete: state=%s", result.status.state)
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    return JSONResponse(content=response.model_dump(mode='json', exclude_none=False))


async def _handle_execute(request_id: str, params: ExecuteParams) -> JSONResponse:
    """Handle execute JSON-RPC method."""
    result = await _process_with_agent(
        params.messages,
        context_id=params.contextId,
        task_id=params.taskId,
    )
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    return JSONResponse(content=response.model_dump(mode='json', exclude_none=False))



# A2A Protocol Routes
@a2a_router.post("/market")
async def a2a_endpoint(request: Request):
    """Main A2A protocol endpoint for market analysis requests.
    
    Handles JSON-RPC 2.0 requests with methods:
    - message/send: Process user message and return analysis
    - execute: Execute analysis task
    """
    # Log incoming request
    try:
        body = await request.json()
        logger.info("[a2a] Incoming request: method=%s id=%s", 
                   body.get("method"), body.get("id"))
    except Exception as e:
        logger.error("[a2a] Failed to parse request body: %s", e)
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": A2AErrorCode.PARSE_ERROR,
                "message": "Parse error",
                "data": {"details": str(e)}
            }
        }
        return JSONResponse(status_code=200, content=error_response)
    
    # Parse and validate request
    body_result = await _parse_request_body(request)
    if isinstance(body_result, JSONResponse):
        logger.error("[a2a] Request parsing failed")
        return body_result
    
    # Use lenient validation (returns HTTP 200 even for errors)
    rpc = await _validate_jsonrpc_request(body_result, lenient=True)
    if isinstance(rpc, JSONResponse):
        logger.error("[a2a] JSON-RPC validation failed")
        return rpc
    
    # Process the request
    try:
        params = rpc.params
        response = None
        
        if isinstance(params, MessageParams):
            logger.info("[a2a] Processing message/send")
            response = await _handle_message_send(rpc.id, params)
        elif isinstance(params, ExecuteParams):
            logger.info("[a2a] Processing execute")
            response = await _handle_execute(rpc.id, params)
        else:
            raise ValueError(f"Unsupported params type: {type(params)}")
        
        # Log successful response
        if response:
            logger.info("[a2a] Response sent: id=%s status=success", rpc.id)
        
        return response
            
    except Exception as exc:
        # Log error with full traceback
        logger.error("[a2a] Unhandled error: %s", exc, exc_info=True)
        
        # Return error as JSON-RPC error response (HTTP 200)
        error_payload = {
            "jsonrpc": "2.0",
            "id": rpc.id,
            "error": {
                "code": A2AErrorCode.INTERNAL_ERROR,
                "message": "Internal error",
                "data": {"details": str(exc), "trace": traceback.format_exc()}
            }
        }
        logger.info("[a2a] Error response sent: id=%s", rpc.id)
        return JSONResponse(status_code=200, content=error_payload)


# System Routes
@system_router.get("/health")
async def health_check():
    """Health check endpoint."""
    ok: dict[str, Any] = {"status": "healthy", "dependencies": {}}
    try:
        redis = redis_store.client
        await redis.ping()  # type: ignore[func-returns-value]
        ok["dependencies"]["redis"] = "ok"
    except Exception as exc:
        ok["dependencies"]["redis"] = f"error: {exc}"
    return ok


@system_router.get("/agent.json")
@system_router.get("/.well-known/agent.json")
async def agent_manifest():
    """Agent manifest/discovery endpoint for A2A protocol.
    
    Returns agent metadata, capabilities, and endpoint information
    for agent discovery and integration.
    """
    return {
        "name": "Market Intelligence Agent",
        "version": "1.0.0",
        "publisher": "Market Intelligence Team",
        "description": "Real-time market analysis agent for cryptocurrencies and forex pairs. Provides price tracking, technical analysis, news aggregation, and AI-powered market insights.",
        "capabilities": [
            "Real-time cryptocurrency price tracking (CoinGecko)",
            "Forex pair analysis and exchange rates",
            "Technical indicators (RSI, MACD, Bollinger Bands)",
            "News aggregation from multiple sources",
            "AI-powered market analysis and insights",
            "Redis caching for performance (60s prices, 300s news)",
            "Supports both blocking and non-blocking modes"
        ],
        "endpoints": [
            {
                "method": "POST",
                "path": "/a2a/agent/market",
                "description": "Main A2A protocol endpoint for market analysis",
                "protocol": "JSON-RPC 2.0",
                "methods": [
                    "message/send",
                    "execute"
                ]
            },
            {
                "method": "GET",
                "path": "/health",
                "description": "Health check endpoint"
            },
            {
                "method": "GET",
                "path": "/agent.json",
                "description": "Agent manifest (this endpoint)"
            }
        ],
        "features": {
            "supported_assets": [
                "Cryptocurrencies (BTC, ETH, SOL, etc.)",
                "Forex pairs (EUR/USD, GBP/USD, etc.)"
            ],
            "analysis_types": [
                "Price tracking",
                "Technical analysis",
                "News aggregation",
                "Market sentiment",
                "AI insights"
            ],
            "caching": {
                "price_data": "60 seconds",
                "news_data": "300 seconds",
                "forex_rates": "60 seconds"
            }
        },
        "protocol": {
            "version": "A2A/1.0",
            "jsonrpc": "2.0",
            "blocking_mode": True,
            "non_blocking_mode": True,
            "webhook_support": True
        },
        "contact": {
            "support": "github.com/lexmanthefirst/forex-crypto-news-a2a-protocol"
        }
    }



# Register Routers
app.include_router(a2a_router)
app.include_router(system_router)



# Main Entry Point
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)



# Agent Processing
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


