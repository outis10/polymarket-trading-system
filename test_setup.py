"""
Example script for testing basic functionality
Run this to verify your setup is working correctly
"""
import sys
import logging
from config.settings import settings
from core.client_wrapper import PolymarketClient


def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def test_connection(client: PolymarketClient, logger: logging.Logger):
    """Test connection to Polymarket"""
    logger.info("Testing connection to Polymarket...")
    
    try:
        balance = client.get_balance()
        if balance is not None:
            logger.info(f"✓ Connection successful!")
            logger.info(f"✓ Account balance: ${balance:.2f} USDC")
            return True
        else:
            logger.error("✗ Could not retrieve balance")
            return False
    except Exception as e:
        logger.error(f"✗ Connection failed: {e}")
        return False


def test_market_data(client: PolymarketClient, logger: logging.Logger):
    """Test retrieving market data"""
    logger.info("\nTesting market data retrieval...")
    
    try:
        # Get active markets
        markets = client.get_markets(closed=False, active=True)
        
        if not markets:
            logger.warning("⚠ No active markets found")
            return False
        
        logger.info(f"✓ Retrieved {len(markets)} active markets")
        
        # Display first 3 markets
        logger.info("\nSample markets:")
        for i, market in enumerate(markets[:3]):
            logger.info(f"\n  Market {i+1}:")
            logger.info(f"    Question: {market.get('question', 'N/A')}")
            logger.info(f"    Condition ID: {market.get('condition_id', 'N/A')}")
            logger.info(f"    Active: {market.get('active', 'N/A')}")
        
        # Test order book for first market
        if markets and markets[0].get('tokens'):
            first_token = markets[0]['tokens'][0]
            token_id = first_token.get('token_id')
            
            if token_id:
                logger.info(f"\nTesting order book for token {token_id[:8]}...")
                orderbook = client.get_order_book(token_id)
                
                if orderbook:
                    bids = orderbook.get('bids', [])
                    asks = orderbook.get('asks', [])
                    logger.info(f"✓ Order book retrieved")
                    logger.info(f"  Bids: {len(bids)}, Asks: {len(asks)}")
                    
                    if bids:
                        logger.info(f"  Best bid: ${float(bids[0]['price']):.4f}")
                    if asks:
                        logger.info(f"  Best ask: ${float(asks[0]['price']):.4f}")
                else:
                    logger.warning("⚠ Could not retrieve order book")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Market data test failed: {e}")
        return False


def test_positions(client: PolymarketClient, logger: logging.Logger):
    """Test retrieving positions"""
    logger.info("\nTesting positions retrieval...")
    
    try:
        positions = client.get_positions()
        logger.info(f"✓ Current open positions: {len(positions)}")
        
        if positions:
            logger.info("\nOpen positions:")
            for pos in positions[:3]:  # Show first 3
                logger.info(f"  - Token: {pos.get('token_id', 'N/A')[:8]}...")
                logger.info(f"    Size: {pos.get('size', 'N/A')}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Positions test failed: {e}")
        return False


def main():
    """Run all tests"""
    logger = setup_logging()
    
    print("""
    ╔═══════════════════════════════════════════╗
    ║   Polymarket Trading System - Test       ║
    ║   Basic Functionality Check              ║
    ╚═══════════════════════════════════════════╝
    """)
    
    # Validate settings
    logger.info("Validating configuration...")
    try:
        settings.validate()
        logger.info("✓ Configuration valid")
        logger.info(f"✓ Mode: {'TESTNET' if settings.polymarket.use_testnet else 'MAINNET'}")
    except Exception as e:
        logger.error(f"✗ Configuration invalid: {e}")
        logger.error("\nPlease check your .env file and ensure all required variables are set.")
        sys.exit(1)
    
    # Initialize client
    logger.info("\nInitializing Polymarket client...")
    try:
        client = PolymarketClient(settings.polymarket)
        logger.info("✓ Client initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize client: {e}")
        sys.exit(1)
    
    # Run tests
    results = []
    
    results.append(("Connection Test", test_connection(client, logger)))
    results.append(("Market Data Test", test_market_data(client, logger)))
    results.append(("Positions Test", test_positions(client, logger)))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")
    
    print("="*60)
    print(f"Results: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n✓ All tests passed! Your setup is ready.")
        print("You can now run 'python main.py' to start the trading bot.")
    else:
        print("\n⚠ Some tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
