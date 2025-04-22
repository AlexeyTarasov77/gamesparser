import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s (%(filename)s:%(lineno)d) %(levelname)s - %(message)s",
)

from .models import AbstractParser, ParsedItem
from .psn import PsnParser
from .xbox import XboxParser

__all__ = ["AbstractParser", "ParsedItem", "PsnParser", "XboxParser"]
