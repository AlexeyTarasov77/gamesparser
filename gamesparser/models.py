from abc import ABC, abstractmethod
import httpx
from collections.abc import Sequence
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Price:
    currency_code: str
    value: float


@dataclass
class ParsedPriceByRegion:
    base_price: Price
    discounted_price: Price


@dataclass
class ParsedItem:
    name: str
    discount: int  # discount in percents (0-100)
    prices: dict[str, ParsedPriceByRegion]
    image_url: str
    with_gp: bool | None = None
    deal_until: datetime | None = None


class AbstractParser(ABC):
    def __init__(self, client: httpx.AsyncClient, limit: int | None = None):
        self._limit = limit
        self._client = client

    @abstractmethod
    async def parse(self) -> Sequence[ParsedItem]: ...
