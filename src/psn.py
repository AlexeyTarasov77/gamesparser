from collections.abc import Sequence
import math
import re
import json

from bs4 import BeautifulSoup, Tag
import requests
from models import AbstractParser, ParsedItem, Price


class ItemParser:
    def __init__(self, item_tag):
        self._item_tag = item_tag

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
        normalized_value = value.replace(",", ".").replace(" ", "")
        return Price(value=float(normalized_value), currency_code=currency_code.strip())

    def _parse_discount(self, s: str) -> int:
        normalized = s.replace("%", "")
        return abs(int(normalized))

    # def parse(self, i: int) -> ParsedItem:
    #     details_section = self._item_tag.find(
    #         "section", class_="psw-product-tile__details psw-m-t-2"
    #     )
    #     name = details_section.find(
    #         "span", {"data-qa": f"ems-sdk-grid#productTile{i}#product-name"}
    #     ).string
    #     discount_badge: str = details_section.find(
    #         "span", class_="psw-badge__text psw-badge--none"
    #     )
    #     discount_badge = discount_badge.replace("%", "")
    #     discount = abs(int(discount_badge))
    #     discounted_price_container = details_section.find(
    #         "span",
    #         {"data-qa": f"ems-sdk-grid#productTile{i}#price#display-price"},
    #     )
    #     default_price_container = details_section.find(
    #         "s",
    #         {"data-qa": f"ems-sdk-grid#productTile{i}#price#price-strikethrough"},
    #     )
    #     discounted_price = self._parse_price(discounted_price_container)
    #     default_price = self._parse_price(default_price_container)
    #     image_url = self._item_tag.find(
    #         "img", {"data-qa": f"ems-sdk-grid#productTile{i}#game-art#image#preview"}
    #     ).src
    #     return ParsedItem(name, discount, default_price, discounted_price, image_url)
    #

    def _find_cover_url(self) -> str | None:
        for el in self._item_tag["media"]:
            if el["type"] == "IMAGE" and el["role"] == "MASTER":
                return el["url"]
        return None

    def parse(self) -> ParsedItem:
        name = self._item_tag["name"]
        discounted_price = self._parse_price(self._item_tag["price"]["discountedPrice"])
        default_price = self._parse_price(self._item_tag["price"]["basePrice"])
        discount = self._parse_discount(self._item_tag["price"]["discountText"])
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

    #
    # def _extract_items(self, soup: BeautifulSoup):
    #     items_container = soup.find("ul", class_="psw-grid-list psw-l-grid")
    #     assert isinstance(items_container, Tag)
    #     return items_container.find_all("li")
    #
    # def _get_last_page_num(self):
    #     int_regex = re.compile(r"\d+")
    #     soup = self._new_soup_for_page(self._url)
    #     items_per_page = len(self._extract_items(soup))
    #     total_items_container = soup.find(
    #         "div",
    #         class_="psw-t-body psw-c-t-2",
    #         # {"data-qa": "ems-sdk-active-filters-metadata"},
    #         string=int_regex,
    #     )
    #     print("container", total_items_container, total_items_container.string)
    #     assert (
    #         isinstance(total_items_container, Tag)
    #         and total_items_container.string is not None
    #     )
    #     total_items_match = int_regex.search(total_items_container.string)
    #     assert total_items_match
    #     return math.ceil(int(total_items_match.group()) / items_per_page)

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
        # items = [
        #     ItemParser(item).parse(i)
        #     for i, item in enumerate(self._extract_items(soup))
        # ]
        # return items

    def parse(self) -> Sequence[ParsedItem]:
        if not self._url.endswith("/"):
            self._url += "/"
        # last_page_num = self._get_last_page_num()
        curr_page_num = 1
        results: list[ParsedItem] = []
        while not self._is_last_page and (
            self._limit is None or len(results) < self._limit
        ):
            results.extend(self._parse_page(curr_page_num))
            curr_page_num += 1
        return results[: self._limit]
