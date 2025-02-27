from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Price:
    currency_code: str
    value: float


@dataclass
class ParsedItem:
    name: str
    discount: int  # discount in percents (0-100)
    default_price: Price
    discounted_price: Price
    image_url: str
    deal_until: datetime | None = None


class AbstractParser(ABC):
    def __init__(self, url: str, limit: int | None = None):
        self._url = url
        self._limit = limit

    @abstractmethod
    def parse(self) -> Sequence[ParsedItem]: ...
