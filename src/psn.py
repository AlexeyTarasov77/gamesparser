import asyncio
from collections.abc import Sequence
import re
import math
import json

from bs4 import BeautifulSoup, Tag
import httpx
from models import AbstractParser, ParsedItem, Price


class ItemParser:
    def __init__(self, data):
        self._data = data

    def _parse_price(self, s: str) -> Price:
        price_regex = re.compile(
            r"(?:(?P<price>\d[\d\s.,]*)\s*([A-Z]{2,3})|([A-Z]{2,3})\s*(\d[\d\s.,]*))"
        )
        price_match = price_regex.search(s)
        assert price_match is not None
        # may be 2 different variations of price form on page
        if price_match.group(1) is not None:
            value, currency_code = price_match.group(1, 2)
        elif price_match.group(3) is not None:
            value, currency_code = price_match.group(4, 3)
        else:
            raise ValueError("Unable to parse price")
        normalized_value = (
            value.replace(".", "")
            .replace(",", ".")
            .replace(" ", "")
            .replace("\xa0", "")
        )
        return Price(value=float(normalized_value), currency_code=currency_code.strip())

    def _parse_discount(self, s: str) -> int:
        normalized = s.replace("%", "")
        return abs(int(normalized))

    def _find_cover_url(self) -> str | None:
        for el in self._data["media"]:
            if el["type"] == "IMAGE" and el["role"] == "MASTER":
                return el["url"]
        return None

    def parse(self, region: str) -> ParsedItem:
        name = self._data["name"]
        discounted_price = self._parse_price(self._data["price"]["discountedPrice"])
        default_price = self._parse_price(self._data["price"]["basePrice"])
        discount = self._parse_discount(self._data["price"]["discountText"])
        image_url = self._find_cover_url()
        return ParsedItem(
            name, discount, default_price, discounted_price, image_url or "", region
        )


class PsnParser(AbstractParser):
    def __init__(self, url: str, client: httpx.AsyncClient, limit: int | None = None):
        super().__init__(url, client, limit)
        self._is_last_page = False
        self.sem = asyncio.Semaphore(10)

    async def _load_page(self, url: str) -> BeautifulSoup:
        async with self.sem:
            resp = await self._client.get(url)
        return BeautifulSoup(resp.text, "html.parser")

    async def _get_last_page_num_with_page_size(self) -> tuple[int, int]:
        soup = await self._load_page(self._url)
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert isinstance(json_data_container, Tag) and json_data_container.string
        data = json.loads(json_data_container.string)["props"]["apolloState"]
        page_info = None
        for key, value in data.items():
            if key.lower().startswith("categorygrid"):
                page_info = value["pageInfo"]
        assert page_info
        return math.ceil(page_info["totalCount"] / page_info["size"]), page_info["size"]

    async def _parse_page(self, page_num: int) -> Sequence[ParsedItem]:
        url = self._url + str(page_num)
        soup = await self._load_page(url)
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert isinstance(json_data_container, Tag) and json_data_container.string
        data = json.loads(json_data_container.string)["props"]["apolloState"]
        items = []
        for key, value in data.items():
            if key.lower().startswith("product:"):
                region = key.split(":")[-1].split("-")[1]
                items.append(ItemParser(value).parse(region))
        return items

    async def parse(self) -> Sequence[ParsedItem]:
        if not self._url.endswith("/"):
            self._url += "/"
        last_page_num, page_size = await self._get_last_page_num_with_page_size()
        if self._limit is not None:
            last_page_num = math.ceil(self._limit / page_size)
        results: list[ParsedItem] = []
        coros = [self._parse_page(i) for i in range(1, last_page_num + 1)]
        res = await asyncio.gather(*coros)
        for items_list in res:
            results.extend(items_list)
        return results[: self._limit]
