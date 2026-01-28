"""
Main entry point for Polymarket Trading System
"""
import logging
import time
import signal
import sys
import json
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any

from config.settings import settings
from core.client_wrapper import PolymarketClient
from risk.position_manager import PositionManager
from execution.order_executor import OrderExecutor

# Gamma API para datos de mercados (más eficiente para exploración)
GAMMA_API = "https://gamma-api.polymarket.com"


class TradingBot:
    """Main trading bot orchestrator"""
    
    def __init__(self):
        """Initialize the trading bot"""
        self.logger = self._setup_logging()
        self.running = False
        
        # Initialize components
        self.logger.info("Initializing Polymarket Trading System...")
        
        try:
            # Validate settings
            settings.validate()
            
            # Initialize Polymarket client
            self.client = PolymarketClient(settings.polymarket)
            
            # Initialize position manager
            self.position_manager = PositionManager(
                max_position_size=settings.trading.max_position_size,
                max_total_exposure=settings.trading.max_total_exposure,
                stop_loss_pct=settings.trading.stop_loss_pct,
                take_profit_pct=settings.trading.take_profit_pct
            )
            
            # Initialize order executor
            self.executor = OrderExecutor(self.client, self.position_manager)
            
            self.logger.info("✓ All components initialized successfully")
            self.logger.info(f"✓ Mode: {'TESTNET' if settings.polymarket.use_testnet else 'MAINNET'}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize bot: {e}")
            sys.exit(1)
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # File handler
        file_handler = logging.FileHandler('trading_bot.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, settings.log_level))
        console_handler.setFormatter(logging.Formatter(log_format))
        
        # Root logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logging.getLogger(__name__)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info("\n⚠️  Shutdown signal received. Stopping bot...")
        self.running = False
    
    def display_status(self):
        """Display current bot status"""
        # Get account balance
        balance = self.client.get_balance()
        
        # Get risk metrics
        risk_metrics = self.position_manager.get_risk_metrics()
        
        self.logger.info("=" * 60)
        self.logger.info(f"Bot Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        self.logger.info(f"Balance: ${balance:.2f} USDC" if balance else "Balance: N/A")
        self.logger.info(f"Open Positions: {risk_metrics['total_positions']}")
        self.logger.info(f"Total Exposure: ${risk_metrics['total_exposure']:.2f}")
        self.logger.info(f"Total P&L: ${risk_metrics['total_pnl']:.2f}")
        self.logger.info(
            f"Exposure Utilization: {risk_metrics['exposure_utilization']:.1%}"
        )
        self.logger.info("=" * 60)
    
    def monitor_positions(self):
        """Monitor and manage open positions"""
        if not self.position_manager.get_all_positions():
            return
        
        # Update all position prices
        self.executor.update_all_position_prices()
        
        # Check and close positions that hit stop-loss or take-profit
        results = self.executor.check_and_close_positions()
        
        if results['closed'] > 0:
            self.logger.info(f"✓ Closed {results['closed']} positions")
            for detail in results['details']:
                if detail['success']:
                    self.logger.info(
                        f"  - {detail['token_id'][:8]}... | "
                        f"Reason: {detail['reason']} | "
                        f"P&L: ${detail['pnl']:.2f}"
                    )
    
    def get_active_markets_gamma(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get active markets from Gamma API (más eficiente para exploración)

        Args:
            limit: Número máximo de mercados a obtener

        Returns:
            Lista de mercados activos
        """
        try:
            params = {
                'active': 'true',
                'closed': 'false',
                'limit': limit
            }
            response = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error fetching markets from Gamma API: {e}")
            return []

    def analyze_market_opportunity(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analiza un mercado para detectar oportunidades

        Args:
            market: Datos del mercado de Gamma API

        Returns:
            Diccionario con oportunidad detectada o None
        """
        try:
            question = market.get('question', 'N/A')

            # Parsear outcomes y precios
            outcomes_str = market.get('outcomes', '[]')
            prices_str = market.get('outcomePrices', '[]')
            token_ids_str = market.get('clobTokenIds', '[]')

            outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
            prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
            token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str

            if not outcomes or not prices or not token_ids:
                return None

            # Métricas del mercado
            volume_24h = float(market.get('volume24hr', 0))
            liquidity = float(market.get('liquidityClob', 0))
            spread = float(market.get('spread', 1))

            # Criterios de oportunidad (AJUSTA SEGÚN TU ESTRATEGIA)
            # Por ahora solo detectamos, NO ejecutamos trades

            opportunities = []

            for i, outcome in enumerate(outcomes):
                if i >= len(prices) or i >= len(token_ids):
                    continue

                price = float(prices[i])
                token_id = token_ids[i]

                # Ejemplo de criterios de oportunidad:
                # 1. Precio muy bajo (posible subestimación)
                if price < 0.10 and volume_24h > 1000:
                    opportunities.append({
                        'type': 'LOW_PRICE',
                        'outcome': outcome,
                        'price': price,
                        'token_id': token_id,
                        'reason': f"Precio bajo (${price:.4f}) con volumen decente"
                    })

                # 2. Precio muy alto (casi seguro según el mercado)
                elif price > 0.90 and volume_24h > 1000:
                    opportunities.append({
                        'type': 'HIGH_CONFIDENCE',
                        'outcome': outcome,
                        'price': price,
                        'token_id': token_id,
                        'reason': f"Alta confianza del mercado ({price*100:.1f}%)"
                    })

            if opportunities:
                return {
                    'question': question,
                    'volume_24h': volume_24h,
                    'liquidity': liquidity,
                    'spread': spread,
                    'opportunities': opportunities
                }

            return None

        except Exception as e:
            self.logger.debug(f"Error analyzing market: {e}")
            return None

    def scan_markets(self):
        """
        Scan markets for opportunities using Gamma API

        Usa Gamma API para obtener mercados activos y analiza oportunidades.
        Por ahora solo hace logging - no ejecuta trades automáticamente.
        """
        try:
            # Obtener mercados activos de Gamma API
            markets = self.get_active_markets_gamma(limit=30)

            if not markets:
                self.logger.warning("No active markets found from Gamma API")
                return

            self.logger.info(f"📊 Scanning {len(markets)} active markets...")

            # Analizar cada mercado
            opportunities_found = 0

            for market in markets:
                opportunity = self.analyze_market_opportunity(market)

                if opportunity:
                    opportunities_found += 1
                    question = opportunity['question'][:50]

                    self.logger.info(f"🔔 Opportunity in: {question}...")
                    self.logger.info(f"   Volume 24h: ${opportunity['volume_24h']:,.2f}")
                    self.logger.info(f"   Liquidity: ${opportunity['liquidity']:,.2f}")

                    for opp in opportunity['opportunities']:
                        self.logger.info(
                            f"   → {opp['outcome']}: ${opp['price']:.4f} "
                            f"({opp['type']}) - {opp['reason']}"
                        )

                    # ========================================
                    # AQUÍ IMPLEMENTARÍAS TU LÓGICA DE TRADING
                    # ========================================
                    # Ejemplo (descomenta cuando estés listo):
                    #
                    # if opp['type'] == 'LOW_PRICE' and opp['price'] < 0.05:
                    #     signal = Signal(
                    #         action=SignalAction.BUY,
                    #         token_id=opp['token_id'],
                    #         price=opp['price'],
                    #         size=settings.trading.max_position_size,
                    #         confidence=0.7,
                    #         reason=opp['reason']
                    #     )
                    #     result = self.executor.execute_signal(signal)
                    #     self.logger.info(f"   Trade result: {result}")

            if opportunities_found == 0:
                self.logger.debug("No opportunities found in this scan")
            else:
                self.logger.info(f"✓ Found {opportunities_found} potential opportunities")

        except Exception as e:
            self.logger.error(f"Error scanning markets: {e}")
    
    def run(self):
        """Main bot loop"""
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.running = True
        self.logger.info("🚀 Trading bot started!")
        self.logger.info("Press Ctrl+C to stop")
        
        iteration = 0
        status_interval = 10  # Display status every 10 iterations
        
        try:
            while self.running:
                iteration += 1
                
                try:
                    # Display status periodically
                    if iteration % status_interval == 0:
                        self.display_status()
                    
                    # Monitor open positions
                    self.monitor_positions()
                    
                    # Scan for new opportunities
                    self.scan_markets()
                    
                    # Sleep before next iteration (60 seconds)
                    time.sleep(60)
                    
                except KeyboardInterrupt:
                    # This will be caught by signal handler
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(10)  # Brief pause before retrying
        
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cleanup and shutdown"""
        self.logger.info("🛑 Shutting down...")
        
        # Display final status
        self.display_status()
        
        # Optional: Close all positions on shutdown (uncomment if desired)
        # self.logger.warning("Closing all open positions...")
        # results = self.executor.emergency_close_all()
        # self.logger.info(f"Closed {results['closed']}/{results['total']} positions")
        
        self.logger.info("✓ Bot stopped successfully")


def main():
    """Entry point"""
    print("""
    ╔═══════════════════════════════════════════╗
    ║   Polymarket Trading System               ║
    ║   Version 1.0.0                          ║
    ╚═══════════════════════════════════════════╝
    """)
    
    # Create and run bot
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
