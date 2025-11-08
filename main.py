"""
A2A Market Intelligence Agent - Main Application

FastAPI application providing JSON-RPC 2.0 endpoint for market analysis
of cryptocurrencies and forex pairs using the Agent-to-Agent (A2A) protocol.

Architecture:
- Request parsing & validation layer
- Synchronous request handling
- Background scheduled analysis jobs
- Market intelligence agent integration
- Redis session storage

Endpoints:
- POST /a2a/agent/market: Main A2A protocol endpoint
- GET /health: Health check with dependency status
"""
from __future__ import annotations

import asyncio
import json
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
    """Parse and validate request body JSON."""
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
    """Validate JSON-RPC 2.0 request structure.
    
    Args:
        body: Request body dictionary
        lenient: Return errors as HTTP 200 with JSON-RPC error instead of HTTP 4xx
    """
    try:
        rpc = JSONRPCRequest(**body)
        return rpc
    except Exception as exc:
        request_id = body.get("id") if isinstance(body, dict) else None
        
        if lenient:
            error_payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": A2AErrorCode.INVALID_REQUEST.value,
                    "message": "Invalid Request",
                    "data": {"details": str(exc)}
                }
            }
            return JSONResponse(status_code=200, content=error_payload)
        else:
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

# async def _process_and_push_webhook(
#     messages: list[A2AMessage],
#     task_id: str,
#     context_id: str,
#     request_id: str,
#     config: MessageConfiguration | None,
#     push_url: str,
#     push_token: str,
# ) -> None:
#     """Process messages in background and push result to Telex webhook.
#     
#     This implements the non-blocking A2A pattern from the blog example.
#     """
#     try:
#         # Process with agent
#         result = await _process_with_agent(
#             messages,
#             context_id=context_id,
#             task_id=task_id,
#             config=config.model_dump(mode='json', by_alias=True) if config else None,
#         )
#         
#         # Build webhook payload - send full TaskResult with proper serialization
#         webhook_payload = result.model_dump(mode='json', by_alias=True, exclude_none=True)
#         
#         # Log webhook attempt
#         logger.info("[webhook] Sending to %s (task_id=%s, status=%s)", 
#                    push_url, task_id, result.status.state)
#         logger.debug("[webhook] Payload preview: %s", json.dumps(webhook_payload, indent=2)[:300])
#         
#         # Send webhook notification (blog's method)
#         headers = {"Content-Type": "application/json"}
#         
#             headers["Authorization"] = f"Bearer {push_token}"
#         
#         async with httpx.AsyncClient(timeout=60.0) as client:
#             response = await client.post(
#                 push_url,
#                 json=webhook_payload,
#                 headers=headers
#             )
#             response.raise_for_status()
#             logger.info("[webhook] ✓ Delivered successfully: status=%s task_id=%s", 
#                        response.status_code, task_id)
#             
#     except httpx.HTTPStatusError as e:
#         logger.error("[webhook] ✗ HTTP error %s: %s (task_id=%s)", 
#                     e.response.status_code, e.response.text[:200], task_id)
#     except Exception as e:
#         logger.error("[webhook] ✗ Failed: %s (task_id=%s)", e, task_id, exc_info=True)


async def _handle_message_send(rpc_request: JSONRPCRequest):
    """Handle message/send JSON-RPC method."""
    if not rpc_request.params:
        raise ValueError("Missing required 'params' field")
    
    params = rpc_request.params
    
    if not params.messages or len(params.messages) == 0:
        raise ValueError("At least one message is required")
    
    try:
        config = getattr(params, 'config', None)
        
        result = await _process_with_agent(
            params.messages,
            context_id=params.contextId,
            task_id=params.taskId,
            config=config
        )
        return result
        
    except Exception as e:
        logger.error(f"Error processing messages: {e}", exc_info=True)
        raise


async def _handle_execute(rpc_request: JSONRPCRequest):
    """Handle execute JSON-RPC method."""
    if not rpc_request.params:
        raise ValueError("Missing required 'params' field")
    
    params = rpc_request.params
    
    if not params.messages or len(params.messages) == 0:
        raise ValueError("At least one message is required")
    
    try:
        config = getattr(params, 'configuration', None)
        
        result = await _process_with_agent(
            params.messages,
            context_id=params.contextId,
            task_id=params.taskId,
            config=config
        )
        return result
        
    except Exception as e:
        logger.error(f"Error executing: {e}", exc_info=True)
        raise



# A2A Protocol Routes
@a2a_router.post("/market")
async def a2a_endpoint(request: Request):
    """Main A2A protocol endpoint for market analysis.
    
    Handles JSON-RPC 2.0 methods: message/send, execute
    """
    if market_agent is None:
        logger.error("Agent not initialized")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": A2AErrorCode.INTERNAL_ERROR.value,
                    "message": "Agent not initialized"
                }
            },
            status_code=500
        )
    
    try:
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON in request: {e}")
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": A2AErrorCode.PARSE_ERROR.value,
                        "message": "Invalid JSON"
                    }
                },
                status_code=400
            )
        
        if not isinstance(body, dict):
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": A2AErrorCode.INVALID_REQUEST.value,
                        "message": "Request must be a JSON object"
                    }
                },
                status_code=400
            )
        
        if body.get("jsonrpc") != "2.0":
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {
                        "code": A2AErrorCode.INVALID_REQUEST.value,
                        "message": "Invalid JSON-RPC version, must be '2.0'"
                    }
                },
                status_code=400
            )
        
        if "id" not in body:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": A2AErrorCode.INVALID_REQUEST.value,
                        "message": "Missing required field 'id'"
                    }
                },
                status_code=400
            )
        
        try:
            rpc_request = JSONRPCRequest(**body)
        except Exception as e:
            logger.error(f"Failed to parse JSON-RPC request: {e}")
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {
                        "code": A2AErrorCode.INVALID_REQUEST.value,
                        "message": "Invalid request format",
                        "data": {"details": str(e)}
                    }
                },
                status_code=400
            )
        
        logger.info(f"Received {rpc_request.method} request (id: {rpc_request.id})")
        
        if rpc_request.method == "message/send":
            result = await _handle_message_send(rpc_request)
            
        elif rpc_request.method == "execute":
            result = await _handle_execute(rpc_request)
            
        else:
            logger.warning(f"Unknown method: {rpc_request.method}")
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rpc_request.id,
                    "error": {
                        "code": A2AErrorCode.METHOD_NOT_FOUND.value,
                        "message": f"Method '{rpc_request.method}' not found"
                    }
                },
                status_code=404
            )
        
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=rpc_request.id,
            result=result
        )
        
        logger.info(f"Request {rpc_request.id} completed successfully")
        
        return JSONResponse(
            content=response.model_dump(exclude_none=True, mode='json'),
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in a2a_endpoint: {e}", exc_info=True)
        
        # Try to extract the request ID for error response
        error_id = None
        try:
            request_body = await request.json()
            error_id = request_body.get("id")
        except:
            pass
        
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": error_id,
                "error": {
                    "code": A2AErrorCode.INTERNAL_ERROR.value,
                    "message": "Internal server error",
                    "data": {"details": str(e)}
                }
            },
            status_code=500
        )


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
    """Agent manifest for A2A protocol discovery."""
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
            "Blocking/synchronous mode only (simplified implementation)"
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
            "non_blocking_mode": False,
            "webhook_support": False
        },
        "contact": {
            "support": "github.com/lexmanthefirst/forex-crypto-news-a2a-protocol"
        }
    }



app.include_router(a2a_router)
app.include_router(system_router)
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

