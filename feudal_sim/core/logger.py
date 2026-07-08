"""
Centralised logging for the feudal simulation.

Usage in any module:
    from feudal_sim.core.logger import get_logger
    logger = get_logger(__name__)

Log levels:
    logger.debug(...)    — verbose/development detail
    logger.info(...)     — normal simulation events (replaces print)
    logger.warning(...)  — recoverable problems, degraded behaviour
    logger.error(...)    — failures that affect simulation correctness
"""

import logging
import sys


_HANDLER_INSTALLED = False


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Configure the root feudal_sim logger. Call once from main.py.
    All child loggers (feudal_sim.core.simulation, etc.) inherit this config.
    """
    global _HANDLER_INSTALLED
    if _HANDLER_INSTALLED:
        return

    root = logging.getLogger('feudal_sim')
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    # Keep the format clean — matches existing output style so log analysis tools still work
    handler.setFormatter(logging.Formatter('%(message)s'))
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)

    _HANDLER_INSTALLED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the feudal_sim namespace."""
    # Ensure the name is rooted under feudal_sim
    if not name.startswith('feudal_sim'):
        name = f'feudal_sim.{name}'
    return logging.getLogger(name)
