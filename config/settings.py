"""Settings and configuration management"""
from dataclasses import dataclass
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class TradingConfig:
    """Trading-specific configuration"""
    max_position_size: float
    max_total_exposure: float
    stop_loss_pct: float
    take_profit_pct: float
    min_confidence: float
    order_timeout: int


@dataclass
class PolymarketConfig:
    """Polymarket API configuration"""
    # L1 Authentication
    private_key: str
    funder: str
    signature_type: int  # 0=EOA/MetaMask, 1=Magic/email, 2=proxy

    # L2 Authentication (opcional, se puede derivar desde private_key)
    api_key: Optional[str] = None
    secret: Optional[str] = None
    passphrase: Optional[str] = None

    # Network
    use_testnet: bool = True
    chain_id: int = 80002  # 80002=testnet, 137=mainnet

    @property
    def host(self) -> str:
        """Get the appropriate host URL"""
        if self.use_testnet:
            return "https://clob-testnet.polymarket.com"
        return "https://clob.polymarket.com"


class Settings:
    """Main settings class"""
    
    def __init__(self):
        # Polymarket settings
        self.polymarket = PolymarketConfig(
            # L1 Authentication
            private_key=os.getenv('POLYMARKET_PRIVATE_KEY', ''),
            funder=os.getenv('POLYMARKET_FUNDER', ''),
            signature_type=int(os.getenv('POLYMARKET_SIGNATURE_TYPE', '1')),

            # L2 Authentication (opcional)
            api_key=os.getenv('POLYMARKET_API_KEY'),
            secret=os.getenv('POLYMARKET_SECRET'),
            passphrase=os.getenv('POLYMARKET_PASSPHRASE'),

            # Network
            use_testnet=os.getenv('USE_TESTNET', 'true').lower() == 'true',
            chain_id=int(os.getenv('CHAIN_ID', '80002'))
        )
        
        # Trading settings
        self.trading = TradingConfig(
            max_position_size=float(os.getenv('MAX_POSITION_SIZE', '100.0')),
            max_total_exposure=float(os.getenv('MAX_TOTAL_EXPOSURE', '500.0')),
            stop_loss_pct=float(os.getenv('STOP_LOSS_PCT', '0.05')),
            take_profit_pct=float(os.getenv('TAKE_PROFIT_PCT', '0.15')),
            min_confidence=float(os.getenv('MIN_CONFIDENCE', '0.7')),
            order_timeout=int(os.getenv('ORDER_TIMEOUT', '300'))
        )
        
        # OpenAI settings (for LangChain)
        self.openai_api_key: Optional[str] = os.getenv('OPENAI_API_KEY')
        
        # Logging
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    
    def validate(self) -> bool:
        """Validate required settings"""
        if not self.polymarket.private_key:
            raise ValueError("POLYMARKET_PRIVATE_KEY is required")
        if not self.polymarket.funder:
            raise ValueError("POLYMARKET_FUNDER is required")
        if self.polymarket.signature_type not in [0, 1, 2]:
            raise ValueError("POLYMARKET_SIGNATURE_TYPE must be 0, 1, or 2")
        # API credentials are optional - se pueden derivar
        return True


# Global settings instance
settings = Settings()
