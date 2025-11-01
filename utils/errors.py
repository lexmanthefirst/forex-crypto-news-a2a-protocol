"""
A2A protocol error handling utilities.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class A2AErrorCode(Enum):
    """Standard JSON-RPC 2.0 error codes for A2A protocol."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


def create_error_response(
    request_id: str | None,
    code: A2AErrorCode,
    message: str,
    data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Create a JSON-RPC 2.0 error response.

    Args:
        request_id: The request ID (can be None for parse errors)
        code: The A2A error code enum
        message: Human-readable error message
        data: Optional additional error data

    Returns:
        JSON-RPC 2.0 error response dict
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code.value,
            "message": message,
            "data": data or {}
        }
    }
