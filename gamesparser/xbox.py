from datetime import datetime
from pytz import timezone
from typing import cast
import re
from bs4 import BeautifulSoup, Tag
from collections.abc import Sequence
from .models import AbstractParser, Price, XboxItemDetails, XboxParsedItem
from returns.maybe import Maybe


class _ItemDetailsParser:
    def __init__(self, item_tag):
        self._item_tag = item_tag

    def _parse_description(self) -> str:
        tag = self._item_tag.find(
            "div", class_="Description-module__descriptionContainer___hlY8t"
        )
        return next(tag.children).string

    def _parse_platforms(self) -> list[str]:
        platforms_container = self._item_tag.find(
            "ul", class_="FeaturesList-module__wrapper___KIw42"
        )
        return [platform.string for platform in platforms_container.children]

    def parse(self) -> XboxItemDetails:
        return XboxItemDetails(self._parse_description(), self._parse_platforms())


class _ItemPartialParser:
    def __init__(self, item_tag, parse_regions: Sequence[str] | set[str]):
        self._item_tag = item_tag
        self._parse_regions = parse_regions

    def _parse_deal_until(self) -> datetime | None:
        deal_until_span = self._item_tag.find("span", string=re.compile("^Deal until:"))
        if not deal_until_span:
            return None
        date, time, tz_string = deal_until_span.string.split()[2:]  # type: ignore
        sep = "." if "." in date else "/"
        dt = datetime.strptime(date + " " + time, f"%m{sep}%d{sep}%Y %H:%M")
        tz = timezone(tz_string)
        deal_until = tz.localize(dt)
        return deal_until

    def _parse_price_mapping(self, containers, discount: int) -> dict[str, Price]:
        price_mapping: dict[str, Price] = {}
        price_regex = re.compile(r"(\d+(?:\.\d+)?)\s([A-Z]{2,3})")
        for tag in containers:
            region_tag = tag.find("img", class_="flag")
            assert isinstance(region_tag, Tag)
            region = str(region_tag["title"]).lower()
            if region not in self._parse_regions:
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
            price_mapping[region] = base_price
        assert price_mapping, "Failed to parse any prices for item"
        return price_mapping

    def _parse_discount(self, discount_container) -> tuple[int, bool]:
        discount_regex = re.compile(r"^(\d+)%(\s\(\w+\))?$")
        discount_tag = discount_container.find("span", string=discount_regex)
        assert isinstance(discount_tag, Tag) and discount_tag.string is not None
        discount_match = discount_regex.search(discount_tag.string)
        assert discount_match is not None
        with_gp = discount_match.group(2) is not None
        discount = int(discount_match.group(1))
        return discount, with_gp

    def _parse_tag_link(self) -> Tag:
        maybe_tag_a: Maybe[Tag] = Maybe.from_optional(
            self._item_tag.find("div", class_="pull-left")
        ).bind_optional(lambda div: div.find("a"))
        tag_a = maybe_tag_a.unwrap()
        return tag_a

    def _calc_base_price(self, discounted_price: Price, discount: int) -> Price:
        base_price_value = round((discounted_price.value * 100) / (100 - discount), 2)
        base_price = Price(
            value=base_price_value, currency_code=discounted_price.currency_code
        )
        return base_price

    def parse(self) -> XboxParsedItem:
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
        discount, with_gp = self._parse_discount(discount_container)
        assert discount < 100, "Products with discount >= 100 are being skipped"
        tag_link = self._parse_tag_link()
        name = str(tag_link.get("title"))
        photo_tag = tag_link.find("img")
        assert isinstance(photo_tag, Tag)
        image_url = str(photo_tag.get("src"))
        item_url = str(tag_link.get("href"))
        deal_until = self._parse_deal_until()
        price_mapping = self._parse_price_mapping(price_containers, discount)
        return XboxParsedItem(
            name=name,
            item_url=item_url,
            discount=discount,
            with_gp=with_gp,
            prices=price_mapping,
            image_url=image_url,
            deal_until=deal_until,
        )


class XboxParser(AbstractParser):
    _url_prefix = "https://www.xbox-now.com/ru"

    def _parse_items(self, tags) -> list[XboxParsedItem]:
        skipped_count = 0
        items = []
        for tag in tags:
            try:
                parsed_item = _ItemPartialParser(tag, self._regions).parse()
            except AssertionError:
                skipped_count += 1
                continue
            items.append(parsed_item)
        self._logger.info(
            "Parsed: %s items, skipped: %d (%.1f)",
            len(items),
            skipped_count,
            skipped_count / len(items) * 100,
        )
        return items

    async def _load_page(self, path: str) -> BeautifulSoup:
        resp = await self._client.get(self._url_prefix + path)
        return BeautifulSoup(resp.text, "html.parser")

    async def parse_item_details(self, url: str) -> XboxItemDetails:
        soup = await self._load_page(url)
        xbox_link_tag = soup.find("a", attrs={"rel": "nofollow noopener"})
        assert isinstance(xbox_link_tag, Tag)
        link = str(xbox_link_tag.get("href"))
        soup = await self._load_page(link.replace("en-us", "ru-RU"))
        item_container = soup.find("div", role="main", id="PageContent")
        return _ItemDetailsParser(item_container).parse()

    async def parse(self) -> list[XboxParsedItem]:
        soup = await self._load_page("/deal-list")
        maybe_products: Maybe[list[XboxParsedItem]] = (
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
