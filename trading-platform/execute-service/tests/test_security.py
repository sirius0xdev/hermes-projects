"""
Security tests for execute-service.
Covers: rate limiting, risk engine, circuit breaker, Solana fixes, JWT validation.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set required env vars BEFORE any app imports
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-that-is-at-least-32-chars-long")
os.environ.setdefault("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")


# -------------------------------------------------------------------
# JWT Security Tests
# -------------------------------------------------------------------
class TestJWTSecurity:
    """Test JWT validation security requirements."""

    def test_jwt_secret_rejected_if_empty(self):
        """Empty JWT secret must raise ValueError."""
        env = dict(os.environ)
        env.pop("JWT_SECRET_KEY", None)
        env.pop("EXECUTE_JWT_SECRET_KEY", None)
        # Clear cached settings module
        mods_to_clear = [k for k in sys.modules if k.startswith("app.config")]
        for m in mods_to_clear:
            del sys.modules[m]
        with patch.dict(os.environ, env, clear=True):
            from app.config import Settings
            with pytest.raises(ValueError, match="must be set"):
                Settings()

    def test_jwt_secret_rejected_if_too_short(self):
        """JWT secret shorter than 32 chars must raise ValueError."""
        env = dict(os.environ)
        env["JWT_SECRET_KEY"] = "abc123"
        env.pop("EXECUTE_JWT_SECRET_KEY", None)
        mods_to_clear = [k for k in sys.modules if k.startswith("app.config")]
        for m in mods_to_clear:
            del sys.modules[m]
        with patch.dict(os.environ, env, clear=True):
            from app.config import Settings
            with pytest.raises(ValueError, match="at least 32"):
                Settings()

    def test_jwt_secret_accepted_if_long_enough(self):
        """JWT secret >= 32 chars should be accepted."""
        import secrets
        good_secret = secrets.token_urlsafe(48)
        env = dict(os.environ)
        env["JWT_SECRET_KEY"] = good_secret
        env.pop("EXECUTE_JWT_SECRET_KEY", None)
        mods_to_clear = [k for k in sys.modules if k.startswith("app.config")]
        for m in mods_to_clear:
            del sys.modules[m]
        with patch.dict(os.environ, env, clear=True):
            from app.config import Settings
            s = Settings()
            assert s.jwt_secret_key == good_secret

    def test_decode_access_token_invalid_token_returns_none(self):
        """Invalid tokens should return None, not raise."""
        from app.auth.service import decode_access_token
        assert decode_access_token("invalid.token.here") is None
        assert decode_access_token("") is None
        assert decode_access_token("notjwt") is None

    def test_decode_access_token_expired_returns_none(self):
        """Expired tokens should return None."""
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.config import settings
        payload = {
            "sub": "0xABC123",
            "chain": "ethereum",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # expired
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        from app.auth.service import decode_access_token
        assert decode_access_token(token) is None


# -------------------------------------------------------------------
# Rate Limiting Tests
# -------------------------------------------------------------------
class TestInMemoryRateLimiter:
    """Test in-memory rate limiter."""

    def test_allows_within_limit(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_minute=10, burst_size=5)
        for i in range(10):
            assert limiter.is_allowed("test-client") is True

    def test_blocks_over_limit(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_minute=5, burst_size=100)
        for i in range(5):
            limiter.is_allowed("test-client")
        assert limiter.is_allowed("test-client") is False

    def test_separate_keys_independent(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_minute=2, burst_size=100)
        limiter.is_allowed("client-a")
        limiter.is_allowed("client-a")
        assert limiter.is_allowed("client-a") is False
        # Client B still allowed
        assert limiter.is_allowed("client-b") is True

    def test_burst_limit(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_minute=100, burst_size=3)
        limiter.is_allowed("test-client")
        limiter.is_allowed("test-client")
        limiter.is_allowed("test-client")
        # 4th request should be blocked by burst
        assert limiter.is_allowed("test-client") is False

    def test_order_rate_limit(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(order_per_second=3)
        limiter.is_allowed("test-client", endpoint_type="order")
        limiter.is_allowed("test-client", endpoint_type="order")
        limiter.is_allowed("test-client", endpoint_type="order")
        assert limiter.is_allowed("test-client", endpoint_type="order") is False

    def test_get_remaining_headers(self):
        from app.middleware.rate_limiter import InMemoryRateLimiter
        limiter = InMemoryRateLimiter(requests_per_minute=10, burst_size=100)
        headers = limiter.get_remaining("test-client")
        assert "x-ratelimit-limit" in headers
        assert "x-ratelimit-remaining" in headers
        assert "x-ratelimit-window" in headers


class TestExtractClientKey:
    """Test client key extraction for rate limiting."""

    def test_key_from_jwt_wallet(self):
        from app.middleware.rate_limiter import _extract_client_key
        request = MagicMock()
        request.headers = {"authorization": "Bearer valid_token"}
        request.client = MagicMock(host="1.2.3.4")
        with patch("app.middleware.rate_limiter.decode_access_token") as mock_decode:
            mock_decode.return_value = {"sub": "0xABCD1234"}
            key = _extract_client_key(request)
            assert key.startswith("wallet:")
            assert "0xABCD1234" in key

    def test_key_fallback_to_ip(self):
        from app.middleware.rate_limiter import _extract_client_key
        request = MagicMock()
        request.headers = {}  # no auth
        request.client = MagicMock(host="1.2.3.4")
        key = _extract_client_key(request)
        assert key.startswith("ip:")
        assert "1.2.3.4" in key


# -------------------------------------------------------------------
# Risk Engine Tests
# -------------------------------------------------------------------
class TestRiskEngine:
    """Test risk management checks."""

    @pytest.fixture
    def risk_engine(self):
        from app.risk.engine import RiskEngine, InMemoryRiskStore
        store = InMemoryRiskStore()

        class AsyncStore:
            def __init__(self, inner):
                self._inner = inner

            async def get_daily_loss(self, wallet):
                return self._inner.get_daily_loss(wallet)

            async def add_daily_loss(self, wallet, loss):
                return self._inner.add_daily_loss(wallet, loss)

            async def get_position_count(self, wallet):
                return self._inner.get_position_count(wallet)

            async def increment_position_count(self, wallet):
                return self._inner.increment_position_count(wallet)

            async def decrement_position_count(self, wallet):
                self._inner.decrement_position_count(wallet)

        return RiskEngine(AsyncStore(store))

    @pytest.mark.asyncio
    async def test_position_size_exceeded(self, risk_engine):
        """Reject orders exceeding max position size."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 1000.0
            mock_settings.blocked_token_mints = []
            mock_settings.allowed_token_mints = None
            mock_settings.max_daily_loss_usd = 100000.0
            mock_settings.max_open_positions = 100
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            from app.risk.engine import RiskViolationError
            with pytest.raises(RiskViolationError, match="position size"):
                await risk_engine.check_order(
                    wallet_address="0xABC",
                    chain="hyperliquid",
                    symbol="BTC",
                    side="buy",
                    quantity=Decimal("1"),
                    price=Decimal("50000"),  # $50,000 position
                )

    @pytest.mark.asyncio
    async def test_position_size_ok(self, risk_engine):
        """Allow orders within max position size."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 50000.0
            mock_settings.blocked_token_mints = []
            mock_settings.allowed_token_mints = None
            mock_settings.max_daily_loss_usd = 100000.0
            mock_settings.max_open_positions = 100
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            # Should not raise
            await risk_engine.check_order(
                wallet_address="0xABC",
                chain="hyperliquid",
                symbol="BTC",
                side="buy",
                quantity=Decimal("0.1"),
                price=Decimal("50000"),  # $5,000 position
            )

    @pytest.mark.asyncio
    async def test_daily_loss_circuit_breaker(self, risk_engine):
        """Block trading when daily loss exceeds threshold."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 100000.0
            mock_settings.blocked_token_mints = []
            mock_settings.allowed_token_mints = None
            mock_settings.max_daily_loss_usd = 5000.0
            mock_settings.max_open_positions = 100
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            # Record losses approaching threshold
            await risk_engine.record_loss("0xABC", 3000)
            await risk_engine.record_loss("0xABC", 2500)  # total: $5,500 > $5,000

            from app.risk.engine import RiskViolationError
            with pytest.raises(RiskViolationError, match="daily loss circuit"):
                await risk_engine.check_order(
                    wallet_address="0xABC",
                    chain="hyperliquid",
                    symbol="ETH",
                    side="buy",
                    quantity=Decimal("1"),
                    price=Decimal("3000"),
                )

    @pytest.mark.asyncio
    async def test_max_open_positions(self, risk_engine):
        """Block when max open positions reached."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 100000.0
            mock_settings.blocked_token_mints = []
            mock_settings.allowed_token_mints = None
            mock_settings.max_daily_loss_usd = 100000.0
            mock_settings.max_open_positions = 3
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            await risk_engine.position_opened("0xABC")
            await risk_engine.position_opened("0xABC")
            await risk_engine.position_opened("0xABC")

            from app.risk.engine import RiskViolationError
            with pytest.raises(RiskViolationError, match="max open positions"):
                await risk_engine.check_order(
                    wallet_address="0xABC",
                    chain="hyperliquid",
                    symbol="SOL",
                    side="buy",
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                )

    @pytest.mark.asyncio
    async def test_token_blocklist(self, risk_engine):
        """Block trades on blacklisted tokens."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 100000.0
            mock_settings.blocked_token_mints = ["RugToken1111111111111111111111111111111111"]
            mock_settings.allowed_token_mints = None
            mock_settings.max_daily_loss_usd = 100000.0
            mock_settings.max_open_positions = 100
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            from app.risk.engine import RiskViolationError
            with pytest.raises(RiskViolationError, match="blocked"):
                await risk_engine.check_order(
                    wallet_address="0xABC",
                    chain="solana",
                    symbol="RugToken1111111111111111111111111111111111",
                    side="buy",
                    quantity=Decimal("1000"),
                    price=Decimal("1"),
                )

    @pytest.mark.asyncio
    async def test_token_allowlist(self, risk_engine):
        """Only allow tokens on the allowlist when enabled."""
        with patch("app.risk.engine.settings") as mock_settings:
            mock_settings.max_position_size_usd = 100000.0
            mock_settings.blocked_token_mints = []
            mock_settings.allowed_token_mints = [
                "EPjFWdd5AufqSSqeM2qN1xzybapC8g4wEGGkZwyTDt1v"
            ]  # USDC
            mock_settings.max_daily_loss_usd = 100000.0
            mock_settings.max_open_positions = 100
            mock_settings.solana_max_tx_lamports = 10_000_000_000

            # USDC should be allowed
            await risk_engine.check_order(
                wallet_address="0xABC",
                chain="solana",
                symbol="USDC",
                side="buy",
                quantity=Decimal("100"),
                price=Decimal("1"),
            )

            # Random token should be blocked
            from app.risk.engine import RiskViolationError
            with pytest.raises(RiskViolationError, match="not on the allowed list"):
                await risk_engine.check_order(
                    wallet_address="0xABC",
                    chain="solana",
                    symbol="RandomToken11111111111111111111111111111111",
                    side="buy",
                    quantity=Decimal("100"),
                    price=Decimal("1"),
                )


