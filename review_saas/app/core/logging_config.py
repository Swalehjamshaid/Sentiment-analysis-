import logging
import sys

def setup_logging(debug: bool = True):
    """
    Configures global logging for FastAPI app.
    Outputs to console (Railway / Uvicorn) with timestamps and levels.
    """
    level = logging.DEBUG if debug else logging.INFO

    fmt = "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce verbosity for external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
