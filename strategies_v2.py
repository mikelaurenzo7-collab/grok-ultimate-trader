"""Trading strategies for Kalshi prediction markets."""
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    ticker: str
    side: str  # "yes" or "no"
    action: str  # "buy" or "sell"
    price: int  # cents 1-99
    edge_bps: int  # edge in basis points (hundredths of a cent)
    confidence: float  # 0.0 - 1.0
    strategy: str
    reason: str


class FavoriteLongshotStrategy:
    """
    Exploits the favorite-longshot bias documented in academic research.
    
    Research on 313,972 Kalshi contracts shows:
    - Low-priced contracts (longshots) win LESS than implied probability
    - High-priced contracts (favorites) win MORE than implied probability
    
    We SHORT longshots (sell NO when YES is cheap, or sell YES when NO is cheap)
    and BUY favorites.
    
    Actually on Kalshi you can only buy. But you can buy YES or buy NO.
    So the play is:
    - When YES price is very low (e.g. 5c), buy NO instead (which is ~95c)
      because the longshot YES is overpriced relative to true probability
    - When YES price is very high (e.g. 95c), buy YES (favorite is underpriced)
    
    Edge threshold must clear fees + safety margin.
    """

    def __init__(self, min_edge_bps: int = 300, max_price: int = 15, min_price: int = 85):
        """
        min_edge_bps: minimum edge in basis points (3% = 300 bps)
        max_price: maximum YES price to consider as "longshot" (buy NO)
        min_price: minimum YES price to consider as "favorite" (buy YES)
        """
        self.min_edge_bps = min_edge_bps
        self.max_price = max_price  # YES <= 15c → buy NO
        self.min_price = min_price  # YES >= 85c → buy YES

    def analyze(self, ticker: str, yes_price: int, no_price: int,
                volume_24h: float = 0, estimated_true_prob: Optional[float] = None) -> Optional[Signal]:
        """
        yes_price/no_price: in cents (1-99), must sum to ~100
        
        If estimated_true_prob provided, use that for edge calc.
        Otherwise use heuristic based on historical bias.
        """
        # Validate prices roughly sum to 100
        if abs((yes_price + no_price) - 100) > 5:
            return None

        signal = None

        # Case 1: Longshot — YES is cheap. Buy NO because longshot is overpriced
        if yes_price <= self.max_price:
            # Historical bias: longshot YES wins ~10-30% less than implied
            # So if YES is at 10c (10% implied), true prob might be 7%
            # NO should be 93c but is priced at 90c → 3c edge
            implied_prob = yes_price / 100.0
            # Heuristic adjustment: longshots win 0.7x implied
            adjusted_prob = implied_prob * 0.75  # conservative
            fair_no_price = int((1 - adjusted_prob) * 100)
            edge = fair_no_price - no_price  # in cents

            if edge * 100 >= self.min_edge_bps:  # convert cents to bps
                signal = Signal(
                    ticker=ticker,
                    side="no",
                    action="buy",
                    price=no_price,
                    edge_bps=edge * 100,
                    confidence=min(0.7, edge / 10),
                    strategy="fav_longshot",
                    reason=f"YES at {yes_price}c is longshot, buying NO at {no_price}c with {edge}c edge"
                )

        # Case 2: Favorite — YES is expensive. Buy YES because favorite is underpriced
        elif yes_price >= self.min_price:
            implied_prob = yes_price / 100.0
            # Heuristic adjustment: favorites win ~1.05-1.15x implied
            adjusted_prob = min(implied_prob * 1.08, 0.99)
            fair_yes_price = int(adjusted_prob * 100)
            edge = fair_yes_price - yes_price

            if edge * 100 >= self.min_edge_bps:
                signal = Signal(
                    ticker=ticker,
                    side="yes",
                    action="buy",
                    price=yes_price,
                    edge_bps=edge * 100,
                    confidence=min(0.75, edge / 5),
                    strategy="fav_longshot",
                    reason=f"YES at {yes_price}c is favorite, buying with {edge}c edge"
                )

        return signal


