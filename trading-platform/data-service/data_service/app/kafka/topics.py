class KafkaTopics:
    """Centralized Kafka topic definitions for the trading platform."""
    
    # Market data topics
    MARKET_PRICES = "trading-platform.market.prices.v1"
    MARKET_ORDERBOOK = "trading-platform.market.orderbook.v1"
    MARKET_TRADES = "trading-platform.market.trades.v1"
    
    # News and analysis topics
    NEWS_FEED = "trading-platform.news.feed.v1"
    NEWS_ANALYSIS = "trading-platform.news.analysis.v1"
    
    # Trading signals (downstream consumption)
    TRADING_SIGNALS = "trading-platform.signals.trading.v1"

    # Solana on-chain data topics
    SOLANA_TOKEN_DATA = "solana.token.data"
    SOLANA_POOL_DATA = "solana.pool.data"
    SOLANA_BLOCK = "solana.block.v1"
