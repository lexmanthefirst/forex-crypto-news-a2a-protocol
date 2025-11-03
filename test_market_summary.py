"""
Test script for market summary functionality.
"""
import asyncio
import json

from utils.market_summary import (
    get_comprehensive_market_summary,
    format_market_summary_text,
    get_top_cryptos_by_market_cap,
    get_trending_cryptos,
    analyze_performers,
)


async def test_top_cryptos():
    print("\n=== Testing Top Cryptos by Market Cap ===")
    cryptos = await get_top_cryptos_by_market_cap(limit=10)
    print(f"Fetched {len(cryptos)} cryptocurrencies")
    
    if cryptos:
        print("\nTop 3:")
        for i, coin in enumerate(cryptos[:3], 1):
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            change_24h = coin.get("price_change_percentage_24h", 0)
            print(f"{i}. {symbol} ({name}): ${price:,.2f} ({change_24h:+.2f}%)")


async def test_trending():
    print("\n=== Testing Trending Cryptos ===")
    trending = await get_trending_cryptos()
    print(f"Fetched {len(trending)} trending coins")
    
    if trending:
        print("\nTrending coins:")
        for coin in trending[:5]:
            symbol = coin.get("symbol", "")
            name = coin.get("name", "")
            rank = coin.get("market_cap_rank", "N/A")
            print(f"• {symbol} - {name} (Rank #{rank})")


async def test_performance_analysis():
    print("\n=== Testing Performance Analysis ===")
    cryptos = await get_top_cryptos_by_market_cap(limit=20)
    
    if cryptos:
        performance = analyze_performers(cryptos)
        
        print("\nBest Performers (24h):")
        for coin in performance["best_24h"]:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            change = coin.get("price_change_percentage_24h", 0)
            print(f"• {symbol} ({name}): {change:+.2f}%")
        
        print("\nWorst Performers (24h):")
        for coin in performance["worst_24h"]:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            change = coin.get("price_change_percentage_24h", 0)
            print(f"• {symbol} ({name}): {change:+.2f}%")
        
        print(f"\nAverage 24h Change: {performance['average_change_24h']:+.2f}%")
        print(f"Total Market Cap (Top 20): ${performance['total_market_cap']:,.0f}")


async def test_comprehensive_summary():
    print("\n=== Testing Comprehensive Market Summary ===")
    summary = await get_comprehensive_market_summary()
    
    print("\n" + "="*70)
    print(format_market_summary_text(summary))
    print("="*70)
    
    # Save to JSON file for inspection
    with open("market_summary_sample.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nFull summary saved to: market_summary_sample.json")


async def main():
    print("Testing Market Summary Utilities")
    print("="*70)
    
    try:
        await test_top_cryptos()
        await asyncio.sleep(1)
        
        await test_trending()
        await asyncio.sleep(1)
        
        await test_performance_analysis()
        await asyncio.sleep(1)
        
        await test_comprehensive_summary()
        
        print("\n✓ All tests completed successfully!")
        
    except Exception as exc:
        print(f"\n✗ Test failed: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
