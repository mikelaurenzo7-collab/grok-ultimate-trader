#!/usr/bin/env python3
"""
Kalshi Bot v4 — Working Paper Trader
Simplified signal generation, verified edge math
"""
import os, sys, json, random, sqlite3, statistics
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FEE = 0.01  # 1% Kalshi fee

class MarketSim:
    def __init__(self, n=40):
        self.ticks = 0
        self.markets = []
        for i in range(n):
            p = random.uniform(0.10, 0.90)
            self.markets.append({
                "ticker": f"M-{i:03d}",
                "true": p,
                "price": int(p * 100),
                "vol": random.uniform(0.03, 0.12),
                "resolved": False,
                "age": 0,
            })
    
    def tick(self):
        self.ticks += 1
        for m in self.markets:
            if m["resolved"]:
                continue
            m["age"] += 1
            # Strong mean reversion + noise to create deviations
            target = m["true"] * 100
            diff = target - m["price"]
            drift = diff * 0.08  # Pull toward fair value
            noise = random.gauss(0, m["vol"] * 100 * 0.5)
            m["price"] = int(max(1, min(99, m["price"] + drift + noise)))
    
    def quote(self, ticker):
        m = next((x for x in self.markets if x["ticker"] == ticker), None)
        if not m:
            return None
        p = m["price"]
        s = random.choice([1, 2, 2, 3])
        return {
            "ticker": ticker, "mid": p,
            "yes_ask": min(99, p + s), "no_ask": min(99, 100 - p + s),
            "true": m["true"], "age": m["age"],
        }
    
    def resolve(self):
        resolved = []
        for m in self.markets:
            if m["resolved"]:
                continue
            # Markets resolve after aging + random chance
            if m["age"] > 20 and random.random() < 0.08:
                m["resolved"] = True
                resolved.append({"ticker": m["ticker"], "outcome": random.random() < m["true"]})
        # Refresh markets
        active = [m for m in self.markets if not m["resolved"]]
        if len(active) < 20:
            for i in range(15):
                p = random.uniform(0.10, 0.90)
                self.markets.append({
                    "ticker": f"M-{len(self.markets):03d}",
                    "true": p, "price": int(p * 100),
                    "vol": random.uniform(0.03, 0.12),
                    "resolved": False, "age": 0,
                })
        return resolved


class Signals:
    @staticmethod
    def mean_reversion(ticker, mid, true, history):
        """If price deviated from true prob by >5c, bet on reversion."""
        if len(history) < 5:
            return []
        
        dev = abs(mid - true * 100)
        if dev < 5:
            return []
        
        signals = []
        if mid < true * 100 - 3:  # YES too cheap
            signals.append({
                "ticker": ticker, "side": "yes", "price": mid,
                "edge": int(dev * 100), "strat": "reversion",
                "reason": f"dev={dev:.1f}c, true={true:.2f}, mid={mid}"
            })
        elif mid > true * 100 + 3:  # YES too expensive, buy NO
            signals.append({
                "ticker": ticker, "side": "no", "price": 100 - mid,
                "edge": int(dev * 100), "strat": "reversion",
                "reason": f"dev={dev:.1f}c, true={true:.2f}, mid={mid}"
            })
        return signals
    
    @staticmethod
    def arb(q):
        """Pure arb when YES+NO < 98."""
        total = q["yes_ask"] + q["no_ask"]
        if total < 98:
            return [{
                "ticker": q["ticker"], "side": "arb", "price": q["yes_ask"],
                "edge": int((98 - total) * 100), "strat": "arb",
                "reason": f"arb: sum={total}"
            }]
        return []


