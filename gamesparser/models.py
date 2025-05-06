from abc import ABC, abstractmethod
import logging
import httpx
from collections.abc import Iterable, Sequence
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Price:
    currency_code: str
    discounted_value: float


@dataclass
class ParsedItem:
    id: str
    name: str
    url: str
    preview_img_url: str
    discount: int  # discount in percents (0-100)
    prices: dict[str, Price]


@dataclass
class XboxParsedItem(ParsedItem):
    with_sub: bool
    deal_until: datetime | None = None


@dataclass
class XboxItemDetails:
    description: str
    platforms: list[str]
    media: Sequence[str]


@dataclass
class PsnParsedItem(ParsedItem):
    platforms: list[str]
    with_sub: bool
    media: Sequence[str]


@dataclass
class PsnItemDetails:
    description: str
    deal_until: datetime | None = None


class AbstractParser[T](ABC):
    def __init__(
        self,
        client: httpx.AsyncClient,
        logger: logging.Logger | None = None,
    ):
        self._client = client
        if logger is None:
            logger = logging.getLogger("GAMESPARSER")
        self._logger = logger

    def _normalize_regions(self, regions: Iterable[str]) -> list[str]:
        assert not isinstance(regions, str), "regions can't be string"
        normalized = []
        for region in regions:
            reg = region.strip().lower()
            if reg not in normalized:
                normalized.append(reg)
        return normalized

    @abstractmethod
    async def parse(self, regions: Iterable[str]) -> Sequence[ParsedItem]: ...
    @abstractmethod
    async def parse_item_details(self, url: str) -> T | None: ...
