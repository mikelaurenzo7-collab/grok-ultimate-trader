import time
from datetime import datetime
from app import fetch_kalshi_markets, fetch_polymarket_markets, detect_arbitrage, ask_grok
import sqlite3

print("🚀 Starting GrokUltimateTrader autonomous loop on Railway")

conn = sqlite3.connect('trades.db')

while True:
    print(f"[{datetime.now()}] Scanning markets...")
    try:
        kalshi = fetch_kalshi_markets(20)
        polymarket = fetch_polymarket_markets(20)
        all_markets = kalshi + polymarket
        
        arbs = detect_arbitrage(all_markets)
        if len(arbs) > 0:
            print(f"🚨 Detected {len(arbs)} potential arbs")
        
        # Analyze with Grok
        for market in all_markets[:8]:
            analysis = ask_grok(market, market['platform'])
            if analysis and analysis.get('edge_percent', 0) > 4.0:
                print(f"HIGH EDGE FOUND: {market['title'][:60]} | {analysis['action']} | Edge: {analysis['edge_percent']}%")
                # Future: place real orders here
    except Exception as e:
        print("Error:", str(e))
    
    print("Sleeping 10 minutes...")
    time.sleep(600)
