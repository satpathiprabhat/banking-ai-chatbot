"""
Centralised logging configuration for the Banking AI assistant.

Call setup_logging() once at application startup (app/main.py).
All other modules obtain their logger with:
    import logging
    logger = logging.getLogger(__name__)

Log level is controlled by the LOG_LEVEL environment variable (default INFO).
"""

import logging
import os


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

    # Quieten noisy third-party libraries
    for lib in ("sentence_transformers", "faiss", "httpx", "httpcore", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)
