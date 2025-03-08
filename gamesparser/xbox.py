from datetime import datetime
from pytz import timezone
from typing import Any, cast
import re
from bs4 import BeautifulSoup, Tag
from collections.abc import Sequence
from .models import AbstractParser, ParsedItem, ParsedPriceByRegion, Price
from returns.maybe import Maybe


class _ItemParser:
    def __init__(self, item_tag, extra_regions: Sequence[str] | set[str]):
        self._item_tag = item_tag
        self._extra_regions = extra_regions

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

    def _parse_price_mapping(
        self, containers, discount: int
    ) -> dict[str, ParsedPriceByRegion]:
        price_mapping: dict[str, ParsedPriceByRegion] = {}
        price_regex = re.compile(r"(\d+(?:\.\d+)?)\s([A-Z]{2,3})")
        for tag in containers:
            region_tag = tag.find("img", class_="flag")
            assert isinstance(region_tag, Tag)
            region = str(region_tag["title"]).lower()
            if region != "us" and region not in self._extra_regions:
                continue
            price_tag = tag.find(
                "span", style="white-space: nowrap", string=price_regex
            )
            assert isinstance(price_tag, Tag) and price_tag.string is not None
            price_match = price_regex.search(price_tag.string)
            assert price_match is not None
            currency_code = price_match.group(2).strip()
            discounted_price = Price(
                value=float(price_match.group(1)),
                currency_code=currency_code,
            )
            base_price = self._calc_base_price(discounted_price, discount)
            price_mapping[region] = ParsedPriceByRegion(base_price, discounted_price)
        assert price_mapping, "Failed to parse any prices for item"
        return price_mapping

    def _parse_discount(self, discount_container) -> tuple[int, bool] | None:
        discount_regex = re.compile(r"^(\d+)%(\s\(\w+\))?$")
        discount_tag = discount_container.find("span", string=discount_regex)
        if discount_tag is None:
            return None
        assert isinstance(discount_tag, Tag) and discount_tag.string is not None
        discount_match = discount_regex.search(discount_tag.string)
        assert discount_match is not None
        with_gp = discount_match.group(2) is not None
        discount = int(discount_match.group(1))
        return discount, with_gp

    def _parse_name_and_image(self) -> tuple[str, str]:
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
        return name, image_url

    def _calc_base_price(self, discounted_price: Price, discount: int) -> Price:
        base_price_value = round((discounted_price.value * 100) / (100 - discount), 2)
        base_price = Price(
            value=base_price_value, currency_code=discounted_price.currency_code
        )
        return base_price

    def parse(self) -> ParsedItem:
        maybe_row_tags = (
            Maybe.from_optional(
                cast(Tag | None, self._item_tag.find("div", class_="row"))
            )
            .bind_optional(lambda row: row.contents[1])
            .bind_optional(
                lambda el: cast(Tag | None, el.find_next("div", class_="row"))
            )
            .bind_optional(lambda row: row.find_all("div", class_="col-xs-4 col-sm-3"))
        )
        res = maybe_row_tags.unwrap()
        discount_container, price_containers = (
            res[0],
            res[1:],
        )
        discount_info = self._parse_discount(discount_container)
        assert discount_info is not None
        discount, with_gp = discount_info
        assert discount < 100
        name, image_url = self._parse_name_and_image()
        deal_until = self._parse_deal_until()
        price_mapping = self._parse_price_mapping(price_containers, discount)
        return ParsedItem(
            name=name,
            discount=discount,
            with_gp=with_gp,
            prices=price_mapping,
            image_url=image_url,
            deal_until=deal_until,
        )


class XboxParser(AbstractParser):
    _url = "https://www.xbox-now.com/en/deal-list"

    def _parse_items(self, tags) -> Sequence[ParsedItem]:
        skipped_count = 0
        res = []
        for tag in tags:
            try:
                parsed_item = _ItemParser(tag, self._regions).parse()
            except AssertionError:
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
