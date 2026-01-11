"""
Thread Safety Utilities

Provides thread-safe singleton patterns and synchronization helpers.
"""

from __future__ import annotations

import threading
from typing import TypeVar, Type, Dict, Any

T = TypeVar('T')


class ThreadSafeSingleton(type):
    """
    Thread-safe singleton metaclass.
    
    Example:
        class ConfigManager(metaclass=ThreadSafeSingleton):
            def __init__(self):
                self.config = {}
        
        # Both return the same instance
        a = ConfigManager()
        b = ConfigManager()
        assert a is b
    """

    _instances: Dict[Type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls: Type[T], *args, **kwargs) -> T:
        if cls not in cls._instances:
            with cls._lock:
                # Double-check locking pattern
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]


class LazySingleton:
    """
    Lazy singleton base class with thread-safe initialization.
    
    Example:
        class DatabaseConnection(LazySingleton):
            @classmethod
            def _create_instance(cls):
                return connect_to_database()
        
        conn = DatabaseConnection.get_instance()
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._create_instance()
        return cls._instance

    @classmethod
    def _create_instance(cls):
        raise NotImplementedError("Subclass must implement _create_instance")

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (mainly for testing)."""
        with cls._lock:
            cls._instance = None


class ReadWriteLock:
    """
    Read-write lock for shared resources.
    
    Allows multiple readers or single writer.
    
    Example:
        lock = ReadWriteLock()
        
        with lock.read():
            # Multiple threads can read
            data = shared_data.copy()
        
        with lock.write():
            # Only one thread can write
            shared_data.update(new_data)
    """

    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0

    def read(self):
        """Context manager for acquiring read lock."""
        return _ReadLockContext(self)

    def write(self):
        """Context manager for acquiring write lock."""
        return _WriteLockContext(self)

    def acquire_read(self):
        """Acquire read lock."""
        with self._read_ready:
            self._readers += 1

    def release_read(self):
        """Release read lock."""
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self):
        """Acquire write lock (waits for all readers)."""
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self):
        """Release write lock."""
        self._read_ready.release()


class _ReadLockContext:
    def __init__(self, lock: ReadWriteLock):
        self._lock = lock

    def __enter__(self):
        self._lock.acquire_read()
        return self

    def __exit__(self, *args):
        self._lock.release_read()


class _WriteLockContext:
    def __init__(self, lock: ReadWriteLock):
        self._lock = lock

    def __enter__(self):
        self._lock.acquire_write()
        return self

    def __exit__(self, *args):
        self._lock.release_write()


class AtomicCounter:
    """
    Thread-safe atomic counter.
    
    Example:
        counter = AtomicCounter()
        counter.increment()
        print(counter.value)  # 1
    """

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def increment(self, amount: int = 1) -> int:
        """Increment and return new value."""
        with self._lock:
            self._value += amount
            return self._value

    def decrement(self, amount: int = 1) -> int:
        """Decrement and return new value."""
        with self._lock:
            self._value -= amount
            return self._value

    def reset(self, value: int = 0) -> None:
        """Reset to given value."""
        with self._lock:
            self._value = value