class IntraMarketArbitrageStrategy:
    """
    The mechanical free money play: YES + NO must equal $1.00.
    If sum < $1.00 minus fees, buy both and hold to expiry.
    
    On Kalshi:
    - Buy YES at price A
    - Buy NO at price B  
    - If A + B < 100, guaranteed profit = 100 - (A + B)
    
    Fees: ~1-2% of max profit. So need sum <= ~97 to be safe.
    
    This is RARE on liquid markets but appears on illiquid ones after news.
    """

    def __init__(self, max_sum: int = 97, min_liquidity: int = 100):
        self.max_sum = max_sum  # cents
        self.min_liquidity = min_liquidity  # minimum contracts available

    def analyze(self, ticker: str, best_yes_ask: int, best_no_ask: int,
                yes_depth: int = 0, no_depth: int = 0) -> Optional[Signal]:
        """
        best_yes_ask: best ask price for YES (lowest sell price)
        best_no_ask: best ask price for NO
        """
        total = best_yes_ask + best_no_ask

        if total > self.max_sum:
            return None

        if yes_depth < self.min_liquidity or no_depth < self.min_liquidity:
            return None

        profit_cents = 100 - total
        edge_bps = profit_cents * 100  # convert to basis points

        # Buy the side with better available size
        # Actually we need to buy BOTH sides. This signal represents the arb.
        # For simplicity, we'll generate a buy on the side with more edge.
        # In practice we'd need to buy both legs.

        return Signal(
            ticker=ticker,
            side="yes",  # We need both, but start with YES
            action="buy",
            price=best_yes_ask,
            edge_bps=edge_bps,
            confidence=0.95,  # mechanical arb is high confidence
            strategy="intra_market_arb",
            reason=f"YES({best_yes_ask}c) + NO({best_no_ask}c) = {total}c < 100c, arb profit {profit_cents}c"
        )


class MomentumStrategy:
    """
    For scheduled macro events: CPI, Fed rates, etc.
    
    Strategy: In the 0-10 min after news breaks, markets are chaotic.
    The FIRST move is often wrong. Fade the initial spike.
    
    Actually better: wait for the informed money to push price,
    then ride the trend in the 10-60 min window.
    
    This needs external data feed (news API, economic calendar).
    """

    def __init__(self):
        self.recent_prices: dict[str, list[tuple[float, int]]] = {}  # ticker -> [(timestamp, price)]

    def on_price_update(self, ticker: str, yes_price: int, timestamp: float):
        if ticker not in self.recent_prices:
            self.recent_prices[ticker] = []
        self.recent_prices[ticker].append((timestamp, yes_price))
        # Keep last 60 minutes
        cutoff = timestamp - 3600
        self.recent_prices[ticker] = [(t, p) for t, p in self.recent_prices[ticker] if t > cutoff]

    def analyze(self, ticker: str, event_type: str = "") -> Optional[Signal]:
        """Analyze price history for momentum signals."""
        prices = self.recent_prices.get(ticker, [])
        if len(prices) < 10:
            return None

        # Simple momentum: 5-min change vs 30-min trend
        now = prices[-1][0]
        recent = [p for t, p in prices if now - t < 300]  # 5 min
        older = [p for t, p in prices if 300 <= now - t < 1800]  # 5-30 min

        if not recent or not older:
            return None

        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        # If recent is trending up strongly, buy YES
        if recent_avg > older_avg * 1.05 and recent_avg < 95:
            return Signal(
                ticker=ticker,
                side="yes",
                action="buy",
                price=int(recent[-1]),
                edge_bps=int((recent_avg - older_avg) * 100),
                confidence=0.55,
                strategy="momentum",
                reason=f"Upward momentum: {older_avg:.1f}c → {recent_avg:.1f}c"
            )

        # If trending down strongly, buy NO
        if recent_avg < older_avg * 0.95 and recent_avg > 5:
            no_price = 100 - int(recent[-1])
            return Signal(
                ticker=ticker,
                side="no",
                action="buy",
                price=no_price,
                edge_bps=int((older_avg - recent_avg) * 100),
                confidence=0.55,
                strategy="momentum",
                reason=f"Downward momentum: {older_avg:.1f}c → {recent_avg:.1f}c"
            )

        return None
