from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from kalshi_client import KalshiClient
from strategy import KalshiSportsStrategy

app = FastAPI(title="Grok Ultimate Kalshi Trader")

client = KalshiClient(demo=True)  # Set False for live
strategy = KalshiSportsStrategy(client)

scheduler = BackgroundScheduler()

def scan_and_trade():
    try:
        bal = client.get_balance()
        opps = strategy.run_scan(bal)
        for op in opps[:3]:
            client.place_limit_order(
                op['ticker'],
                op['suggested_side'],
                op['size'],
                int(op['yes_price'] * 100)
            )
    except:
        pass

scheduler.add_job(scan_and_trade, 'interval', minutes=10)
scheduler.start()

@app.get("/")
def root():
    return {"status": "Grok Ultimate Kalshi Trader running"}

@app.get("/balance")
def get_balance():
    bal = client.get_balance()
    opps = strategy.run_scan(bal)
    return {"balance": bal, "opportunities": opps}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)