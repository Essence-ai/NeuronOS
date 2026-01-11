"""
Logging configuration for NeuronOS.

Provides structured logging with JSON and colored console output.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import json
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """JSON log formatter for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability."""

    COLORS = {
        logging.DEBUG: "\033[36m",    # Cyan
        logging.INFO: "\033[32m",     # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        levelname = record.levelname
        
        # Apply color to level name
        record.levelname = f"{color}{levelname}{self.RESET}"
        
        # Format the message
        result = super().format(record)
        
        # Restore original levelname for other handlers
        record.levelname = levelname
        
        return result


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    json_logs: bool = False,
    log_dir: Optional[Path] = None,
):
    """
    Configure logging for NeuronOS.

    Args:
        level: Logging level (default: INFO)
        log_file: Path to log file (optional)
        json_logs: Use JSON format for file logs
        log_dir: Directory for log files (creates neuronos.log)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler with colors (if terminal supports it)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)

    if sys.stderr.isatty():
        console_format = ColoredFormatter(
            "%(levelname)s %(name)s: %(message)s"
        )
    else:
        console_format = logging.Formatter(
            "%(levelname)s %(name)s: %(message)s"
        )

    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # Determine log file path
    if log_dir:
        log_file = log_dir / "neuronos.log"
    
    # File handler with rotation
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # Capture all to file

        if json_logs:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s"
            ))

        root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("libvirt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("gi").setLevel(logging.WARNING)


class LogContext:
    """
    Context manager for adding context to log messages.
    
    Example:
        with LogContext(vm_name="my-vm", operation="start"):
            logger.info("Starting VM")  # Will include vm_name and operation
    """

    def __init__(self, **kwargs):
        self.context = kwargs
        self._old_factory = None

    def __enter__(self):
        self._old_factory = logging.getLogRecordFactory()

        context = self.context

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            record.extra_data = context
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args):
        logging.setLogRecordFactory(self._old_factory)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the NeuronOS prefix.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"neuronos.{name}")
