from collections.abc import Sequence
import re
import json

from bs4 import BeautifulSoup, Tag
import requests
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

    def parse(self) -> ParsedItem:
        name = self._data["name"]
        discounted_price = self._parse_price(self._data["price"]["discountedPrice"])
        default_price = self._parse_price(self._data["price"]["basePrice"])
        discount = self._parse_discount(self._data["price"]["discountText"])
        image_url = self._find_cover_url()
        return ParsedItem(
            name, discount, default_price, discounted_price, image_url or ""
        )


class PsnParser(AbstractParser):
    def __init__(self, url: str, limit: int | None = None):
        super().__init__(url, limit)
        self._offset = 0
        self._is_last_page = False
        self._page_size = 24

    def _new_soup_for_page(self, url: str) -> BeautifulSoup:
        resp = requests.get(url, {"Accept": "text/html"})
        return BeautifulSoup(resp.text, "html.parser")

    def _parse_page(self, page_num: int) -> Sequence[ParsedItem]:
        url = self._url + str(page_num)
        soup = self._new_soup_for_page(url)
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert isinstance(json_data_container, Tag) and json_data_container.string
        data = json.loads(json_data_container.string)["props"]["apolloState"]
        page_info = None
        items = []
        for key, value in data.items():
            if key.lower().startswith("categorygrid"):
                page_info = value["pageInfo"]
            elif key.lower().startswith("product:"):
                items.append(ItemParser(value).parse())
        assert page_info is not None
        self._is_last_page = bool(page_info["isLast"])
        return items

    def parse(self) -> Sequence[ParsedItem]:
        if not self._url.endswith("/"):
            self._url += "/"
        curr_page_num = 1
        results: list[ParsedItem] = []
        while not self._is_last_page and (
            self._limit is None or len(results) < self._limit
        ):
            results.extend(self._parse_page(curr_page_num))
            curr_page_num += 1
        return results[: self._limit]