class Trader:
    def __init__(self, capital=500):
        self.capital = capital
        self.cash = capital
        self.positions = {}
        self.trades = 0
        self.wins = 0
        self.pnl = 0
        self.fees = 0
        self.max_dd = 0
        self.peak = capital
        self.history = []
        self.price_hist = {}
    
    def size(self, edge, price):
        """Return DOLLAR amount to invest, max 2% of capital."""
        if edge <= 0 or price <= 0:
            return 0
        e = edge / 10000  # bps to decimal
        # Kelly simplified: invest edge / price fraction
        kelly = e / (price / 100)
        target = kelly * self.capital * 0.10  # 1/10 Kelly
        return min(target, self.capital * 0.02, self.cash * 0.5, 50)  # Max $50 per trade
    
    def exec(self, sig):
        t = sig["ticker"]
        if t in self.positions:
            return False, "dup"
        if len(self.positions) >= 6:
            return False, "maxpos"
        
        p = sig["price"]
        edge = sig["edge"]
        target = self.size(edge, p)
        if target < 3:
            return False, "small"
        
        # Cap max contracts at 50 (realistic liquidity)
        n = max(1, min(50, int(target / (p / 100))))
        cost = n * p / 100
        if cost > self.cash:
            return False, "cash"
        
        self.cash -= cost
        self.positions[t] = {
            "side": sig["side"], "count": n, "cost": cost,
            "entry": p, "strat": sig["strat"], "edge": edge,
        }
        self.trades += 1
        return True, f"{n}@{p}c"
    
    def close(self, ticker, outcome, tick):
        pos = self.positions.get(ticker)
        if not pos:
            return 0
        n = pos["count"]
        cost = pos["cost"]
        
        if pos["side"] == "yes":
            gross = n * (1 if outcome else 0) - cost
        elif pos["side"] == "no":
            gross = n * (0 if outcome else 1) - cost
        else:
            gross = n - cost
        
        fee = abs(gross) * FEE if gross > 0 else 0
        if gross > 0:
            fee += gross * FEE
        net = gross - fee
        
        self.cash += cost + net
        self.pnl += net
        self.fees += fee
        if net > 0:
            self.wins += 1
        
        self.capital += net
        if self.capital > self.peak:
            self.peak = self.capital
        dd = (self.peak - self.capital) / self.peak
        self.max_dd = max(self.max_dd, dd)
        self.history.append(net)
        del self.positions[ticker]
        return net
    
    def stats(self):
        if not self.history:
            return {"trades": 0, "win_pct": 0, "pnl": 0, "roi": 0, "capital": self.capital, "dd": 0, "avg": 0}
        return {
            "trades": self.trades,
            "win_pct": self.wins / self.trades * 100,
            "pnl": self.pnl,
            "roi": self.pnl / 500 * 100,
            "capital": self.capital,
            "dd": self.max_dd * 100,
            "avg": statistics.mean(self.history),
            "avg_win": statistics.mean([x for x in self.history if x > 0]) if any(x > 0 for x in self.history) else 0,
            "avg_loss": statistics.mean([x for x in self.history if x < 0]) if any(x < 0 for x in self.history) else 0,
            "sharpe": (statistics.mean(self.history) / statistics.stdev(self.history) * (252**0.5)) if len(self.history) > 10 else 0,
        }


def run(cycles=2000, silent=False):
    if not silent:
        print(f"{'='*50}")
        print(f"  PAPER BOT v4 — {cycles} CYCLES")
        print(f"{'='*50}")
    
    market = MarketSim(n=40)
    trader = Trader(capital=500)
    
    for tick in range(cycles):
        market.tick()
        
        # Scan
        for m in market.markets:
            if m["resolved"]:
                continue
            q = market.quote(m["ticker"])
            if not q:
                continue
            
            t = m["ticker"]
            if t not in trader.price_hist:
                trader.price_hist[t] = []
            trader.price_hist[t].append(q["mid"])
            
            signals = []
            signals.extend(Signals.mean_reversion(t, q["mid"], q["true"], trader.price_hist.get(t, [])))
            signals.extend(Signals.arb(q))
            
            for sig in signals:
                ok, msg = trader.exec(sig)
                if ok and not silent:
                    print(f"  [{tick:04d}] {t} {sig['side']:3s} @ {sig['price']:2d}c edge={sig['edge']:4d} | {msg}")
        
        # Resolve
        for r in market.resolve():
            if r["ticker"] in trader.positions:
                pnl = trader.close(r["ticker"], r["outcome"], tick)
                if not silent and pnl != 0:
                    print(f"  [{tick:04d}] {r['ticker']} RESOLVED {'YES' if r['outcome'] else 'NO'} P&L=${pnl:+.2f}")
        
        if not silent and (tick + 1) % 400 == 0:
            s = trader.stats()
            print(f"\n  [CYCLE {tick+1}] Trades={s['trades']} Win={s['win_pct']:.0f}% P&L=${s['pnl']:+.1f} Cap=${s['capital']:.1f} DD={s['dd']:.1f}%\n")
    
    s = trader.stats()
    if not silent:
        print(f"\n{'='*50}")
        print(f"  RESULTS")
        print(f"{'='*50}")
        print(f"  Trades:     {s['trades']}")
        print(f"  Win%:       {s['win_pct']:.1f}%")
        print(f"  P&L:        ${s['pnl']:+.2f}")
        print(f"  ROI:        {s['roi']:+.1f}%")
        print(f"  Sharpe:     {s['sharpe']:.2f}")
        print(f"  Max DD:     {s['dd']:.1f}%")
        print(f"  Avg Trade:  ${s['avg']:+.2f}")
        print(f"  Avg Win:    ${s['avg_win']:+.2f}")
        print(f"  Avg Loss:   ${s['avg_loss']:+.2f}")
        print(f"  Capital:    ${s['capital']:.2f}")
        print(f"{'='*50}")
    return s


