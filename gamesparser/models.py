from abc import ABC, abstractmethod
import logging
import httpx
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
    item_url: str
    discount: int  # discount in percents (0-100)
    prices: dict[str, Price]
    image_url: str

    # def as_json_serializable(self) -> dict[str, Any]:
    #     data = asdict(self)
    #     if self.deal_until:
    #         data["deal_until"] = str(self.deal_until)
    #     return data


@dataclass
class XboxParsedItem(ParsedItem):
    with_gp: bool
    deal_until: datetime | None = None


@dataclass
class XboxItemDetails:
    description: str
    platforms: list[str]


@dataclass
class PsnParsedItem(ParsedItem):
    platforms: list[str]
    with_sub: bool


@dataclass
class PsnItemDetails:
    description: str
    deal_until: datetime | None = None


class AbstractParser(ABC):
    def __init__(
        self,
        parse_regions: Sequence[str],
        client: httpx.AsyncClient,
        limit: int | None = None,
        logger: logging.Logger | None = None,
    ):
        self._limit = limit
        self._client = client
        if not parse_regions:
            raise ValueError("parse_regions can't be empty, specify at least 1 region")
        self._regions = set(region.lower() for region in parse_regions)
        if logger is None:
            logger = logging.getLogger(__name__)
        self._logger = logger

    @abstractmethod
    async def parse(self) -> Sequence[ParsedItem]: ...
