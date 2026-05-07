# 🚀 GrokUltimateTrader

**Grok-powered autonomous trader for Kalshi + Polymarket**

One unified brain scanning both platforms 24/7 for edges and cross-platform arbitrage.

## Quick Start on Railway
1. Add your `XAI_API_KEY` in Railway → Variables
2. Create **Web Service**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
3. Create **Background Worker**: `python trader_loop.py`
4. Add a Volume for persistent database (`trades.db`)

Start with `SIMULATION_MODE=true` for safety.

Built live by Grok.