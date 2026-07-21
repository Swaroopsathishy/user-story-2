"""
logger.py
=========
Centralised logging configuration for the employee scraper pipeline.

Every module obtains its logger through :func:`get_logger` so that:

* Log format is consistent across all modules.
* Handlers can be swapped in a single place (e.g. switch to JSON logging or a
  cloud sink without touching individual modules).
* Optional file-based rotating logs are supported out of the box.

Functions
---------
- get_logger   : Factory that returns a fully configured :class:`logging.Logger`.
- reset_logger : Test-only helper that removes a logger from the registry so
                 it can be reconfigured (e.g. to attach a file handler in tests).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Module-level registry so that repeated calls to get_logger() with the
# same name return an already-configured logger (avoids duplicate handlers).
_CONFIGURED: set[str] = set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(
    name: str,
    level: int = logging.DEBUG,
    log_file: Optional[Path] = None,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
) -> logging.Logger:
    """Return a fully configured :class:`logging.Logger` for *name*.

    The first call for a given *name* attaches:

    * A ``StreamHandler`` writing **INFO** and above to ``sys.stdout``.
    * An optional ``RotatingFileHandler`` when *log_file* is provided,
      capturing **DEBUG** and above.

    Subsequent calls with the same *name* return the existing logger
    unchanged (idempotent).

    Args:
        name (str): Logger name — conventionally ``__name__`` of the calling
            module (e.g. ``"project.validator"``).
        level (int): Root log level for the logger itself.  Defaults to
            ``logging.DEBUG`` so that attached handlers can each apply their
            own filter.
        log_file (Optional[Path]): When supplied, log records are also written
            to this file using a :class:`~logging.handlers.RotatingFileHandler`.
            Parent directories are created automatically.
        max_bytes (int): Maximum size of each log file before rotation.
            Defaults to 5 MB.
        backup_count (int): Number of rotated log files to keep.
            Defaults to 3.

    Returns:
        logging.Logger: A configured logger instance ready for use.

    Example::

        from pathlib import Path
        from logger import get_logger

        log = get_logger(__name__, log_file=Path("logs/scraper.log"))
        log.info("Pipeline started.")
    """
    logger = logging.getLogger(name)

    # Idempotency guard — do not add duplicate handlers.
    if name in _CONFIGURED:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ---- Console handler (INFO+) ----------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ---- Optional rotating file handler (DEBUG+) ------------------------
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent log records from propagating to the root logger twice.
    logger.propagate = False

    _CONFIGURED.add(name)
    return logger


def reset_logger(name: str) -> None:
    """Remove *name* from the configured-logger registry and clear its handlers.

    This is intended **exclusively for use in unit tests** that need to
    reconfigure a logger (e.g. to attach a temporary file handler) without
    the idempotency guard blocking the re-initialisation.

    Args:
        name (str): The logger name to reset (same value passed to
            :func:`get_logger`).

    Example::

        from logger import reset_logger, get_logger
        reset_logger("my_test_logger")
        log = get_logger("my_test_logger", log_file=Path("test.log"))
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    _CONFIGURED.discard(name)
