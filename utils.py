import json
import requests
import difflib
from datetime import datetime
from openai import OpenAI

def ask_grok(market_data: dict, platform: str, client: OpenAI) -> dict:
    """Ask Grok for structured trade recommendation"""
    prompt = f"""You are GrokUltimateTrader, a world-class profitable prediction market trader.
Analyze this {platform} market and output ONLY valid JSON (no extra text).

Market: {json.dumps(market_data)}

Return JSON with keys:
- reasoning: string (detailed analysis, key factors, news synthesis)
- yes_probability: float (0-1, your true fair probability of YES)
- confidence: float (0-1)
- action: "BUY_YES" | "BUY_NO" | "SELL_YES" | "SELL_NO" | "HOLD"
- suggested_price: float (limit price to enter)
- edge_percent: float (your edge vs current market price)
- kelly_fraction: float (0-1 recommended bankroll %)

Current time: {datetime.now().isoformat()}"""
    response = client.chat.completions.create(
        model="grok-4.3",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def fetch_kalshi_markets(limit=30):
    """Public Kalshi open markets"""
    url = "https://external-api.kalshi.com/trade-api/v2/markets"
    params = {"status": "open", "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json().get("markets", [])
        return [{"platform": "Kalshi", "ticker": m["ticker"], "title": m["title"], 
                 "yes_price": m.get("yes_price", 50)/100, "volume": m.get("volume_24h", 0)} for m in data]
    except:
        return []

def fetch_polymarket_markets(limit=30):
    """Public Polymarket markets via Gamma API"""
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": limit, "active": True}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return [{"platform": "Polymarket", "ticker": m["condition_id"], "title": m["question"], 
                 "yes_price": float(m.get("tokens", [{}])[0].get("price", 0.5)), 
                 "volume": m.get("volume", 0)} for m in data if m.get("tokens")]
    except:
        return []

def detect_arbitrage(markets):
    """Simple title-based cross-platform arb detection"""
    kalshi = [m for m in markets if m["platform"] == "Kalshi"]
    poly = [m in markets if m["platform"] == "Polymarket"]
    arbs = []
    for k in kalshi:
        for p in poly:
            sim = difflib.SequenceMatcher(None, k["title"].lower(), p["title"].lower()).ratio()
            if sim > 0.85 and abs(k["yes_price"] - p["yes_price"]) > 0.03:
                arbs.append({
                    "kalshi": k["ticker"], "polymarket": p["ticker"],
                    "title": k["title"], "kalshi_yes": k["yes_price"],
                    "poly_yes": p["yes_price"], "spread": abs(k["yes_price"] - p["yes_price"])
                })
    return arbs