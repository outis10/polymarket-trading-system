"""Wrapper for py-clob-client with extended functionality"""

import logging
from typing import Any, Dict, List, Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    AssetType,
    BalanceAllowanceParams,
    MarketOrderArgs,
    OrderArgs,
    OrderType,
)

from config.settings import PolymarketConfig


class PolymarketClient:
    """Enhanced wrapper for Polymarket CLOB client"""

    def __init__(self, config: PolymarketConfig):
        """
        Initialize the Polymarket client

        Args:
            config: Polymarket configuration object
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize ClobClient with L1 authentication
        self.client = ClobClient(
            host=config.host,
            key=config.private_key,
            chain_id=config.chain_id,
            signature_type=config.signature_type,
            funder=config.funder,
        )

        # Derive or use existing L2 credentials
        if config.api_key and config.secret and config.passphrase:
            # Use existing credentials
            self.logger.info("Using existing API credentials")
            from py_clob_client.clob_types import ApiCreds

            api_creds = ApiCreds(
                api_key=config.api_key,
                api_secret=config.secret,
                api_passphrase=config.passphrase,
            )
            self.client.set_api_creds(api_creds)
        else:
            # Derive new credentials from private key
            self.logger.info("Deriving API credentials from private key...")
            api_creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(api_creds)
            self.logger.info("API credentials derived successfully")

        self.logger.info(
            f"Polymarket client initialized "
            f"(testnet={config.use_testnet}, chain_id={config.chain_id}, "
            f"signature_type={config.signature_type})"
        )

    # Market Data Methods

    def get_markets(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Get list of markets

        Args:
            **kwargs: Additional filters (next_cursor for pagination)

        Returns:
            List of market dictionaries
        """
        try:
            # La nueva API devuelve un dict con 'data', 'next_cursor', etc.
            next_cursor = kwargs.get("next_cursor", "MA==")
            response = self.client.get_markets(next_cursor=next_cursor)

            if isinstance(response, dict):
                markets = response.get("data", [])
                self.logger.debug(f"Retrieved {len(markets)} markets")
                return markets
            else:
                self.logger.warning("Unexpected response format from get_markets")
                return []
        except Exception as e:
            self.logger.error(f"Error getting markets: {e}")
            return []

    def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific market by condition ID

        Args:
            condition_id: The condition ID of the market

        Returns:
            Market dictionary or None if not found
        """
        try:
            market = self.client.get_market(condition_id)
            return market
        except Exception as e:
            self.logger.error(f"Error getting market {condition_id}: {e}")
            return None

    def get_order_book(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order book for a specific token

        Args:
            token_id: The token ID to get order book for

        Returns:
            Order book with bids and asks or None if error
        """
        try:
            orderbook = self.client.get_order_book(token_id)
            return orderbook
        except Exception as e:
            self.logger.error(f"Error getting order book for {token_id}: {e}")
            return None

    def get_market_price(self, token_id: str, side: str = "buy") -> Optional[float]:
        """
        Get current market price for a token

        Args:
            token_id: The token ID
            side: 'buy' for best bid, 'sell' for best ask

        Returns:
            Current price or None if unavailable
        """
        try:
            orderbook = self.get_order_book(token_id)
            if not orderbook:
                return None

            # OrderBookSummary has .bids and .asks as attributes, not dict keys
            bids = orderbook.bids or []
            asks = orderbook.asks or []

            if side == "buy" and bids:
                return float(bids[0].price)
            elif side == "sell" and asks:
                return float(asks[0].price)

            return None
        except Exception as e:
            self.logger.error(f"Error getting market price: {e}")
            return None

    def get_mid_price(self, token_id: str) -> Optional[float]:
        """
        Get mid price (average of best bid and best ask)

        Args:
            token_id: The token ID

        Returns:
            Mid price or None if unavailable
        """
        try:
            orderbook = self.get_order_book(token_id)
            if not orderbook:
                return None

            # OrderBookSummary has .bids and .asks as attributes, not dict keys
            bids = orderbook.bids or []
            asks = orderbook.asks or []

            if not bids or not asks:
                return None

            best_bid = float(bids[0].price)
            best_ask = float(asks[0].price)

            return (best_bid + best_ask) / 2
        except Exception as e:
            self.logger.error(f"Error calculating mid price: {e}")
            return None

    # Order Management Methods

    def place_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str = "LIMIT",
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order on Polymarket

        Args:
            token_id: The token ID to trade
            side: 'BUY' or 'SELL'
            price: Limit price (for limit orders)
            size: Order size in USDC
            order_type: 'LIMIT' or 'MARKET'

        Returns:
            Order result dictionary or None if failed
        """
        try:
            # Get tick size for proper price rounding
            tick_size = 0.01  # default
            try:
                tick_size = float(self.client.get_tick_size(token_id))
                self.logger.info(f"Tick size for token: {tick_size}")
            except Exception as e:
                self.logger.warning(f"Could not get tick size: {e}")

            # Round price to tick size
            rounded_price = round(price / tick_size) * tick_size
            rounded_price = round(rounded_price, 2)

            self.logger.info(
                f"Placing order: {side} {size} @ {rounded_price} (original: {price}) for token {token_id[:8]}..."
            )

            # Create order with all required parameters
            order_args = OrderArgs(
                token_id=token_id,
                price=rounded_price,
                size=size,
                side=side.upper(),
            )

            # Use create_and_post_order
            result = self.client.create_and_post_order(order_args)
            self.logger.info(f"Order result: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            raise

    # NOTE: nombrado place_fok_order por compatibilidad con event_manager.py,
    # pero usa FAK (Fill-and-Kill) en lugar de FOK (Fill-or-Kill).
    # FAK llena lo que puede al mejor precio y cancela el resto — más seguro para
    # órdenes pequeñas donde puede no haber liquidez exacta para el notional completo.
    def place_fok_order(
        self,
        token_id: str,
        side: str,
        amount_usd: float,
        hint_price: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Place a Fill-and-Kill (FAK) market order.
        Fills as much as possible at best available prices, cancels any unfilled remainder.

        Args:
            token_id: The token ID to trade
            side: 'BUY' or 'SELL'
            amount_usd: Notional amount in USDC to spend/receive
            hint_price: Pre-fetched best ask price. When provided, skips the internal
                        get_order_book() call in create_market_order, reducing latency
                        and the race-condition window with market makers.

        Returns:
            Order result or None if rejected
        """
        try:
            self.logger.info(
                f"Placing FAK order: {side} ${amount_usd:.2f} for token {token_id[:8]}..."
                + (f" hint_price={hint_price}" if hint_price > 0 else "")
            )
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount_usd,
                side=side.upper(),
                order_type=OrderType.FAK,
                price=hint_price if hint_price > 0 else 0,
            )
            signed_order = self.client.create_market_order(order_args)
            result = self.client.post_order(signed_order, OrderType.FAK)
            self.logger.info(f"FAK order result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error placing FAK order: {e}")
            raise

    def place_market_order(
        self, token_id: str, side: str, size: float
    ) -> Optional[Dict[str, Any]]:
        """
        Place a market order (executed at best available price)

        Args:
            token_id: The token ID to trade
            side: 'BUY' or 'SELL'
            size: Order size in USDC

        Returns:
            Order result dictionary or None if failed
        """
        # Get current market price
        price = self.get_market_price(
            token_id, "sell" if side.upper() == "BUY" else "buy"
        )
        if not price:
            self.logger.error("Could not get market price for market order")
            return None

        return self.place_order(token_id, side, price, size, "MARKET")

    def place_gtc_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        amount_usd: float,
    ) -> Optional[Dict[str, Any]]:
        """Place a GTC (Good-Till-Cancelled) limit order.

        Args:
            token_id: The token ID to trade
            side: 'BUY' or 'SELL'
            price: Limit price per share (0-1)
            amount_usd: Notional amount in USDC; converted to shares internally

        Returns:
            Order result dict (contains 'orderID' or 'id') or raises on error.
        """
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")
        shares = round(amount_usd / price, 6)
        return self.place_order(token_id, side, price, shares)

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order

        Args:
            order_id: The order ID to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.cancel_order(order_id)
            self.logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """
        Cancel all open orders

        Returns:
            Number of orders cancelled
        """
        try:
            orders = self.get_open_orders()
            cancelled = 0
            for order in orders:
                if self.cancel_order(order["id"]):
                    cancelled += 1
            self.logger.info(f"Cancelled {cancelled} orders")
            return cancelled
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            return 0

    # Account Methods

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders for the account

        Returns:
            List of open order dictionaries
        """
        try:
            orders = self.client.get_orders()
            return [o for o in orders if o.get("status") == "OPEN"]
        except Exception as e:
            self.logger.error(f"Error getting open orders: {e}")
            return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions (basado en órdenes abiertas)

        Returns:
            List of position dictionaries
        """
        try:
            # La nueva API no tiene get_positions directo
            # Usamos get_orders para aproximar posiciones
            orders = self.client.get_orders()
            # Filtrar solo órdenes filled que representen posiciones
            # Por ahora retornamos lista vacía ya que es complejo derivar posiciones
            self.logger.debug("Position tracking via orders")
            return []
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []

    def get_balance(self) -> Optional[float]:
        """
        Get account balance allowance

        Returns:
            Balance allowance or None if error
        """
        try:
            # py_clob_client requires params (None can raise AttributeError in some versions).
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self.config.signature_type,
            )
            allowance = self.client.get_balance_allowance(params)
            self.logger.info(
                f"Balance allowance raw: {allowance} (type: {type(allowance)})"
            )

            if allowance is None:
                return None

            extracted = self._extract_numeric_from_payload(allowance)
            if extracted is None:
                return None
            return self._normalize_usdc_amount(extracted)
        except Exception as e:
            self.logger.error(f"Error getting balance: {e}")
            return None

    def get_trades(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Get trade history

        Args:
            **kwargs: Filters (e.g., market, before, after)

        Returns:
            List of trade dictionaries
        """
        try:
            trades = self.client.get_trades(**kwargs)
            return trades
        except Exception as e:
            self.logger.error(f"Error getting trades: {e}")
            return []

    @staticmethod
    def _normalize_usdc_amount(value: float) -> float:
        """
        Normalize USDC-like amounts that may come in base units.
        USDC commonly uses 6 decimals on-chain (e.g. 9040000 -> 9.04).
        """
        if value == 0:
            return 0.0
        abs_v = abs(value)

        # Very large integers are usually base units (6 decimals for USDC).
        if abs_v >= 1_000_000:
            return value / 1_000_000
        return value

    @staticmethod
    def _extract_numeric_from_payload(payload: Any) -> Optional[float]:
        """Extract a numeric balance candidate from nested payloads."""
        if payload is None:
            return None

        if isinstance(payload, (int, float)):
            return float(payload)

        if isinstance(payload, str):
            try:
                return float(payload)
            except ValueError:
                return None

        # Pydantic/dataclass-like objects
        for attr in ("balance", "available", "cash", "portfolio", "allowance"):
            if hasattr(payload, attr):
                try:
                    raw = getattr(payload, attr)
                    extracted = PolymarketClient._extract_numeric_from_payload(raw)
                    if extracted is not None:
                        return extracted
                except Exception:
                    pass

        if isinstance(payload, dict):
            priority_keys = (
                "balance",
                "available_balance",
                "available",
                "cash",
                "portfolio",
                "allowance",
                "usdc",
                "value",
                "total",
            )
            for key in priority_keys:
                if key in payload:
                    extracted = PolymarketClient._extract_numeric_from_payload(
                        payload.get(key)
                    )
                    if extracted is not None:
                        return extracted

            # Recursive fallback: first numeric-like value found.
            for v in payload.values():
                extracted = PolymarketClient._extract_numeric_from_payload(v)
                if extracted is not None:
                    return extracted

        return None