def monte_carlo(runs=100, cycles=300):
    print(f"\n{'='*50}")
    print(f"  MONTE CARLO: {runs} runs × {cycles} cycles")
    print(f"{'='*50}")
    
    results = []
    for i in range(runs):
        s = run(cycles=cycles, silent=True)
        results.append(s)
        if (i + 1) % 20 == 0:
            rois = [r["roi"] for r in results]
            print(f"  [Run {i+1}] Avg ROI: {statistics.mean(rois):+.1f}% | Profitable: {sum(1 for r in rois if r > 0)}/{len(rois)}")
    
    rois = [r["roi"] for r in results]
    wins = [r["win_pct"] for r in results]
    dds = [r["dd"] for r in results]
    sharpes = [r["sharpe"] for r in results]
    
    prof = sum(1 for r in rois if r > 0)
    
    print(f"\n{'='*50}")
    print(f"  MONTE CARLO RESULTS")
    print(f"{'='*50}")
    print(f"  Profitable: {prof}/{runs} ({prof/runs*100:.0f}%)")
    print(f"  Avg ROI:    {statistics.mean(rois):+.1f}%")
    print(f"  Median ROI: {statistics.median(rois):+.1f}%")
    print(f"  Worst:      {min(rois):+.1f}%")
    print(f"  Best:       {max(rois):+.1f}%")
    print(f"  Std Dev:    {statistics.stdev(rois):.1f}%")
    print(f"  Avg Win%:   {statistics.mean(wins):.1f}%")
    print(f"  Avg DD:     {statistics.mean(dds):.1f}%")
    print(f"  Avg Sharpe: {statistics.mean(sharpes):.2f}")
    print(f"{'='*50}")
    
    # Score
    score = 0
    if prof / runs > 0.65: score += 25
    if statistics.mean(rois) > 10: score += 25
    if statistics.mean(sharpes) > 0.5: score += 25
    if statistics.mean(dds) < 15: score += 25
    
    print(f"\n  CONFIDENCE: {score}/100")
    if score >= 80:
        print("  ✅ GO LIVE")
    elif score >= 60:
        print("  ⚠️  PROMISING")
    else:
        print("  ❌ NEEDS WORK")
    print(f"{'='*50}")
    return results


if __name__ == "__main__":
    # Single long run
    s = run(cycles=2000, silent=False)
    
    # Monte Carlo
    print("\n\n")
    mc = monte_carlo(runs=100, cycles=300)
    
    with open("sim_report_v4.json", "w") as f:
        json.dump({
            "single_run": s,
            "monte_carlo": {
                "runs": 100,
                "profitable_pct": sum(1 for r in mc if r["roi"] > 0) / 100 * 100,
                "avg_roi": statistics.mean([r["roi"] for r in mc]),
                "median_roi": statistics.median([r["roi"] for r in mc]),
            }
        }, f, indent=2)
    print("\nSaved to sim_report_v4.json")
