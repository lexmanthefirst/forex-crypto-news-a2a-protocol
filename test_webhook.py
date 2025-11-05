"""
Test script to verify webhook payload format with Telex.

This script tests different webhook payload formats to find what Telex accepts.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

# Test webhook URL (replace with your actual webhook URL from error logs)
WEBHOOK_URL = "https://ping.telex.im/v1/a2a/webhooks/019a4f1a-2cc9-761b-a869-6efffa924bc2"
WEBHOOK_TOKEN = os.getenv("TELEX_WEBHOOK_TOKEN", "test-token")


async def test_format_1_jsonrpc_wrapper():
    """Test Format 1: JSON-RPC response wrapper (current implementation)"""
    print("\n" + "="*60)
    print("TEST 1: JSON-RPC Response Wrapper")
    print("="*60)
    
    payload = {
        "jsonrpc": "2.0",
        "id": "test-123",
        "result": {
            "id": "task-test-123",
            "contextId": "context-test",
            "status": {
                "state": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": {
                    "role": "agent",
                    "parts": [
                        {"kind": "text", "text": "Test response"}
                    ]
                }
            },
            "artifacts": [],
            "history": [],
            "kind": "task"
        }
    }
    
    print(f"Payload:\n{json.dumps(payload, indent=2)}\n")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WEBHOOK_TOKEN}"
                }
            )
            print(f"✅ Status: {response.status_code}")
            print(f"Response: {response.text}\n")
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ Status: {e.response.status_code}")
        print(f"Response: {e.response.text}\n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


async def test_format_2_clean_result():
    """Test Format 2: Clean result without JSON-RPC wrapper"""
    print("\n" + "="*60)
    print("TEST 2: Clean Result (No JSON-RPC wrapper)")
    print("="*60)
    
    payload = {
        "context_id": "context-test",
        "task_id": "task-test-123",
        "result": {
            "id": "task-test-123",
            "contextId": "context-test",
            "status": {
                "state": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": {
                    "role": "agent",
                    "parts": [
                        {"kind": "text", "text": "Test response"}
                    ]
                }
            },
            "artifacts": [],
            "history": [],
            "kind": "task"
        }
    }
    
    print(f"Payload:\n{json.dumps(payload, indent=2)}\n")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WEBHOOK_TOKEN}"
                }
            )
            print(f"✅ Status: {response.status_code}")
            print(f"Response: {response.text}\n")
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ Status: {e.response.status_code}")
        print(f"Response: {e.response.text}\n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


async def test_format_3_direct_task_result():
    """Test Format 3: Direct TaskResult (no wrapper at all)"""
    print("\n" + "="*60)
    print("TEST 3: Direct TaskResult")
    print("="*60)
    
    payload = {
        "id": "task-test-123",
        "contextId": "context-test",
        "status": {
            "state": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "role": "agent",
                "parts": [
                    {"kind": "text", "text": "Test response"}
                ]
            }
        },
        "artifacts": [],
        "history": [],
        "kind": "task"
    }
    
    print(f"Payload:\n{json.dumps(payload, indent=2)}\n")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WEBHOOK_TOKEN}"
                }
            )
            print(f"✅ Status: {response.status_code}")
            print(f"Response: {response.text}\n")
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ Status: {e.response.status_code}")
        print(f"Response: {e.response.text}\n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


async def test_format_4_minimal():
    """Test Format 4: Minimal payload"""
    print("\n" + "="*60)
    print("TEST 4: Minimal Payload")
    print("="*60)
    
    payload = {
        "status": "completed",
        "message": "Test response"
    }
    
    print(f"Payload:\n{json.dumps(payload, indent=2)}\n")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {WEBHOOK_TOKEN}"
                }
            )
            print(f"✅ Status: {response.status_code}")
            print(f"Response: {response.text}\n")
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ Status: {e.response.status_code}")
        print(f"Response: {e.response.text}\n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


async def main():
    print("\n" + "="*60)
    print("TELEX WEBHOOK PAYLOAD FORMAT TEST")
    print("="*60)
    print(f"Webhook URL: {WEBHOOK_URL}")
    print(f"Token: {WEBHOOK_TOKEN[:10]}..." if len(WEBHOOK_TOKEN) > 10 else "No token")
    
    results = {}
    
    # Test all formats
    results["Format 1 (JSON-RPC wrapper)"] = await test_format_1_jsonrpc_wrapper()
    await asyncio.sleep(1)  # Be nice to the server
    
    results["Format 2 (Clean result)"] = await test_format_2_clean_result()
    await asyncio.sleep(1)
    
    results["Format 3 (Direct TaskResult)"] = await test_format_3_direct_task_result()
    await asyncio.sleep(1)
    
    results["Format 4 (Minimal)"] = await test_format_4_minimal()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for format_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {format_name}")
    
    print("\n" + "="*60)
    winning_formats = [name for name, success in results.items() if success]
    if winning_formats:
        print(f"✅ Working format(s): {', '.join(winning_formats)}")
    else:
        print("❌ No formats worked. Check webhook URL and token.")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
