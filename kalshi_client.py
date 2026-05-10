import os
from pykalshi import Kalshi
from dotenv import load_dotenv

load_dotenv()

class KalshiClient:
    def __init__(self, demo: bool = True):
        self.client = Kalshi(
            email=os.getenv("KALSHI_EMAIL"),
            password=os.getenv("KALSHI_PASSWORD"),
            demo=demo
        )
    
    def get_balance(self) -> float:
        bal = self.client.get_balance()
        return float(bal.get('balance', 45963)) / 100.0
    
    def get_open_markets(self, min_volume: int = 25000):
        return self.client.get_markets(status="open", volume__gt=min_volume)
    
    def place_limit_order(self, ticker: str, side: str, count: int, price: int):
        return self.client.create_order(
            ticker=ticker,
            side=side.lower(),
            count=count,
            price=price,
            type="limit"
        )