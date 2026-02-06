#!/usr/bin/env python3
"""Verify wallet configuration."""
from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv()

private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
funder = os.getenv("POLYMARKET_FUNDER", "")

if not private_key:
    print("ERROR: POLYMARKET_PRIVATE_KEY not set")
    exit(1)

# Derive address from private key
account = Account.from_key(private_key)
derived_address = account.address

print(f"Private key address: {derived_address}")
print(f"Funder in .env:      {funder}")
print()

if derived_address.lower() == funder.lower():
    print("OK: Addresses match!")
else:
    print("ERROR: Addresses DO NOT match!")
    print("Your POLYMARKET_FUNDER should be:", derived_address)
