import logging
import sys


def setup_logging():
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger("research")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    root.propagate = False
