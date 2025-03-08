from abc import ABC, abstractmethod
from typing import Any
import httpx
from collections.abc import Sequence
from datetime import datetime
from dataclasses import asdict, dataclass


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

    def as_json_serializable(self) -> dict[str, Any]:
        data = asdict(self)
        if self.deal_until:
            data["deal_until"] = str(self.deal_until)
        return data


class AbstractParser(ABC):
    def __init__(
        self,
        parse_regions: Sequence[str],
        client: httpx.AsyncClient,
        limit: int | None = None,
    ):
        self._limit = limit
        self._client = client
        if not parse_regions:
            raise ValueError("parse_regions can't be empty, specify at least 1 region")
        self._regions = set(region.lower() for region in parse_regions)

    @abstractmethod
    async def parse(self) -> Sequence[ParsedItem]: ...
