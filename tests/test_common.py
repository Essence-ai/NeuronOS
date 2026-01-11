"""
Tests for common module (Phase 4 error handling).
"""

import pytest
import logging
import time


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_neuron_error_basic(self):
        """Test basic NeuronError."""
        from common.exceptions import NeuronError

        error = NeuronError("Something failed")
        assert str(error) == "[NeuronError] Something failed"
        assert error.recoverable is True

    def test_neuron_error_with_details(self):
        """Test NeuronError with details."""
        from common.exceptions import NeuronError

        error = NeuronError(
            "Operation failed",
            code="OP_FAILED",
            details={"field": "value"},
            recoverable=False,
        )

        assert error.code == "OP_FAILED"
        assert error.details == {"field": "value"}
        assert error.recoverable is False
        assert "details:" in str(error)

    def test_neuron_error_to_dict(self):
        """Test JSON serialization."""
        from common.exceptions import NeuronError

        error = NeuronError("Test", code="TEST", details={"key": 1})
        d = error.to_dict()

        assert d["error"] == "TEST"
        assert d["message"] == "Test"
        assert d["details"]["key"] == 1

    def test_vm_not_found_error(self):
        """Test VMNotFoundError specialization."""
        from common.exceptions import VMNotFoundError

        error = VMNotFoundError("my-vm")
        assert "my-vm" in str(error)
        assert error.code == "VM_NOT_FOUND"
        assert error.recoverable is False

    def test_iommu_error_contains_hints(self):
        """Test IOMMUError includes helpful hints."""
        from common.exceptions import IOMMUError

        error = IOMMUError()
        assert "intel_iommu" in str(error.details)
        assert "amd_iommu" in str(error.details)


class TestDecorators:
    """Tests for error handling decorators."""

    def test_handle_errors_returns_default(self):
        """Test @handle_errors returns default on exception."""
        from common.decorators import handle_errors

        @handle_errors(ValueError, default="fallback")
        def failing_func():
            raise ValueError("test error")

        result = failing_func()
        assert result == "fallback"

    def test_handle_errors_passes_through(self):
        """Test @handle_errors passes through on success."""
        from common.decorators import handle_errors

        @handle_errors(ValueError, default="fallback")
        def working_func():
            return "success"

        result = working_func()
        assert result == "success"

    def test_handle_errors_reraise(self):
        """Test @handle_errors can reraise."""
        from common.decorators import handle_errors

        @handle_errors(ValueError, reraise=True)
        def failing_func():
            raise ValueError("test")

        with pytest.raises(ValueError):
            failing_func()

    def test_retry_succeeds_eventually(self):
        """Test @retry succeeds after failures."""
        from common.decorators import retry

        attempt_count = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("not yet")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert attempt_count == 3

    def test_retry_exhausts_attempts(self):
        """Test @retry raises after exhausting attempts."""
        from common.decorators import retry

        @retry(max_attempts=2, delay=0.01)
        def always_fails():
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            always_fails()

    def test_timed_decorator(self, caplog):
        """Test @timed logs execution time."""
        from common.decorators import timed

        @timed
        def slow_func():
            time.sleep(0.05)
            return "done"

        with caplog.at_level(logging.DEBUG):
            result = slow_func()

        assert result == "done"


class TestLogging:
    """Tests for logging configuration."""

    def test_setup_logging_creates_handlers(self):
        """Test setup_logging configures handlers."""
        from common.logging_config import setup_logging

        setup_logging(level=logging.DEBUG)

        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_get_logger_prefix(self):
        """Test get_logger adds neuronos prefix."""
        from common.logging_config import get_logger

        logger = get_logger("test_module")
        assert "neuronos.test_module" in logger.name


class TestResources:
    """Tests for resource management."""

    def test_managed_resource_acquires(self):
        """Test ManagedResource acquires on first use."""
        from common.resources import ManagedResource

        acquire_count = 0

        def acquire():
            nonlocal acquire_count
            acquire_count += 1
            return {"connection": True}

        resource = ManagedResource(
            acquire=acquire,
            release=lambda r: None,
        )

        with resource.use() as r:
            assert r["connection"] is True

        assert acquire_count == 1

    def test_managed_resource_reuses(self):
        """Test ManagedResource reuses existing resource."""
        from common.resources import ManagedResource

        acquire_count = 0

        def acquire():
            nonlocal acquire_count
            acquire_count += 1
            return {"id": acquire_count}

        resource = ManagedResource(
            acquire=acquire,
            release=lambda r: None,
        )

        # Use twice
        with resource.use():
            pass
        with resource.use():
            pass

        # Should only acquire once
        assert acquire_count == 1

    def test_resource_pool_creates_and_returns(self):
        """Test ResourcePool creates and returns resources."""
        from common.resources import ResourcePool

        created = []

        pool = ResourcePool(
            create=lambda: {"id": len(created) + 1},
            destroy=lambda r: None,
            validate=lambda r: True,
            max_size=2,
        )

        with pool.acquire() as r1:
            created.append(r1)
            assert r1["id"] == 1

        # Second acquire should reuse pooled resource
        with pool.acquire() as r2:
            assert r2["id"] == 1  # Same resource

    def test_cleanup_registry(self):
        """Test CleanupRegistry executes callbacks."""
        from common.resources import CleanupRegistry

        cleanup_called = []

        registry = CleanupRegistry()
        registry.register(lambda: cleanup_called.append(1))
        registry.register(lambda: cleanup_called.append(2))

        registry.cleanup_all()

        # Should be called in reverse order
        assert cleanup_called == [2, 1]


class TestSingletons:
    """Tests for thread-safe singletons."""

    def test_thread_safe_singleton(self):
        """Test ThreadSafeSingleton creates single instance."""
        from common.singleton import ThreadSafeSingleton

        class MySingleton(metaclass=ThreadSafeSingleton):
            def __init__(self):
                self.value = 42

        a = MySingleton()
        b = MySingleton()

        assert a is b
        assert a.value == 42

    def test_atomic_counter(self):
        """Test AtomicCounter thread-safe operations."""
        from common.singleton import AtomicCounter

        counter = AtomicCounter(0)
        assert counter.value == 0

        counter.increment()
        assert counter.value == 1

        counter.increment(5)
        assert counter.value == 6

        counter.decrement(3)
        assert counter.value == 3


class TestFeatures:
    """Tests for graceful degradation."""

    def test_feature_manager_executes_primary(self):
        """Test FeatureManager executes primary when available."""
        from common.features import Feature, FeatureManager

        manager = FeatureManager()
        manager.register(Feature(
            name="test_feature",
            check=lambda: True,
            primary=lambda x: x * 2,
            fallback=lambda x: x,
        ))

        result = manager.execute("test_feature", 5)
        assert result == 10

    def test_feature_manager_uses_fallback(self):
        """Test FeatureManager uses fallback when unavailable."""
        from common.features import Feature, FeatureManager

        manager = FeatureManager()
        manager.register(Feature(
            name="test_feature",
            check=lambda: False,
            primary=lambda x: x * 2,
            fallback=lambda x: x + 1,
        ))

        result = manager.execute("test_feature", 5)
        assert result == 6

    def test_feature_manager_raises_without_fallback(self):
        """Test FeatureManager raises when no fallback."""
        from common.features import Feature, FeatureManager

        manager = FeatureManager()
        manager.register(Feature(
            name="test_feature",
            check=lambda: False,
            primary=lambda: "primary",
            fallback=None,
        ))

        with pytest.raises(RuntimeError):
            manager.execute("test_feature")
