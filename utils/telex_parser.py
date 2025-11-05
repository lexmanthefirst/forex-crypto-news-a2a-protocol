"""
Telex Message Parser

Enhanced text extraction for Telex.im messages with conversation history support.
Combines robust extraction strategies with comprehensive fallback paths.

Inspired by emmanueldev247/hng-stage3-task implementation with enhancements.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any

# Regex patterns for cleaning
_TAGS_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


def clean_html(raw: str) -> str:
    """
    Clean HTML tags and entities from text.
    
    Args:
        raw: Raw text potentially containing HTML
    
    Returns:
        Cleaned text with HTML removed and entities decoded
    """
    if not raw:
        return ""
    # Decode HTML entities (&amp; -> &, etc.)
    text = unescape(raw)
    # Remove HTML tags
    text = _TAGS_RE.sub(" ", text)
    # Normalize whitespace
    text = _WS_RE.sub(" ", text).strip()
    return text


def extract_conversation_history(params: dict[str, Any]) -> list[str]:
    """
    Extract conversation history from Telex message data parts.
    
    Telex stores conversation history in parts[1].data[*].text structure.
    This extracts the last 20 messages for context.
    
    Args:
        params: JSON-RPC params object
    
    Returns:
        List of previous message texts (oldest to newest, max 20)
    """
    history: list[str] = []
    
    try:
        message = (params or {}).get("message") or {}
        parts = message.get("parts") or []
        
        # Check for data part at parts[1]
        if len(parts) > 1 and isinstance(parts[1], dict):
            if parts[1].get("kind") == "data":
                data_items = parts[1].get("data") or []
                
                for item in data_items:
                    if isinstance(item, dict) and item.get("kind") == "text":
                        text = clean_html(item.get("text") or "")
                        if text:
                            history.append(text)
        
        # Return last 20 messages for context
        return history[-20:] if history else []
        
    except Exception:
        return []


def extract_text_primary(params: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """
    Primary text extraction strategy for Telex messages.
    
    Extraction priority:
    1. Last message from parts[1].data[*].text (conversation history)
    2. Current message from parts[0].text
    3. Fallback to message.text
    
    Args:
        params: JSON-RPC params object
    
    Returns:
        Tuple of (extracted_text, debug_info)
    """
    extracted_text: str | None = None
    debug_info: dict[str, Any] = {"source": None, "history_count": 0}
    
    try:
        message = (params or {}).get("message") or {}
        parts = message.get("parts") or []
        
        # Strategy 1: Get conversation history and use last message
        history = extract_conversation_history(params)
        if history:
            extracted_text = history[-1]
            debug_info["source"] = "conversation_history"
            debug_info["history_count"] = len(history)
            debug_info["history_index"] = len(history) - 1
            return extracted_text, debug_info
        
        # Strategy 2: Current message from parts[0].text
        if len(parts) > 0 and isinstance(parts[0], dict):
            if parts[0].get("kind") == "text":
                text = clean_html(parts[0].get("text") or "")
                if text:
                    extracted_text = text
                    debug_info["source"] = "parts[0].text"
                    return extracted_text, debug_info
        
        # Strategy 3: Fallback to message.text
        message_text = clean_html(message.get("text") or "")
        if message_text:
            extracted_text = message_text
            debug_info["source"] = "message.text"
            return extracted_text, debug_info
        
    except Exception as e:
        debug_info["error"] = str(e)
    
    return extracted_text, debug_info


def extract_text_fallback(params: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """
    Fallback text extraction strategy (less aggressive cleaning).
    
    Used when primary extraction fails. Tries raw text without cleaning.
    
    Args:
        params: JSON-RPC params object
    
    Returns:
        Tuple of (extracted_text, debug_info)
    """
    extracted_text: str | None = None
    debug_info: dict[str, Any] = {"source": None, "strategy": "fallback"}
    
    try:
        message = (params or {}).get("message") or {}
        parts = message.get("parts") or []
        
        # Try parts[0].text without cleaning
        if len(parts) > 0 and isinstance(parts[0], dict):
            if parts[0].get("kind") == "text":
                text = (parts[0].get("text") or "").strip()
                if text:
                    extracted_text = text
                    debug_info["source"] = "parts[0].text_raw"
                    return extracted_text, debug_info
        
        # Try message.text without cleaning
        message_text = (message.get("text") or "").strip()
        if message_text:
            extracted_text = message_text
            debug_info["source"] = "message.text_raw"
            return extracted_text, debug_info
        
    except Exception as e:
        debug_info["error"] = str(e)
    
    return extracted_text, debug_info


def extract_text_from_telex_message(params: dict[str, Any]) -> tuple[str | None, list[str], dict[str, Any]]:
    """
    Comprehensive text extraction from Telex message with multiple strategies.
    
    Tries primary extraction first, then fallback if needed.
    Also extracts conversation history for context.
    
    Args:
        params: JSON-RPC params object (message/send or execute)
    
    Returns:
        Tuple of:
        - extracted_text: The main query text
        - conversation_history: List of previous messages (last 20)
        - debug_info: Metadata about extraction process
    
    Examples:
        >>> params = {"message": {"parts": [{"kind": "text", "text": "What is BTC price?"}]}}
        >>> text, history, debug = extract_text_from_telex_message(params)
        >>> text
        "What is BTC price?"
        >>> debug["source"]
        "parts[0].text"
    """
    # Try primary extraction
    text, debug_info = extract_text_primary(params)
    
    # If primary fails, try fallback
    if not text:
        text, fallback_debug = extract_text_fallback(params)
        debug_info.update(fallback_debug)
    
    # Always extract conversation history
    history = extract_conversation_history(params)
    debug_info["history_count"] = len(history)
    
    return text, history, debug_info


def parse_jsonrpc_lenient(body: dict[str, Any] | None) -> tuple[str, str | None, dict[str, Any]]:
    """
    Lenient JSON-RPC parsing that doesn't raise errors.
    
    Extracts id, method, and params without strict validation.
    Returns defaults for missing fields instead of failing.
    
    Args:
        body: JSON-RPC request body
    
    Returns:
        Tuple of (request_id, method, params)
    """
    body = body or {}
    request_id = body.get("id", "")
    method = body.get("method", None)
    params = body.get("params") or {}
    
    return str(request_id), method, params
