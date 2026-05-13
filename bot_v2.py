"""
Production Kalshi Trading Bot v2
Uses OFFICIAL kalshi-python-sync SDK + all strategies + simulator mode.
"""
import json
import time
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from kalshi_client_v2 import KalshiTraderClient
from strategies import FavoriteLongshotStrategy, IntraMarketArbitrageStrategy, MomentumStrategy
from risk_manager import RiskManager


class KalshiBotV2:
    """
    Production-ready autonomous Kalshi trading bot.
    
    Features:
    - Official SDK with proper auth
    - Multi-strategy engine
    - SQLite logging
    - Simulator mode (no real money)
    - Health checks
    """

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.simulator_mode = self.config.get("simulator_mode", True)
        self.sandbox = self.config.get("sandbox", True)
        
        # Initialize client only if not in simulator
        self.client = None
        if not self.simulator_mode:
            key_id = self.config.get("key_id") or os.getenv("KALSHI_KEY_ID")
            key_path = self.config.get("private_key_path", "keys/kalshi_private.pem")
            if not key_id:
                raise ValueError("No key_id in config or KALSHI_KEY_ID env var!")
            self.client = KalshiTraderClient(
                key_id=key_id,
                private_key_path=key_path,
                sandbox=self.sandbox,
            )
            # Test connection
            try:
                balance = self.client.get_balance()
                print(f"[CONNECTED] Balance: ${balance/100:.2f}")
            except Exception as e:
                print(f"[WARN] Could not connect: {e}")
        else:
            print("[SIMULATOR MODE] No real money at risk. Testing strategies only.")

        # Risk management
        self.risk = RiskManager(
            capital=self.config.get("capital", 500.0),
            max_daily_loss_pct=self.config.get("max_daily_loss_pct", 0.05),
            max_per_trade_pct=self.config.get("max_per_trade_pct", 0.02),
            max_total_exposure_pct=self.config.get("max_total_exposure_pct", 0.30),
            kelly_fraction=self.config.get("kelly_fraction", 0.125),
            min_edge_bps=self.config.get("min_edge_bps", 200),
            max_trades_per_day=self.config.get("max_trades_per_day", 20),
        )

        # Strategies
        self.strategies = {
            "fav_longshot": FavoriteLongshotStrategy(
                min_edge_bps=self.config.get("fav_longshot_min_edge", 300),
                max_price=self.config.get("fav_longshot_max_price", 20),
                min_price=self.config.get("fav_longshot_min_price", 80),
            ),
            "intra_arb": IntraMarketArbitrageStrategy(
                max_sum=self.config.get("arb_max_sum", 97),
                min_liquidity=self.config.get("arb_min_liquidity", 50),
            ),
            "momentum": MomentumStrategy(),
        }
        self.active_strategies = self.config.get("active_strategies", ["fav_longshot"])
        self.watchlist = set(self.config.get("watchlist", []))
        
        # Database
        self.db_path = self.config.get("db_path", "trades.db")
        self._init_db()
        
        # State
        self.running = False
        self.scan_interval = self.config.get("scan_interval_seconds", 15)
        self.cycle_count = 0

    def _load_config(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                side TEXT,
                action TEXT,
                price INTEGER,
                count INTEGER,
                cost REAL,
                strategy TEXT,
                edge_bps INTEGER,
                confidence REAL,
                reason TEXT,
                order_id TEXT,
                status TEXT,
                realized_pnl REAL,
                simulator INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                yes_bid INTEGER,
                yes_ask INTEGER,
                no_bid INTEGER,
                no_ask INTEGER,
                volume REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ticker TEXT,
                strategy TEXT,
                side TEXT,
                price INTEGER,
                edge_bps INTEGER,
                confidence REAL,
                reason TEXT,
                executed INTEGER,
                risk_reason TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                cycle INTEGER,
                markets_scanned INTEGER,
                signals_found INTEGER,
                trades_executed INTEGER,
                capital REAL,
                daily_pnl REAL,
                error TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _log_trade(self, **kwargs):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO trades (timestamp, ticker, side, action, price, count, cost,
                              strategy, edge_bps, confidence, reason, order_id, status,
                              realized_pnl, simulator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            kwargs.get("ticker"),
            kwargs.get("side"),
            kwargs.get("action"),
            kwargs.get("price"),
            kwargs.get("count"),
            kwargs.get("cost"),
            kwargs.get("strategy"),
            kwargs.get("edge_bps"),
            kwargs.get("confidence"),
            kwargs.get("reason"),
            kwargs.get("order_id"),
            kwargs.get("status"),
            kwargs.get("realized_pnl"),
            int(self.simulator_mode),
        ))
        conn.commit()
        conn.close()

    def _log_signal(self, signal, executed: bool, risk_reason: str = ""):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO signals (timestamp, ticker, strategy, side, price, edge_bps,
                               confidence, reason, executed, risk_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            signal.ticker,
            signal.strategy,
            signal.side,
            signal.price,
            signal.edge_bps,
            signal.confidence,
            signal.reason,
            int(executed),
            risk_reason,
        ))
        conn.commit()
        conn.close()

    def _log_health(self, markets_scanned: int, signals_found: int, trades_executed: int, error: str = ""):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        status = self.risk.get_status()
        c.execute("""
            INSERT INTO bot_health (timestamp, cycle, markets_scanned, signals_found,
                                   trades_executed, capital, daily_pnl, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            self.cycle_count,
            markets_scanned,
            signals_found,
            trades_executed,
            status["capital"],
            status["daily_pnl"],
            error,
        ))
        conn.commit()
        conn.close()

    def scan_markets(self):
        """Scan markets for trading opportunities."""
        markets_scanned = 0
        signals_found = 0
        trades_executed = 0
        error = ""

        try:
            if self.simulator_mode:
                # In simulator mode, we can't fetch real data
                # Return early - simulator handles its own data
                return 0, 0, 0, "simulator_mode"

            if not self.client:
                return 0, 0, 0, "no_client"

            # Fetch markets
            if self.watchlist:
                markets = []
                for ticker in self.watchlist:
                    try:
                        m = self.client.get_market(ticker)
                        markets.append(m)
                    except Exception as e:
                        print(f"[ERROR] Failed to fetch {ticker}: {e}")
            else:
                resp = self.client.get_markets(status="active", limit=100)
                markets = getattr(resp, 'markets', []) if hasattr(resp, 'markets') else []

            for market in markets:
                ticker = market.ticker if hasattr(market, 'ticker') else market.get("ticker")
                if not ticker:
                    continue
                markets_scanned += 1

                try:
                    ob = self.client.get_orderbook(ticker=ticker, depth=5)
                except Exception as e:
                    continue

                # Parse orderbook
                yes_bid = getattr(getattr(ob, 'yes_bid', None), 'price', 0) if hasattr(ob, 'yes_bid') and ob.yes_bid else 0
                yes_ask = getattr(getattr(ob, 'yes_ask', None), 'price', 0) if hasattr(ob, 'yes_ask') and ob.yes_ask else 0
                no_bid = getattr(getattr(ob, 'no_bid', None), 'price', 0) if hasattr(ob, 'no_bid') and ob.no_bid else 0
                no_ask = getattr(getattr(ob, 'no_ask', None), 'price', 0) if hasattr(ob, 'no_ask') and ob.no_ask else 0

                yes_mid = (yes_bid + yes_ask) // 2 if yes_bid and yes_ask else (yes_bid or yes_ask or 50)
                no_mid = (no_bid + no_ask) // 2 if no_bid and no_ask else (no_bid or no_ask or 50)
                volume = getattr(market, 'volume', 0) if hasattr(market, 'volume') else 0

                # Run strategies
                for strat_name in self.active_strategies:
                    strat = self.strategies.get(strat_name)
                    if not strat:
                        continue

                    signal = None
                    if strat_name == "fav_longshot":
                        signal = strat.analyze(ticker, yes_mid, no_mid, volume)
                    elif strat_name == "intra_arb":
                        signal = strat.analyze(ticker, yes_ask, no_ask)
                    elif strat_name == "momentum":
                        strat.on_price_update(ticker, yes_mid, time.time())
                        signal = strat.analyze(ticker)

                    if signal:
                        signals_found += 1
                        executed = self._execute_signal(signal, yes_ask if signal.side == "yes" else no_ask)
                        if executed:
                            trades_executed += 1

        except Exception as e:
            error = str(e)
            print(f"[SCAN ERROR] {error}")

        return markets_scanned, signals_found, trades_executed, error

    def _execute_signal(self, signal, best_ask: int) -> bool:
        """Execute a signal through risk manager."""
        allowed, count, reason = self.risk.check_trade_allowed(
            signal, current_price=best_ask, estimated_prob=0.5
        )

        self._log_signal(signal, allowed, reason)

        if not allowed:
            print(f"[RISK REJECT] {signal.ticker}: {reason}")
            return False

        if self.simulator_mode:
            cost = count * (best_ask / 100.0)
            self.risk.record_trade(signal.ticker, count, best_ask, signal.side)
            self._log_trade(
                ticker=signal.ticker,
                side=signal.side,
                action="buy",
                price=best_ask,
                count=count,
                cost=cost,
                strategy=signal.strategy,
                edge_bps=signal.edge_bps,
                confidence=signal.confidence,
                reason=signal.reason,
                order_id="SIM",
                status="simulated",
            )
            print(f"[SIM-EXEC] {signal.ticker}: {count} {signal.side} @ {best_ask}c, ${cost:.2f} | {signal.reason}")
            return True

        # Live execution
        try:
            resp = self.client.create_order(
                ticker=signal.ticker,
                side=signal.side,
                count=count,
                price=best_ask,
            )
            order_id = getattr(getattr(resp, 'order', None), 'order_id', 'unknown') if hasattr(resp, 'order') else 'unknown'
            cost = count * (best_ask / 100.0)
            self.risk.record_trade(signal.ticker, count, best_ask, signal.side)
            self._log_trade(
                ticker=signal.ticker,
                side=signal.side,
                action="buy",
                price=best_ask,
                count=count,
                cost=cost,
                strategy=signal.strategy,
                edge_bps=signal.edge_bps,
                confidence=signal.confidence,
                reason=signal.reason,
                order_id=order_id,
                status="filled",
            )
            print(f"[LIVE-EXEC] {signal.ticker}: {count} {signal.side} @ {best_ask}c, ${cost:.2f} | {signal.reason}")
            return True
        except Exception as e:
            print(f"[EXEC ERROR] {signal.ticker}: {e}")
            self._log_trade(
                ticker=signal.ticker,
                side=signal.side,
                action="buy",
                price=best_ask,
                count=count,
                cost=0,
                strategy=signal.strategy,
                edge_bps=signal.edge_bps,
                confidence=signal.confidence,
                reason=signal.reason,
                order_id="",
                status=f"error: {e}",
            )
            return False

    def run(self):
        """Main event loop."""
        self.running = True
        print(f"\n{'='*60}")
        print(f"  🤖 KALSHI BOT v2 STARTED")
        print(f"{'='*60}")
        print(f"  Mode: {'SIMULATOR' if self.simulator_mode else 'LIVE'}")
        print(f"  Environment: {'SANDBOX' if self.sandbox else 'PRODUCTION'}")
        print(f"  Capital: ${self.risk.capital:.2f}")
        print(f"  Strategies: {self.active_strategies}")
        print(f"  Watchlist: {self.watchlist or 'ALL MARKETS'}")
        print(f"  Scan Interval: {self.scan_interval}s")
        print(f"{'='*60}\n")

        while self.running:
            self.cycle_count += 1
            try:
                ms, sf, te, err = self.scan_markets()
                self._log_health(ms, sf, te, err)
                
                status = self.risk.get_status()
                print(f"[CYCLE {self.cycle_count}] Markets: {ms} | Signals: {sf} | Trades: {te} | "
                      f"Cap: ${status['capital']:.2f} | PnL: ${status['daily_pnl']:+.2f} | "
                      f"Exp: ${status['total_exposure']:.2f}")
                
                # Check circuit breaker
                if status['daily_pnl'] <= -self.risk.max_daily_loss:
                    print(f"\n🚨 CIRCUIT BREAKER TRIGGERED 🚨")
                    print(f"Daily loss limit reached: ${status['daily_pnl']:.2f}")
                    print(f"Bot pausing for remainder of session.")
                    self.running = False
                    break

            except KeyboardInterrupt:
                print("\n[INTERRUPT] Stopping bot...")
                self.running = False
                break
            except Exception as e:
                print(f"[FATAL LOOP ERROR] {e}")
                self._log_health(0, 0, 0, str(e))

            time.sleep(self.scan_interval)

        self._print_final_report()

    def _print_final_report(self):
        """Print final performance report."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            SELECT COUNT(*), SUM(cost), SUM(realized_pnl), AVG(edge_bps)
            FROM trades WHERE simulator=?
        """, (int(self.simulator_mode),))
        total, cost, pnl, edge = c.fetchone()
        
        c.execute("""
            SELECT strategy, COUNT(*), SUM(realized_pnl)
            FROM trades WHERE simulator=?
            GROUP BY strategy
        """, (int(self.simulator_mode),))
        by_strat = c.fetchall()
        
        conn.close()
        
        print(f"\n{'='*60}")
        print(f"  📊 FINAL REPORT")
        print(f"{'='*60}")
        print(f"  Mode: {'SIMULATOR' if self.simulator_mode else 'LIVE'}")
        print(f"  Total Trades: {total or 0}")
        print(f"  Total Cost: ${cost or 0:.2f}")
        print(f"  Total PnL: ${pnl or 0:+.2f}")
        print(f"  Avg Edge: {edge or 0:.0f} bps")
        if cost and cost > 0:
            roi = (pnl or 0) / cost * 100
            print(f"  ROI: {roi:+.2f}%")
        print(f"\n  By Strategy:")
        for strat, n, spnl in by_strat:
            print(f"    {strat}: {n} trades, ${spnl or 0:+.2f}")
        print(f"{'='*60}\n")

    def stop(self):
        self.running = False


if __name__ == "__main__":
    import sys
    
    # Allow --live flag to switch to live mode
    simulator = "--live" not in sys.argv
    
    # Quick config override for testing
    if not os.path.exists("config.json"):
        default_config = {
            "simulator_mode": simulator,
            "sandbox": True,
            "key_id": os.getenv("KALSHI_KEY_ID", ""),
            "private_key_path": "keys/kalshi_private.pem",
            "capital": 500.0,
            "max_daily_loss_pct": 0.05,
            "max_per_trade_pct": 0.02,
            "max_total_exposure_pct": 0.30,
            "kelly_fraction": 0.125,
            "min_edge_bps": 200,
            "max_trades_per_day": 20,
            "scan_interval_seconds": 15,
            "active_strategies": ["fav_longshot", "intra_arb"],
            "fav_longshot_min_edge": 300,
            "fav_longshot_max_price": 20,
            "fav_longshot_min_price": 80,
            "arb_max_sum": 97,
            "arb_min_liquidity": 50,
            "watchlist": [],
            "db_path": "trades.db"
        }
        with open("config.json", "w") as f:
            json.dump(default_config, f, indent=2)
        print("[INIT] Created default config.json")

    bot = KalshiBotV2("config.json")
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
