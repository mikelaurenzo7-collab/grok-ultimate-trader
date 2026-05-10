import pandas as pd
import numpy as np

class KalshiSportsStrategy:
    def __init__(self, client, kelly_frac=0.32, min_net_edge=0.065):
        self.client = client
        self.kelly_frac = kelly_frac
        self.min_net_edge = min_net_edge
    
    def maker_fee(self, p: float) -> float:
        return 0.0175 * p * (1 - p)
    
    def score_market(self, market):
        try:
            yes_p = market.get('yes_price', 50) / 100.0
            volume = market.get('volume_24h', 0) or market.get('volume', 0)
            ticker = market['ticker']
            
            edge = 0.0
            if yes_p <= 0.22:
                edge += 0.048
            elif yes_p >= 0.78:
                edge += 0.038
            
            if volume > 80000:
                edge += 0.028
            
            if any(x in ticker.lower() for x in ['live', 'prop', 'player']):
                edge += 0.022
            
            net_edge = edge - self.maker_fee(yes_p) - 0.006
            
            suggested_side = "yes" if yes_p < 0.48 else "no"
            
            return {
                'ticker': ticker,
                'yes_price': yes_p,
                'net_edge': max(0.0, net_edge),
                'suggested_side': suggested_side,
                'score': net_edge * (volume / 100000),
                'volume': volume
            }
        except:
            return {'net_edge': -1}
    
    def kelly_size(self, net_edge: float, bankroll: float, price: float):
        if net_edge < self.min_net_edge:
            return 0
        bet_frac = min(0.11, net_edge * 2.1 * self.kelly_frac)
        dollars_risk = bankroll * bet_frac
        contracts = max(1, int(dollars_risk // (price * 100)))
        return contracts
    
    def run_scan(self, bankroll: float):
        markets = self.client.get_open_markets(min_volume=20000)
        opps = []
        for m in markets[:100]:
            score = self.score_market(m)
            if score.get('net_edge', 0) > self.min_net_edge:
                size = self.kelly_size(score['net_edge'], bankroll, score['yes_price'])
                if size > 0:
                    opps.append({**score, 'size': size})
        
        opps.sort(key=lambda x: x.get('score', 0), reverse=True)
        return opps[:8]