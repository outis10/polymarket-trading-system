#!/usr/bin/env python3
"""
Setup allowances for Polymarket trading.
This approves USDC spending for the Polymarket exchange.
"""
from py_clob_client.client import ClobClient
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder = os.getenv("POLYMARKET_FUNDER", "")
    chain_id = int(os.getenv("CHAIN_ID", "137"))
    signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    use_testnet = os.getenv("USE_TESTNET", "false").lower() == "true"

    host = "https://clob-testnet.polymarket.com" if use_testnet else "https://clob.polymarket.com"

    print(f"Network: {'Testnet' if use_testnet else 'Mainnet'}")
    print(f"Chain ID: {chain_id}")
    print(f"Funder: {funder}")
    print()

    # Create client
    client = ClobClient(
        host,
        key=private_key,
        chain_id=chain_id,
        signature_type=signature_type,
        funder=funder
    )

    # Derive API credentials
    print("Deriving API credentials...")
    api_creds = client.create_or_derive_api_creds()
    client.set_api_creds(api_creds)
    print("OK")
    print()

    # Check current allowance
    print("Checking current allowance...")
    try:
        allowance = client.get_balance_allowance()
        print(f"Current allowance: {allowance}")
    except Exception as e:
        print(f"Could not get allowance: {e}")
        allowance = None
    print()

    # Set max allowance
    print("Setting up allowance...")
    print("This will send a transaction to approve USDC spending.")
    print()

    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    try:
        # Update allowance to maximum
        result = client.update_balance_allowance()
        print(f"Allowance updated: {result}")
        print()
        print("SUCCESS! You can now trade via the API.")
    except Exception as e:
        print(f"Error setting allowance: {e}")
        print()
        print("Alternative: Go to https://polymarket.com and make a small trade")
        print("from the website. This will prompt MetaMask to approve the contracts.")

if __name__ == "__main__":
    main()
