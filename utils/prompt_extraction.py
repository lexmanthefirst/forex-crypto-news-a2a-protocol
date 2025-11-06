"""
Prompt-based extraction utilities using Gemini.

Provides intelligent extraction of coins, forex pairs, and other entities
from natural language queries using LLM-powered prompts.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from utils.gemini_client import generate_text_sync

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        logger.error(f"Prompt file not found: {prompt_path}")
        return ""
    return prompt_path.read_text(encoding="utf-8")


def extract_coin_with_llm(query: str) -> str | None:
    """
    Extract cryptocurrency name/symbol from query using LLM.
    
    Uses a prompt-based approach that understands context and ignores
    command words automatically.
    
    Args:
        query: User query like "analyze ethereum" or "check BTC price"
    
    Returns:
        Coin name/symbol if found, None if no valid coin mentioned
    
    Examples:
        >>> extract_coin_with_llm("analyze ethereum")
        "ethereum"
        >>> extract_coin_with_llm("what is bitcoin price")
        "bitcoin"
        >>> extract_coin_with_llm("hello there")
        None
    """
    try:
        # Load prompt template
        prompt_template = load_prompt("extract_coin.prompt")
        if not prompt_template:
            logger.error("Failed to load coin extraction prompt")
            return None
        
        # Fill in the query
        prompt = prompt_template.format(query=query)
        
        # Call Gemini with low temperature for consistent extraction
        response = generate_text_sync(prompt, temperature=0.1, timeout=5)
        
        if not response:
            logger.warning(f"Empty response from LLM for query: {query}")
            return None
        
        # Clean up response - remove any quotes, whitespace, markdown
        result = response.strip().strip('"').strip("'").strip('`').strip()
        
        # Check if no coin was found
        if result.upper() == "NONE" or not result or len(result) > 50:
            logger.debug(f"No coin found in query: {query}")
            return None
        
        logger.debug(f"Extracted coin '{result}' from query: {query}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to extract coin with LLM: {e}", exc_info=True)
        return None
