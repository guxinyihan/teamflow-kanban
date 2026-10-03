"""Application logs deliberately omit request headers, bodies and tokens."""
import logging
logger = logging.getLogger("teamflow")

def debug_log(function):
    return function