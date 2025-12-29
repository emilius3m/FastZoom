"""
Centralized Loguru logging configuration for FastZoom application.

This module provides a comprehensive logging setup using Loguru with:
- InterceptHandler to redirect standard Python logging to Loguru
- Console and file output configuration
- Environment variable support for configuration
- Proper formatting with colors for console and plain text for files
- Integration with FastAPI, Uvicorn, SQLAlchemy, and other libraries
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

from loguru import logger


class InterceptHandler(logging.Handler):
    """
    Intercept standard logging messages and redirect them to Loguru.
    
    This handler captures logs from standard Python logging libraries
    (like FastAPI, Uvicorn, SQLAlchemy) and routes them through Loguru
    for consistent formatting and handling.
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record through Loguru.
        
        Args:
            record: The log record to emit
        """
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_rotation: Optional[str] = None,
    log_retention: Optional[str] = None,
    log_format: Optional[str] = None,
    console_format: Optional[str] = None,
    enable_colors: Optional[bool] = None,
) -> None:
    """
    Set up centralized logging with Loguru.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (default: logs/app.log)
        log_rotation: Log rotation configuration (default: "10 MB")
        log_retention: Log retention configuration (default: "30 days")
        log_format: Custom log format for file output
        console_format: Custom log format for console output
        enable_colors: Whether to enable colors in console output
    """
    # Get configuration from environment variables with defaults
    log_level = log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = log_file or os.getenv("LOG_FILE", "logs/app.log")
    log_rotation = log_rotation or os.getenv("LOG_ROTATION", "10 MB")
    log_retention = log_retention or os.getenv("LOG_RETENTION", "30 days")
    enable_colors = enable_colors if enable_colors is not None else os.getenv("LOG_COLORS", "true").lower() == "true"
    
    # Default formats
    if log_format is None:
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    
    if console_format is None:
        console_format = (
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    
    # Remove default Loguru handler
    logger.remove()
    
    # Add console handler with colors
    logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=enable_colors,
        backtrace=False,  # Ridotto per meno verbosità
        diagnose=False,   # Disabilita annotazioni variabili
    )
    
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add file handler without colors
    file_format = log_format.replace("<green>", "").replace("</green>", "") \
                          .replace("<level>", "").replace("</level>", "") \
                          .replace("<cyan>", "").replace("</cyan>", "")
    
    logger.add(
        log_file,
        format=file_format,
        level=log_level,
        rotation=log_rotation,
        retention=log_retention,
        compression="zip",
        backtrace=False,  # Ridotto per meno verbosità
        diagnose=False,   # Disabilita annotazioni variabili
        encoding="utf-8",
    )
    
    # Intercept standard logging
    setup_logging_interception()
    
    logger.info(f"Logging initialized with level: {log_level}")
    logger.info(f"Log file: {log_file}")


def setup_logging_interception() -> None:
    """
    Set up interception of standard Python logging to route through Loguru.
    
    This captures logs from FastAPI, Uvicorn, SQLAlchemy, and other libraries
    that use the standard Python logging module.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add our intercept handler
    root_logger.addHandler(InterceptHandler())
    root_logger.setLevel(logging.DEBUG)
    
    # Configure specific loggers to avoid duplicate logs
    loggers_to_configure = [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "sqlalchemy.dialects",
        "minio",
        "botocore",
        "urllib3",
        "requests",
        "aiohttp",
    ]
    
    for logger_name in loggers_to_configure:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = []
        # Set SQLAlchemy loggers to WARNING to reduce verbose query logging
        if logger_name.startswith("sqlalchemy"):
            logging_logger.setLevel(logging.WARNING)
        else:
            logging_logger.setLevel(logging.DEBUG)
        logging_logger.propagate = True


def get_logger(name: Optional[str] = None) -> Any:
    """
    Get a logger instance for backward compatibility.
    
    Args:
        name: Optional logger name (for compatibility with standard logging)
        
    Returns:
        Loguru logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger


def configure_third_party_loggers(
    loggers_config: Optional[Dict[str, Dict[str, Any]]] = None
) -> None:
    """
    Configure third-party library loggers with specific settings.
    
    Args:
        loggers_config: Dictionary mapping logger names to their configuration
                       (level, handlers, etc.)
    """
    default_config = {
        "uvicorn": {"level": "INFO"},
        "uvicorn.access": {"level": "INFO"},
        "uvicorn.error": {"level": "INFO"},
        "fastapi": {"level": "INFO"},
        "sqlalchemy.engine": {"level": "WARNING"},
        "sqlalchemy.pool": {"level": "WARNING"},
        "minio": {"level": "WARNING"},
        "botocore": {"level": "WARNING"},
        "urllib3": {"level": "WARNING"},
    }
    
    # Merge with provided config
    if loggers_config:
        default_config.update(loggers_config)
    
    # Apply configuration
    for logger_name, config in default_config.items():
        logging_logger = logging.getLogger(logger_name)
        if "level" in config:
            logging_logger.setLevel(config["level"])


def get_log_config() -> Dict[str, Any]:
    """
    Get current logging configuration.
    
    Returns:
        Dictionary containing current logging configuration
    """
    return {
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "log_file": os.getenv("LOG_FILE", "logs/app.log"),
        "log_rotation": os.getenv("LOG_ROTATION", "10 MB"),
        "log_retention": os.getenv("LOG_RETENTION", "30 days"),
        "log_colors": os.getenv("LOG_COLORS", "true"),
    }


# Initialize logging when module is imported
def _initialize_logging() -> None:
    """Initialize logging with default configuration if not already set up."""
    # Check if logging is already configured
    if not logger._core.handlers:
        # Only set up if not already configured
        setup_logging()


# Auto-initialize when module is imported
_initialize_logging()