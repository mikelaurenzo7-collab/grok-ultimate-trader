"""
Kalshi API client wrapper using the OFFICIAL kalshi-python-sync SDK.
Handles auth, token refresh, and rate limiting automatically.
"""
import os
import time
from pathlib import Path

# Official Kalshi SDK
try:
    from kalshi_python_sync import Configuration, KalshiClient as OfficialClient
except ImportError:
    print("[WARN] kalshi_python_sync not installed. Run: pip install kalshi-python-sync")
    raise


class KalshiTraderClient:
    """
    Production-grade wrapper around official Kalshi SDK.
    """

    SANDBOX_HOST = "https://demo-api.kalshi.co/trade-api/v2"
    PRODUCTION_HOST = "https://api.elections.kalshi.com/trade-api/v2"

    def __init__(self, key_id: str, private_key_path: str, sandbox: bool = True):
        self.sandbox = sandbox
        host = self.SANDBOX_HOST if sandbox else self.PRODUCTION_HOST

        # Read private key
        with open(private_key_path, "r") as f:
            private_key = f.read()

        config = Configuration(
            host=host,
            api_key_id=key_id,
            private_key_pem=private_key,
        )
        self.client = OfficialClient(config)
        self._member_id = None

    def get_balance(self):
        """Get account balance in cents."""
        resp = self.client.get_balance()
        return resp.balance if hasattr(resp, 'balance') else 0

    def get_markets(self, status: str = "active", limit: int = 100, cursor: str = None):
        """List active markets."""
        kwargs = {"status": status, "limit": limit}
        if cursor:
            kwargs["cursor"] = cursor
        return self.client.get_markets(**kwargs)

    def get_market(self, ticker: str):
        """Get single market details."""
        return self.client.get_market(ticker=ticker)

    def get_orderbook(self, ticker: str, depth: int = 10):
        """Get orderbook for a market."""
        return self.client.get_orderbook(ticker=ticker, depth=depth)

    def get_positions(self):
        """Get current positions."""
        return self.client.get_positions()

    def create_order(self, ticker: str, side: str, count: int, price: int,
                     action: str = "buy", order_type: str = "limit"):
        """
        Place an order.
        side: "yes" or "no"
        price: cents (1-99)
        count: number of contracts
        Returns order response.
        """
        client_order_id = f"bot_{int(time.time() * 1000)}"
        return self.client.create_order(
            ticker=ticker,
            client_order_id=client_order_id,
            side=side,
            action=action,
            type=order_type,
            count=count,
            price=price,
        )

    def cancel_order(self, order_id: str):
        """Cancel an order by ID."""
        return self.client.cancel_order(order_id=order_id)

    def get_orders(self, status: str = "active", ticker: str = None):
        """Get orders."""
        kwargs = {"status": status}
        if ticker:
            kwargs["ticker"] = ticker
        return self.client.get_orders(**kwargs)

    def get_exchange_status(self):
        """Check if exchange is open."""
        return self.client.get_exchange_status()
