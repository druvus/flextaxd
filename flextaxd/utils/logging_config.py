"""Logging configuration for FlexTaxD."""

import logging
import logging.config
import sys
from typing import Optional
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_file: Optional[Path] = None) -> None:
    """
    Setup structured logging for FlexTaxD.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
    """
    # Define log format
    console_format = "%(levelname)s: %(message)s"
    file_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure handlers
    handlers = {
        'console': {
            'class': 'logging.StreamHandler',
            'level': level,
            'formatter': 'console',
            'stream': sys.stderr,
        }
    }
    
    formatters = {
        'console': {
            'format': console_format,
        },
        'file': {
            'format': file_format,
            'datefmt': '%Y-%m-%d %H:%M:%S',
        }
    }
    
    # Add file handler if specified
    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        handlers['file'] = {
            'class': 'logging.FileHandler',
            'level': logging.DEBUG,  # File gets everything
            'formatter': 'file',
            'filename': str(log_file),
            'mode': 'a',
        }
    
    # Configure logging
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': formatters,
        'handlers': handlers,
        'loggers': {
            'flextaxd': {
                'level': logging.DEBUG,
                'handlers': list(handlers.keys()),
                'propagate': False,
            },
            # Reduce noise from external libraries
            'urllib3': {'level': logging.WARNING},
            'requests': {'level': logging.WARNING},
        },
        'root': {
            'level': logging.WARNING,
            'handlers': list(handlers.keys()),
        }
    }
    
    logging.config.dictConfig(config)
    
    # Log configuration info
    logger = logging.getLogger('flextaxd.logging')
    logger.debug(f"Logging configured with level: {logging.getLevelName(level)}")
    if log_file:
        logger.debug(f"File logging enabled: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with FlexTaxD namespace."""
    if not name.startswith('flextaxd.'):
        name = f'flextaxd.{name}'
    return logging.getLogger(name)