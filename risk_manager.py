"""Risk management, position sizing, and circuit breakers."""
import math
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    daily_trades: int = 0
    total_exposure: float = 0.0  # sum of position sizes
    max_drawdown: float = 0.0
    peak_capital: float = 0.0
    trades_today: list = field(default_factory=list)
    last_reset: datetime = field(default_factory=lambda: datetime.now())


class RiskManager:
    """
    Hardcoded risk rules. NOT flexible. These are the guardrails.
    """

    def __init__(
        self,
        capital: float = 500.0,
        max_daily_loss_pct: float = 0.05,  # 5%
        max_per_trade_pct: float = 0.02,     # 2%
        max_total_exposure_pct: float = 0.30,  # 30% deployed max
        kelly_fraction: float = 0.125,       # 1/8 Kelly (very conservative)
        min_edge_bps: int = 200,             # 2% minimum edge
        max_trades_per_day: int = 20,
        cooldown_seconds: int = 60,            # min time between trades on same market
    ):
        self.capital = capital
        self.initial_capital = capital
        self.max_daily_loss = capital * max_daily_loss_pct
        self.max_per_trade = capital * max_per_trade_pct
        self.max_total_exposure = capital * max_total_exposure_pct
        self.kelly_fraction = kelly_fraction
        self.min_edge_bps = min_edge_bps
        self.max_trades_per_day = max_trades_per_day
        self.cooldown_seconds = cooldown_seconds
        self.state = RiskState()
        self._trade_history: dict[str, float] = {}  # ticker -> last trade timestamp

    def _reset_daily(self):
        now = datetime.now()
        if now.date() != self.state.last_reset.date():
            self.state = RiskState(last_reset=now)

    def check_trade_allowed(self, signal, current_price: int, estimated_prob: float = 0.5) -> tuple[bool, Optional[int], str]:
        """
        Returns: (allowed, contract_count, reason)
        contract_count is how many contracts to buy
        """
        self._reset_daily()

        # 1. Circuit breaker: daily loss limit
        if self.state.daily_pnl <= -self.max_daily_loss:
            return False, None, f"DAILY LOSS CIRCUIT BREAKER: ${abs(self.state.daily_pnl):.2f} lost"

        # 2. Max trades per day
        if self.state.daily_trades >= self.max_trades_per_day:
            return False, None, "MAX TRADES PER DAY REACHED"

        # 3. Cooldown check
        last_trade = self._trade_history.get(signal.ticker, 0)
        import time
        if time.time() - last_trade < self.cooldown_seconds:
            return False, None, f"COOLDOWN: {self.cooldown_seconds}s between trades"

        # 4. Edge check
        if signal.edge_bps < self.min_edge_bps:
            return False, None, f"EDGE TOO SMALL: {signal.edge_bps} bps < {self.min_edge_bps} bps min"

        # 5. Position sizing (Fractional Kelly for binary prediction markets)
        # For binary contracts: if we buy at price P, edge E (in dollars), 
        # the simplified Kelly fraction is approximately E / P for small edges
        # Then we apply the fractional multiplier for safety
        price_dollars = current_price / 100.0
        edge_dollars = signal.edge_bps / 10000.0  # e.g., 300 bps = $0.03
        
        if price_dollars <= 0:
            return False, None, "INVALID PRICE"

        # Simplified Kelly: edge / price = advantage ratio
        # Then scale down by kelly_fraction for safety
        kelly = edge_dollars / price_dollars if price_dollars > 0 else 0
        kelly = max(0, min(kelly, 0.5))  # Cap Kelly at 50% (shouldn't happen, but safety)
        
        fraction = kelly * self.kelly_fraction
        target_dollar = fraction * self.capital
        
        # Cap at max per trade
        target_dollar = min(target_dollar, self.max_per_trade)
        
        # Also enforce a MINIMUM position size based on edge strength
        # Strong edge gets at least $5, weak edge needs to clear minimum
        min_trade = 5.0 if signal.edge_bps >= 300 else 10.0  # Require bigger commitment for smaller edges
        
        if target_dollar < min_trade:
            # Try to size up to minimum if edge is strong enough
            if signal.edge_bps >= 500:  # 5%+ edge
                target_dollar = min_trade
            else:
                return False, None, f"POSITION TOO SMALL: ${target_dollar:.2f} < ${min_trade} min"

        # Convert to contract count (each contract costs price_dollars, pays $1 if win)
        cost_per_contract = price_dollars
        count = max(1, int(target_dollar / cost_per_contract))
        
        if count < 1:
            return False, None, "CANT AFFORD EVEN 1 CONTRACT"

        # 6. Total exposure check
        trade_cost = count * cost_per_contract
        if self.state.total_exposure + trade_cost > self.max_total_exposure:
            return False, None, f"MAX EXPOSURE: would be ${self.state.total_exposure + trade_cost:.2f}"

        # 7. Liquidity check (handled by caller with orderbook depth)
        
        return True, count, f"APPROVED: {count} contracts @ {current_price}c, cost ${trade_cost:.2f}, edge {signal.edge_bps}bps"

        # 6. Total exposure check
        trade_cost = count * cost_per_contract
        if self.state.total_exposure + trade_cost > self.max_total_exposure:
            return False, None, f"MAX EXPOSURE: would be ${self.state.total_exposure + trade_cost:.2f}"

        # 7. Liquidity check (handled by caller with orderbook depth)
        
        return True, count, f"APPROVED: {count} contracts @ {price}c, cost ${trade_cost:.2f}, edge {signal.edge_bps}bps"

    def record_trade(self, ticker: str, count: int, price: int, side: str):
        """Record a trade for tracking."""
        import time
        self._trade_history[ticker] = time.time()
        self.state.daily_trades += 1
        cost = count * (price / 100.0)
        self.state.total_exposure += cost
        self.state.trades_today.append({
            "ticker": ticker,
            "count": count,
            "price": price,
            "side": side,
            "cost": cost,
            "time": datetime.now().isoformat(),
        })

    def record_pnl(self, pnl: float):
        """Record realized P&L from a closed position."""
        self.state.daily_pnl += pnl
        self.capital += pnl
        # Track drawdown
        if self.capital > self.state.peak_capital:
            self.state.peak_capital = self.capital
        dd = (self.state.peak_capital - self.capital) / self.state.peak_capital if self.state.peak_capital > 0 else 0
        self.state.max_drawdown = max(self.state.max_drawdown, dd)

    def get_status(self) -> dict:
        self._reset_daily()
        return {
            "capital": self.capital,
            "initial_capital": self.initial_capital,
            "daily_pnl": self.state.daily_pnl,
            "daily_trades": self.state.daily_trades,
            "total_exposure": self.state.total_exposure,
            "max_drawdown": self.state.max_drawdown,
            "remaining_daily_loss_budget": self.max_daily_loss + self.state.daily_pnl,
            "exposure_budget_remaining": self.max_total_exposure - self.state.total_exposure,
        }
