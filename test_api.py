"""
Simple test script to validate the A2A Market endpoint.
Run this with: python test_api.py
"""

import requests

BASE_URL = "http://localhost:8000"


def test_health_check():
    """Test the health endpoint."""
    print("Testing /health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_message_send():
    """Test the JSON-RPC message/send method."""
    print("Testing /a2a/market with message/send...")
    payload = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "parts": [{"kind": "text", "text": "Analyze BTC"}]
            }
        }
    }
    
    response = requests.post(f"{BASE_URL}/a2a/market", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_execute_method():
    """Test the JSON-RPC execute method."""
    print("Testing /a2a/market with execute...")
    payload = {
        "jsonrpc": "2.0",
        "id": "test-2",
        "method": "execute",
        "params": {
            "contextId": "test-context",
            "taskId": "test-task",
            "messages": [
                {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Analyze EUR/USD"}]
                }
            ]
        }
    }
    
    response = requests.post(f"{BASE_URL}/a2a/market", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_multiple_symbols():
    """Test analysis with multiple crypto symbols."""
    print("Testing multiple symbols...")
    symbols = ["BTC", "ETH", "DOGE"]
    
    for symbol in symbols:
        payload = {
            "jsonrpc": "2.0",
            "id": f"test-{symbol}",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": f"Analyze {symbol}"}]
                }
            }
        }
        
        response = requests.post(f"{BASE_URL}/a2a/market", json=payload)
        print(f"{symbol} - Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json().get("result", {})
            status = result.get("status", {})
            print(f"{symbol} - State: {status.get('state')}")
        else:
            print(f"{symbol} - Error: {response.json()}")
        print()


def test_invalid_request():
    """Test error handling with invalid payload."""
    print("Testing invalid request handling...")
    payload = {
        "jsonrpc": "2.0",
        "id": "test-invalid",
        "method": "invalid-method",
        "params": {}
    }
    
    response = requests.post(f"{BASE_URL}/a2a/market", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 400


if __name__ == "__main__":
    print("=" * 60)
    print("A2A Market Intelligence API Test Suite")
    print("=" * 60 + "\n")
    
    results = {
        "Health Check": test_health_check(),
        "Message Send": test_message_send(),
        "Execute Method": test_execute_method(),
        "Invalid Request": test_invalid_request(),
    }
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name}: {status}")
    
    print("\nRunning additional tests...")
    test_multiple_symbols()
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)
