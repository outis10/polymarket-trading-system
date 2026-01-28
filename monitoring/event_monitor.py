#!/usr/bin/env python3
"""
Event Monitor - Real-time monitoring for Polymarket events
===========================================================
Handles fetching and updating data from Polymarket API.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import yaml
import os

# Setup logging
logger = logging.getLogger(__name__)


@dataclass
class TokenPrices:
    """Current prices for YES/NO tokens"""
    yes_bid: float = 0.0
    yes_ask: float = 0.0
    yes_mid: float = 0.0
    no_bid: float = 0.0
    no_ask: float = 0.0
    no_mid: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EventState:
    """Current state of a monitored event"""
    event_id: str
    name: str
    description: str
    condition_id: str
    yes_token_id: str
    no_token_id: str
    prices: TokenPrices = field(default_factory=TokenPrices)
    price_history: List[Dict] = field(default_factory=list)
    is_active: bool = True
    last_update: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    last_error: Optional[str] = None


class EventMonitor:
    """
    Monitors multiple Polymarket events in real-time.

    Usage:
        monitor = EventMonitor()
        await monitor.load_events_from_config()
        await monitor.start_monitoring()
    """

    def __init__(self, client=None):
        """
        Initialize the event monitor.

        Args:
            client: Optional PolymarketClient instance. If not provided,
                   will create one when needed.
        """
        self.client = client
        self.events: Dict[str, EventState] = {}
        self.is_running = False
        self._update_task: Optional[asyncio.Task] = None
        self.update_interval = 5  # seconds
        self.max_history_length = 500
        self.callbacks: List[callable] = []

    def load_events_from_config(self, config_path: Optional[str] = None) -> None:
        """
        Load events from YAML configuration file.

        Args:
            config_path: Path to config file. Defaults to config/events.yaml
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config',
                'events.yaml'
            )

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            events_config = config.get('events', [])

            for event_config in events_config:
                # Skip events without token IDs
                tokens = event_config.get('tokens', {})
                if not tokens.get('yes') or not tokens.get('no'):
                    logger.warning(f"Skipping event '{event_config.get('name')}': missing token IDs")
                    continue

                event_id = event_config['name'].lower().replace(' ', '_')

                self.events[event_id] = EventState(
                    event_id=event_id,
                    name=event_config['name'],
                    description=event_config.get('description', ''),
                    condition_id=event_config.get('condition_id', ''),
                    yes_token_id=tokens['yes'],
                    no_token_id=tokens['no']
                )

                logger.info(f"Loaded event: {event_config['name']}")

            logger.info(f"Loaded {len(self.events)} events from config")

        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config file: {e}")
            raise

    def add_event(
        self,
        name: str,
        yes_token_id: str,
        no_token_id: str,
        description: str = "",
        condition_id: str = ""
    ) -> str:
        """
        Add an event to monitor programmatically.

        Args:
            name: Event name
            yes_token_id: Token ID for YES outcome
            no_token_id: Token ID for NO outcome
            description: Optional description
            condition_id: Optional condition ID

        Returns:
            Event ID
        """
        event_id = name.lower().replace(' ', '_')

        self.events[event_id] = EventState(
            event_id=event_id,
            name=name,
            description=description,
            condition_id=condition_id,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id
        )

        logger.info(f"Added event: {name}")
        return event_id

    def remove_event(self, event_id: str) -> bool:
        """
        Remove an event from monitoring.

        Args:
            event_id: Event ID to remove

        Returns:
            True if removed, False if not found
        """
        if event_id in self.events:
            del self.events[event_id]
            logger.info(f"Removed event: {event_id}")
            return True
        return False

    async def update_event_prices(self, event_id: str) -> Optional[TokenPrices]:
        """
        Fetch and update prices for a single event.

        Args:
            event_id: Event ID to update

        Returns:
            TokenPrices or None if error
        """
        if event_id not in self.events:
            logger.error(f"Event not found: {event_id}")
            return None

        event = self.events[event_id]

        if not self.client:
            logger.warning("No client configured - cannot fetch prices")
            return None

        try:
            # Fetch order books for YES and NO tokens
            yes_orderbook = self.client.get_order_book(event.yes_token_id)
            no_orderbook = self.client.get_order_book(event.no_token_id)

            if not yes_orderbook or not no_orderbook:
                raise Exception("Failed to fetch order books")

            # Extract prices
            prices = TokenPrices(
                yes_bid=float(yes_orderbook['bids'][0]['price']) if yes_orderbook.get('bids') else 0,
                yes_ask=float(yes_orderbook['asks'][0]['price']) if yes_orderbook.get('asks') else 0,
                no_bid=float(no_orderbook['bids'][0]['price']) if no_orderbook.get('bids') else 0,
                no_ask=float(no_orderbook['asks'][0]['price']) if no_orderbook.get('asks') else 0,
                timestamp=datetime.now()
            )

            # Calculate mid prices
            prices.yes_mid = (prices.yes_bid + prices.yes_ask) / 2 if prices.yes_bid and prices.yes_ask else 0
            prices.no_mid = (prices.no_bid + prices.no_ask) / 2 if prices.no_bid and prices.no_ask else 0

            # Update event state
            event.prices = prices
            event.last_update = datetime.now()
            event.error_count = 0
            event.last_error = None

            # Add to history
            event.price_history.append({
                'timestamp': prices.timestamp,
                'yes_bid': prices.yes_bid,
                'yes_ask': prices.yes_ask,
                'yes_mid': prices.yes_mid,
                'no_bid': prices.no_bid,
                'no_ask': prices.no_ask,
                'no_mid': prices.no_mid
            })

            # Trim history
            if len(event.price_history) > self.max_history_length:
                event.price_history = event.price_history[-self.max_history_length:]

            logger.debug(f"Updated prices for {event.name}: YES={prices.yes_mid:.3f}, NO={prices.no_mid:.3f}")

            return prices

        except Exception as e:
            event.error_count += 1
            event.last_error = str(e)
            logger.error(f"Error updating prices for {event.name}: {e}")
            return None

    async def update_all_events(self) -> Dict[str, Optional[TokenPrices]]:
        """
        Update prices for all monitored events.

        Returns:
            Dictionary of event_id -> TokenPrices (or None if error)
        """
        results = {}

        for event_id in self.events:
            results[event_id] = await self.update_event_prices(event_id)
            # Small delay between requests to avoid rate limiting
            await asyncio.sleep(0.1)

        # Notify callbacks
        for callback in self.callbacks:
            try:
                callback(results)
            except Exception as e:
                logger.error(f"Error in callback: {e}")

        return results

    async def _monitoring_loop(self):
        """Internal monitoring loop."""
        logger.info("Starting monitoring loop")

        while self.is_running:
            try:
                await self.update_all_events()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.update_interval)

        logger.info("Monitoring loop stopped")

    async def start_monitoring(self):
        """Start the monitoring loop."""
        if self.is_running:
            logger.warning("Monitoring already running")
            return

        self.is_running = True
        self._update_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Monitoring started")

    async def stop_monitoring(self):
        """Stop the monitoring loop."""
        self.is_running = False

        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

        logger.info("Monitoring stopped")

    def on_update(self, callback: callable):
        """
        Register a callback to be called when prices update.

        Args:
            callback: Function that receives Dict[str, TokenPrices]
        """
        self.callbacks.append(callback)

    def get_event(self, event_id: str) -> Optional[EventState]:
        """Get event state by ID."""
        return self.events.get(event_id)

    def get_all_events(self) -> Dict[str, EventState]:
        """Get all monitored events."""
        return self.events.copy()

    def get_event_summary(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a summary of an event's current state.

        Returns:
            Dictionary with event summary or None if not found
        """
        event = self.events.get(event_id)
        if not event:
            return None

        return {
            'name': event.name,
            'description': event.description,
            'yes_price': event.prices.yes_mid,
            'no_price': event.prices.no_mid,
            'yes_bid': event.prices.yes_bid,
            'yes_ask': event.prices.yes_ask,
            'no_bid': event.prices.no_bid,
            'no_ask': event.prices.no_ask,
            'last_update': event.last_update.isoformat(),
            'is_active': event.is_active,
            'error_count': event.error_count,
            'last_error': event.last_error,
            'history_length': len(event.price_history)
        }


# =============================================================================
# STANDALONE USAGE
# =============================================================================

async def main():
    """Example usage of EventMonitor."""
    from config.settings import Settings, PolymarketConfig
    from core.client_wrapper import PolymarketClient

    # Initialize client
    settings = Settings()
    client = PolymarketClient(settings.polymarket)

    # Create monitor
    monitor = EventMonitor(client)

    # Load events from config
    monitor.load_events_from_config()

    # Register callback
    def on_price_update(prices):
        for event_id, price in prices.items():
            if price:
                print(f"{event_id}: YES={price.yes_mid:.3f}, NO={price.no_mid:.3f}")

    monitor.on_update(on_price_update)

    # Start monitoring
    await monitor.start_monitoring()

    # Run for 60 seconds
    try:
        await asyncio.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        await monitor.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(main())
