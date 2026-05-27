"""Redis cache layer for real-time market data."""

import json
import logging
import time
from typing import Optional

import redis

from data_infrastructure.redis.config import RedisSettings, get_redis_settings

logger = logging.getLogger(__name__)


class MarketDataCache:
    """Hot cache for market data backed by Redis.

    Patterns:
    - String SET/GET for latest tick prices and BBO snapshots
    - Sorted Sets + hash tags for order book price-level queries
    - Redis Streams for tick data event log with replay
    """

    def __init__(self, settings: Optional[RedisSettings] = None):
        self._settings = settings or get_redis_settings()
        self._client: Optional[redis.Redis] = None
        self._connected = False

        # Hit/miss tracking
        self._hits = 0
        self._misses = 0

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("MarketDataCache not connected. Call connect() first.")
        return self._client

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self):
        """Establish Redis connection."""
        self._client = redis.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            db=self._settings.redis_db,
            password=self._settings.redis_password,
            socket_timeout=self._settings.redis_socket_timeout,
            socket_connect_timeout=self._settings.redis_socket_connect_timeout,
            retry_on_timeout=self._settings.redis_retry_on_timeout,
            health_check_interval=self._settings.redis_health_check_interval,
            decode_responses=True,
        )
        # Test connection
        try:
            self._client.ping()
            self._connected = True
            logger.info(
                f"Redis connected: {self._settings.redis_host}:"
                f"{self._settings.redis_port}"
            )
        except redis.ConnectionError as e:
            self._connected = False
            logger.error(f"Redis connection failed: {e}")
            raise

    async def disconnect(self):
        """Close Redis connection."""
        if self._client:
            self._client.close()
            self._connected = False
            logger.info("Redis connection closed")

    def _key(self, *parts: str) -> str:
        """Build namespaced Redis key."""
        return f"{self._settings.key_prefix}:{'-'.join(parts)}"

    # --- Latest price (String SET/GET) ---

    def set_latest_price(self, symbol: str, price_data: dict) -> bool:
        """Store latest price for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'AAPL')
            price_data: Dict with price fields {price, bid, ask, volume, ts_ns}

        Returns:
            True if written successfully
        """
        try:
            key = self._key("latest", symbol)
            self.client.setex(
                key,
                self._settings.tick_ttl,
                json.dumps(price_data),
            )
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to set latest price for {symbol}: {e}")
            return False

    def get_latest_price(self, symbol: str) -> Optional[dict]:
        """Retrieve latest price for a symbol."""
        try:
            key = self._key("latest", symbol)
            val = self.client.get(key)
            if val:
                self._hits += 1
                return json.loads(val)
            self._misses += 1
            return None
        except redis.RedisError as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            self._misses += 1
            return None

    # --- BBO - Best Bid/Offer (String SET/GET) ---

    def set_bbo(self, symbol: str, bbo_data: dict) -> bool:
        """Store best bid/offer snapshot.

        Args:
            symbol: Trading symbol
            bbo_data: Dict {bid, bid_size, ask, ask_size, ts_ns}

        Returns:
            True if written successfully
        """
        try:
            key = self._key("bbo", symbol)
            self.client.setex(
                key,
                self._settings.bbo_ttl,
                json.dumps(bbo_data),
            )
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to set BBO for {symbol}: {e}")
            return False

    def get_bbo(self, symbol: str) -> Optional[dict]:
        """Retrieve best bid/offer for a symbol."""
        try:
            key = self._key("bbo", symbol)
            val = self.client.get(key)
            if val:
                self._hits += 1
                return json.loads(val)
            self._misses += 1
            return None
        except redis.RedisError as e:
            logger.error(f"Failed to get BBO for {symbol}: {e}")
            self._misses += 1
            return None

    # --- Order book (Sorted Set + hash tags for cluster co-location) ---

    def set_orderbook(self, symbol: str, levels: list[dict]) -> bool:
        """Store order book levels as sorted set.

        Uses hash tags for cluster co-location: {SYMBOL}:ob

        Args:
            symbol: Trading symbol
            levels: List of {side: 'bid'|'ask', price: float, size: int, ts_ns: int}

        Returns:
            True if written successfully
        """
        try:
            prefix = self._settings.key_prefix
            # Clear existing order book
            self.client.delete(f"{prefix}:{{{symbol}}}:ob")

            # Add levels: score = price, member = json(side:size:ts_ns)
            pipe = self.client.pipeline()
            for level in levels:
                member = json.dumps({
                    "side": level["side"],
                    "price": level["price"],
                    "size": level["size"],
                    "ts_ns": level.get("ts_ns", 0),
                })
                pipe.zadd(f"{prefix}:{{{symbol}}}:ob", {member: level["price"]})
            pipe.execute()
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to set order book for {symbol}: {e}")
            return False

    def get_orderbook(self, symbol: str, top_n: int = 10) -> Optional[dict]:
        """Retrieve top N bid/ask levels from order book.

        Args:
            symbol: Trading symbol
            top_n: Number of levels to return per side

        Returns:
            Dict {bids: [...], asks: [...]} or None
        """
        try:
            prefix = self._settings.key_prefix
            # Get all members sorted by price
            all_levels = self.client.zrange(
                f"{prefix}:{{{symbol}}}:ob", 0, -1, withscores=True
            )
            if not all_levels:
                self._misses += 1
                return None

            self._hits += 1
            bids = []
            asks = []
            for member, score in all_levels:
                level = json.loads(member)
                if level["side"] == "bid":
                    bids.append(level)
                else:
                    asks.append(level)

            return {
                "bids": bids[:top_n],
                "asks": sorted(asks, reverse=True)[:top_n],
            }
        except redis.RedisError as e:
            logger.error(f"Failed to get order book for {symbol}: {e}")
            self._misses += 1
            return None

    # --- Tick data (Redis Streams) ---

    def add_tick(self, symbol: str, tick_data: dict) -> str:
        """Append tick to Redis Stream for symbol.

        Args:
            symbol: Trading symbol
            tick_data: Dict {price, side, size, exchange, ts_ns}

        Returns:
            Stream entry ID (or empty string on failure)
        """
        try:
            stream_key = self._key("ticks", symbol)
            entry_id = self.client.xadd(
                stream_key,
                tick_data,
                maxlen=1_000_000,  # Keep last 1M entries per symbol
                approximate=True,
            )
            return entry_id or ""
        except redis.RedisError as e:
            logger.error(f"Failed to add tick for {symbol}: {e}")
            return ""

    # --- Health / stats ---

    def get_cache_hit_rate(self) -> dict:
        """Return cache hit/miss stats.

        Returns:
            Dict {hits, misses, hit_rate}
        """
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }

    def check_connection(self) -> bool:
        """Ping Redis to check connection health."""
        try:
            if self._client:
                self._client.ping()
                return True
        except redis.RedisError:
            pass
        return False
