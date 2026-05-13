#!/usr/bin/env python3
"""
Kalshi API Connection Test
Run this BEFORE going live. It checks auth, balance, and market data.
"""
import os, sys

# Load env
key_id = os.getenv("KALSHI_KEY_ID", "").strip()
key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "keys/kalshi_private.pem")
sandbox = os.getenv("KALSHI_SANDBOX", "true").lower() == "true"

print(f"{'='*50}")
print(f"  KALSHI CONNECTION TEST")
print(f"{'='*50}")
print(f"  Key ID: {key_id[:20]}...")
print(f"  Key Path: {key_path}")
print(f"  Mode: {'SANDBOX' if sandbox else 'PRODUCTION'}")
print(f"{'='*50}\n")

# Check 1: Key ID exists
if not key_id:
    print("❌ FAIL: KALSHI_KEY_ID is empty!")
    print("   Fix: Edit .env and add your Key ID")
    sys.exit(1)
print("✅ Key ID found")

# Check 2: Private key file exists
if not os.path.exists(key_path):
    print(f"❌ FAIL: Private key not found at {key_path}")
    print("   Fix: Run: openssl genrsa -out keys/kalshi_private.pem 2048")
    sys.exit(1)
print("✅ Private key file exists")

# Check 3: Try importing SDK
try:
    from kalshi_client_v2 import KalshiTraderClient
    print("✅ Kalshi SDK imported")
except Exception as e:
    print(f"❌ FAIL: Could not import SDK: {e}")
    print("   Fix: python3 -m pip install kalshi-python-sync")
    sys.exit(1)

# Check 4: Connect and get balance
print(f"\n🌐 Connecting to Kalshi...\n")
try:
    client = KalshiTraderClient(
        key_id=key_id,
        private_key_path=key_path,
        sandbox=sandbox,
    )
    bal = client.get_balance()
    balance = bal.balance if hasattr(bal, 'balance') else 0
    print(f"✅ CONNECTED!")
    print(f"   Balance: ${balance/100:.2f}")
    
    # Check 5: Get exchange status
    status = client.get_exchange_status()
    print(f"   Exchange: {status}")
    
    # Check 6: List 3 markets
    markets = client.get_markets(status="active", limit=3)
    market_list = getattr(markets, 'markets', []) if hasattr(markets, 'markets') else []
    print(f"   Markets: {len(market_list)} active")
    for m in market_list[:3]:
        ticker = m.ticker if hasattr(m, 'ticker') else m.get('ticker', '?')
        print(f"     - {ticker}")
    
    print(f"\n{'='*50}")
    print(f"  🎉 ALL CHECKS PASSED — READY FOR LIVE TRADING!")
    print(f"{'='*50}")
    
except Exception as e:
    print(f"❌ CONNECTION FAILED: {e}")
    print(f"\nCommon fixes:")
    print(f"   1. Key ID is wrong — copy it EXACTLY from Kalshi dashboard")
    print(f"   2. Private key doesn't match public key uploaded to Kalshi")
    print(f"   3. Using sandbox key on production (or vice versa)")
    print(f"   4. Network / firewall blocking port 443")
    sys.exit(1)
