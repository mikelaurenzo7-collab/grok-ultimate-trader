import streamlit as st
import os
import json
import sqlite3
import requests
import pandas as pd
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import difflib

load_dotenv()

st.set_page_config(page_title="GrokUltimateTrader", page_icon="🚀", layout="wide")
st.title("🚀 GrokUltimateTrader")
st.caption("Kalshi + Polymarket | Grok-Powered | Running 24/7 on Railway")

XAI_API_KEY = os.getenv("XAI_API_KEY")
SIMULATION = os.getenv("SIMULATION_MODE", "true").lower() == "true"

if not XAI_API_KEY:
    st.error("XAI_API_KEY not set in Railway Variables!")
    st.stop()

client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

conn = sqlite3.connect("trades.db", check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    platform TEXT,
    ticker TEXT,
    side TEXT,
    price REAL,
    size REAL,
    grok_prob REAL,
    edge REAL,
    status TEXT
)''')
conn.commit()

def ask_grok(market_data, platform):
    prompt = f"""You are GrokUltimateTrader - elite prediction market trader.
Analyze this {platform} market. Respond with **only** valid JSON.

Market: {json.dumps(market_data)}

JSON format:
{{"reasoning": "string", "yes_probability": float 0-1, "confidence": float 0-1, "action": "BUY_YES" | "BUY_NO" | "HOLD", "suggested_price": float, "edge_percent": float, "kelly_fraction": float}}"""
    try:
        resp = client.chat.completions.create(
            model="grok-4.3",
            messages=[{"role":"user", "content":prompt}],
            temperature=0.3,
            response_format={{"type": "json_object"}}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print("Grok error:", e)
        return None

def fetch_kalshi_markets(limit=25):
    try:
        r = requests.get("https://trading-api.kalshi.com/trade-api/v2/markets", params={"status":"open","limit":limit}, timeout=12)
        data = r.json().get("markets", [])
        return [{
            "platform": "Kalshi",
            "ticker": m["ticker"],
            "title": m.get("title", ""),
            "yes_price": m.get("yes_price", 50)/100,
            "volume": m.get("volume_24h", 0)
        } for m in data if m.get("title")]
    except:
        return []

def fetch_polymarket_markets(limit=25):
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets", params={"limit": limit}, timeout=12)
        markets = []
        for m in r.json():
            if m.get("tokens"):
                markets.append({
                    "platform": "Polymarket",
                    "ticker": m.get("condition_id"),
                    "title": m.get("question", ""),
                    "yes_price": float(m["tokens"][0].get("price", 0.5)),
                    "volume": m.get("volume", 0)
                })
        return markets
    except:
        return []

def detect_arbitrage(markets):
    kal = [m for m in markets if m["platform"] == "Kalshi"]
    poly = [m for m in markets if m["platform"] == "Polymarket"]
    arbs = []
    for k in kal:
        for p in poly:
            if difflib.SequenceMatcher(None, k["title"].lower(), p["title"].lower()).ratio() > 0.83 and abs(k["yes_price"] - p["yes_price"]) > 0.03:
                arbs.append({"title": k["title"], "kal_yes": round(k["yes_price"],3), "poly_yes": round(p["yes_price"],3), "diff": round(abs(k["yes_price"]-p["yes_price"]),3)})
    return arbs

tab1, tab2 = st.tabs(["Scanner", "History"])

with tab1:
    if st.button("Run Market Scan + Grok Analysis", type="primary"):
        with st.spinner("Consulting Grok..."):
            k = fetch_kalshi_markets()
            p = fetch_polymarket_markets()
            markets = k + p
            arbs = detect_arbitrage(markets)
            if arbs:
                st.success(f"Found {len(arbs)} arbs!")
                st.dataframe(pd.DataFrame(arbs))
            # Grok analysis on top markets
            for m in markets[:10]:
                analysis = ask_grok(m, m["platform"])
                if analysis and analysis.get("edge_percent", 0) > 3:
                    st.write(f"**Edge on {m['title'][:50]}** - {analysis['action']} | Edge {analysis['edge_percent']}%")

with tab2:
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20", conn)
    st.dataframe(df)

st.success("✅ GrokUltimateTrader is ready on Railway")