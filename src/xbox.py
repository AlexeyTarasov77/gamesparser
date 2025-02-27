from datetime import datetime
from pytz import timezone
from typing import Any, NamedTuple, cast
import re
import requests
from bs4 import BeautifulSoup, Tag
from collections.abc import Sequence
from models import AbstractParser, ParsedItem, Price
from returns.maybe import Maybe


class ProductPricesWithDiscount(NamedTuple):
    default_price: Price
    discounted_price: Price
    discount: int


class _ItemParser:
    def __init__(self, item_tag):
        self._item_tag = item_tag

    def _parse_deal_until(self) -> datetime | None:
        deal_until_span = self._item_tag.find("span", string=re.compile("^Deal until:"))
        deal_until = None
        if deal_until_span:
            if not any(
                [
                    isinstance(deal_until_span, Tag),
                    getattr(deal_until_span, "string", None),
                ]
            ):
                raise ValueError("Got invalid html tag")
            date, time, tz_string = deal_until_span.string.split()[2:]  # type: ignore
            date_sep = "." if "." in date else "/"
            dt = datetime.strptime(
                date + " " + time, f"%m{date_sep}%d{date_sep}%Y %H:%M"
            )
            tz = timezone(tz_string)
            deal_until = tz.localize(dt)
        return deal_until

    def _parse_price(self) -> ProductPricesWithDiscount:
        price_regex = re.compile(
            r"(?:(\d[\d\s.,]*)\s*([A-Z]{2,3})|([A-Z]{2,3})\s*(\d[\d\s.,]*))"
        )
        maybe_price_tags = (
            Maybe.from_optional(
                cast(Tag | None, self._item_tag.find("div", class_="row"))
            )
            .bind_optional(lambda row: row.contents[1])
            .bind_optional(
                lambda el: cast(Tag | None, el.find_next("div", class_="row"))
            )
            .bind_optional(lambda row: row.find_all("div", class_="col-xs-4 col-sm-3"))
        )
        res = maybe_price_tags.unwrap()
        discount_container, price_container = res[0], res[2]
        assert isinstance(price_container, Tag) and isinstance(discount_container, Tag)
        price_tag = price_container.find(
            "span", style="white-space: nowrap", string=price_regex
        )
        assert isinstance(price_tag, Tag) and price_tag.string is not None
        price_match = price_regex.search(price_tag.string)
        assert price_match is not None
        currency_code = price_match.group(2).strip()
        discounted_price = Price(
            value=float(price_match.group(1).replace(",", ".")),
            currency_code=currency_code,
        )
        discount_regex = re.compile(r"(\d+)%")
        discount_tag = discount_container.find("span", string=discount_regex)
        assert isinstance(discount_tag, Tag) and discount_tag.string is not None
        discount_match = discount_regex.search(discount_tag.string)
        assert discount_match is not None
        discount = int(discount_match.group(1))
        default_price_value = (discounted_price.value * 100) // (100 - discount)
        default_price = Price(value=default_price_value, currency_code=currency_code)
        return ProductPricesWithDiscount(default_price, discounted_price, discount)

    def parse(self) -> ParsedItem:
        maybe_tag_a: Maybe[Any] = Maybe.from_optional(
            self._item_tag.find("div", class_="pull-left")
        ).bind_optional(lambda div: div.find("a"))
        tag_a = maybe_tag_a.unwrap()
        assert isinstance(tag_a, Tag)
        name = str(tag_a.get("title"))
        photo_tag = tag_a.find("img")
        if not photo_tag or not isinstance(photo_tag, Tag):
            raise ValueError("Tag with photo_url not found")
        image_url = str(photo_tag.get("src"))
        prices = self._parse_price()
        deal_until = self._parse_deal_until()
        return ParsedItem(
            name=name, image_url=image_url, deal_until=deal_until, **prices._asdict()
        )


class XboxParser(AbstractParser):
    def parse(self) -> Sequence[ParsedItem]:
        resp = requests.get(self._url, {"Accept": "text/html"})
        soup = BeautifulSoup(resp.text, "html.parser")
        maybe_products: Maybe[Sequence[ParsedItem]] = (
            Maybe.from_optional(soup.find("div", class_="content-wrapper"))
            .bind_optional(lambda el: cast(Tag, el).find("section", class_="content"))
            .bind_optional(
                lambda content: cast(Tag, content).find_all(
                    "div", class_="box-body comparison-table-entry", limit=self._limit
                )
            )
            .bind_optional(
                lambda products: [
                    _ItemParser(product_tag).parse() for product_tag in products
                ]
            )
        )
        return maybe_products.unwrap()
