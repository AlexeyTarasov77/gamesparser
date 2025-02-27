from datetime import datetime
from types import EllipsisType
from pytz import timezone
from typing import Any, Final, NamedTuple, cast
import re
from bs4 import BeautifulSoup, Tag
from collections.abc import Sequence
from models import AbstractParser, ParsedItem, Price
from returns.maybe import Maybe


class _ProductPricesWithDiscount(NamedTuple):
    default_price: Price
    discounted_price: Price
    discount: int


type _SkipType = EllipsisType
skip: Final = ...


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

    def _parse_price(self) -> _ProductPricesWithDiscount | _SkipType:
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
        if discount_tag is None:
            return skip
        assert isinstance(discount_tag, Tag) and discount_tag.string is not None
        discount_match = discount_regex.search(discount_tag.string)
        assert discount_match is not None
        discount = int(discount_match.group(1))
        if discount >= 100:
            return skip
        default_price_value = (discounted_price.value * 100) // (100 - discount)
        default_price = Price(value=default_price_value, currency_code=currency_code)
        return _ProductPricesWithDiscount(default_price, discounted_price, discount)

    def parse(self) -> ParsedItem | _SkipType:
        maybe_tag_a: Maybe[Any] = Maybe.from_optional(
            self._item_tag.find("div", class_="pull-left")
        ).bind_optional(lambda div: div.find("a"))
        tag_a = maybe_tag_a.unwrap()
        assert isinstance(tag_a, Tag)
        name = str(tag_a.get("title"))
        prices = self._parse_price()
        if prices is skip:
            return skip
        photo_tag = tag_a.find("img")
        if not photo_tag or not isinstance(photo_tag, Tag):
            raise ValueError("Tag with photo_url not found")
        image_url = str(photo_tag.get("src"))
        deal_until = self._parse_deal_until()
        return ParsedItem(
            name=name,
            image_url=image_url,
            deal_until=deal_until,
            **cast(_ProductPricesWithDiscount, prices)._asdict(),
        )


class XboxParser(AbstractParser):
    def _parse_items(self, tags) -> Sequence[ParsedItem]:
        skipped_count = 0
        res = []
        for tag in tags:
            parsed_item = _ItemParser(tag).parse()
            if parsed_item is skip:
                skipped_count += 1
            else:
                res.append(parsed_item)
        print("XBOX RES", "parsed", len(res), "skipped", skipped_count)
        return res

    async def parse(self) -> Sequence[ParsedItem]:
        resp = await self._client.get(self._url)
        soup = BeautifulSoup(resp.text, "html.parser")
        maybe_products: Maybe[Sequence[ParsedItem]] = (
            Maybe.from_optional(soup.find("div", class_="content-wrapper"))
            .bind_optional(lambda el: cast(Tag, el).find("section", class_="content"))
            .bind_optional(
                lambda content: cast(Tag, content).find_all(
                    "div", class_="box-body comparison-table-entry", limit=self._limit
                )
            )
            .bind_optional(lambda products: self._parse_items(products))
        )
        return maybe_products.unwrap()