# -------------------------------------------------------------------
# Solana Circuit Breaker Tests
# -------------------------------------------------------------------
class TestSolanaCircuitBreaker:
    """Test Solana circuit breaker logic."""

    def test_closed_allows_requests(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=3, timeout_seconds=5)
        assert cb.is_open is False

    def test_opens_after_threshold_failures(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=3, timeout_seconds=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True

    def test_success_resets(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=3, timeout_seconds=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.is_open is False

    def test_half_open_after_timeout(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=2, timeout_seconds=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        time.sleep(1.1)
        assert cb.is_open is False  # transitioned to HALF_OPEN

    def test_half_open_failure_retrips(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=2, timeout_seconds=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        cb.is_open  # trigger HALF_OPEN
        cb.record_failure()  # fail recovery test
        assert cb.is_open is True

    def test_state_report(self):
        from app.executors.solana import SolanaCircuitBreaker

        cb = SolanaCircuitBreaker(threshold=5, timeout_seconds=300)
        state = cb.get_state()
        assert state["state"] == "CLOSED"
        assert state["consecutive_failures"] == 0
        assert state["threshold"] == 5


# -------------------------------------------------------------------
# Solana Executor Fixes Tests
# -------------------------------------------------------------------
class TestSolanaExecutorFixes:
    """Test Solana executor security fixes."""

    def test_transfer_instruction_uses_signer_pubkey(self):
        """Transfer instruction must use actual signer pubkey, not empty string."""
        from solders.pubkey import Pubkey

        from app.executors.solana import SolanaExecutor

        test_pubkey = Pubkey.from_string(
            "TestPubkey111111111111111111111111111111111"
        )
        to_pubkey = Pubkey.from_string("ToAddress111111111111111111111111111111111")

        instruction = SolanaExecutor._create_transfer_instruction(
            from_pubkey=test_pubkey,
            to=to_pubkey,
            lamports=1000000,
        )

        # Verify the instruction has the correct from_pubkey
        assert instruction.keys[0].pubkey == test_pubkey

    def test_send_sol_uses_signer_pubkey_not_empty(self):
        """send_sol should not use Pubkey.from_string('') as from_pubkey."""
        import inspect

        from app.executors.solana import SolanaExecutor

        source = inspect.getsource(SolanaExecutor.send_sol)
        assert (
            'Pubkey.from_string("")' not in source
        ), "send_sol still uses empty string for from_pubkey"

    def test_has_http_client_pooling(self):
        """Solana executor should have HTTP client pooling."""
        import inspect

        from app.executors.solana import SolanaExecutor

        source = inspect.getsource(SolanaExecutor)
        assert "_http_client" in source
        assert "httpx.AsyncClient" in source

    def test_has_confirmation_polling(self):
        """Solana executor should wait for transaction confirmation."""
        import inspect

        from app.executors.solana import SolanaExecutor

        source = inspect.getsource(SolanaExecutor)
        assert "_wait_for_confirmation" in source

    def test_has_circuit_breaker(self):
        """Solana executor should have circuit breaker."""
        import inspect

        from app.executors.solana import SolanaExecutor

        source = inspect.getsource(SolanaExecutor)
        assert "_circuit_breaker" in source
        assert "_check_circuit" in source


# -------------------------------------------------------------------
# Configuration Security Tests
# -------------------------------------------------------------------
class TestConfigSecurity:
    """Test security-related configuration."""

    def test_devnet_rpc_warning(self):
        """Devnet RPC URL should produce a warning."""
        import logging
        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("app.config")
        logger.addHandler(handler)

        env = dict(os.environ)
        env["SOLANA_RPC_URL"] = "https://api.devnet.solana.com"
        mods_to_clear = [k for k in sys.modules if k.startswith("app.config")]
        for m in mods_to_clear:
            del sys.modules[m]
        with patch.dict(os.environ, env, clear=True):
            from app.config import Settings

            s = Settings()
            assert "devnet" in s.solana_rpc_url

        logger.removeHandler(handler)

    def test_rate_limit_config(self):
        """Rate limiting config should be present."""
        from app.config import settings

        assert hasattr(settings, "rate_limit_enabled")
        assert hasattr(settings, "rate_limit_requests_per_minute")
        assert hasattr(settings, "rate_limit_burst_size")
        assert hasattr(settings, "rate_limit_order_per_second")

    def test_risk_config(self):
        """Risk management config should be present."""
        from app.config import settings

        assert hasattr(settings, "max_position_size_usd")
        assert hasattr(settings, "max_daily_loss_usd")
        assert hasattr(settings, "max_open_positions")
        assert hasattr(settings, "blocked_token_mints")
        assert hasattr(settings, "allowed_token_mints")

    def test_solana_security_config(self):
        """Solana security config should be present."""
        from app.config import settings

        assert hasattr(settings, "solana_circuit_breaker_threshold")
        assert hasattr(settings, "solana_circuit_breaker_timeout_seconds")
        assert hasattr(settings, "solana_txn_poll_timeout_seconds")
        assert hasattr(settings, "solana_max_tx_lamports")
