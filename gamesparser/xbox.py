from datetime import datetime
from urllib.parse import urljoin, urlparse
import httpx
from pytz import timezone
from typing import cast
import re
from bs4 import BeautifulSoup, Tag
from collections.abc import Iterable
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
        return [platform.text for platform in platforms_container.children]

    def _parse_gallery(self) -> list[str]:
        # TODO: Use selenium to parse gallery, because gallery is loaded by js script
        return []
        # gallery_list = self._item_tag.find(
        #     "ol", {"role": "none"}, class_="ItemsSlider-module__wrapper___nAi6y"
        # )
        # if gallery_list is None:
        #     print("GALLERY NOT FOUND")
        #     return []
        # urls = []
        # for li in gallery_list.children:
        #     # print("LIST ITEM", li.get("role"), li)
        #     if li.get("role") != "none":
        #         continue
        #     img = li.find("img")
        #     urls.append(img.get("src"))
        # return urls

    def parse(self) -> XboxItemDetails:
        return XboxItemDetails(
            self._parse_description(), self._parse_platforms(), self._parse_gallery()
        )


class _ItemPartialParser:
    def __init__(self, item_tag, regions: Iterable[str]):
        self._item_tag = item_tag
        self._regions = regions

    def _parse_deal_until(self) -> datetime | None:
        deal_until_span = self._item_tag.find("span", string=re.compile("^Deal until:"))
        if not deal_until_span:
            return None
        date, time, tz_string = deal_until_span.string.split()[2:]  # type: ignore
        sep = "." if "." in date else "/"
        # change to %d{sep}%m{sep}%Y %H:%M format if parsing from ru website version
        dt = datetime.strptime(date + " " + time, f"%m{sep}%d{sep}%Y %H:%M")
        tz = timezone(tz_string)
        deal_until = tz.localize(dt)
        return deal_until

    def _parse_price_mapping(self, containers) -> dict[str, Price]:
        price_mapping: dict[str, Price] = {}
        price_regex = re.compile(r"(\d+(?:\.\d+)?)\s([A-Z]{2,3})")
        for tag in containers:
            region_tag = tag.find("img", class_="flag")
            assert isinstance(region_tag, Tag)
            region = str(region_tag["title"]).lower()
            if region not in self._regions:
                continue
            price_tag = tag.find(
                "span", style="white-space: nowrap", string=price_regex
            )
            assert isinstance(price_tag, Tag) and price_tag.string is not None
            price_match = price_regex.search(price_tag.string)
            assert price_match is not None
            currency_code = price_match.group(2).strip()
            discounted_price = Price(
                discounted_value=float(price_match.group(1)),
                currency_code=currency_code,
            )
            price_mapping[region] = discounted_price
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
        # normalize image url by removing query params specifier width, height, etc..
        image_url = urljoin(image_url, urlparse(image_url).path)
        item_url = str(tag_link.get("href"))
        item_id = item_url.split("/")[5]
        deal_until = self._parse_deal_until()
        price_mapping = self._parse_price_mapping(price_containers)
        return XboxParsedItem(
            id=item_id,
            name=name,
            url=item_url,
            discount=discount,
            with_sub=with_gp,
            prices=price_mapping,
            preview_img_url=image_url,
            deal_until=deal_until,
        )


class XboxParser(AbstractParser[XboxItemDetails]):
    _url_prefix = "https://www.xbox-now.com/en"

    def _parse_items(self, tags) -> list[XboxParsedItem]:
        skipped_count = 0
        products = []
        i = 1
        for tag in tags:
            i += 1
            try:
                parsed_item = _ItemPartialParser(tag, self._regions).parse()
            except AssertionError as e:
                self._logger.info("Failed to parse product %s: %s", e, i)
                skipped_count += 1
                continue
            products.append(parsed_item)
        if not products and not skipped_count:
            self._logger.warning("Couldn't find any products for provided regions")
            return []
        self._logger.info(
            "Parsed: %s items, skipped: %d (%.1f%%)",
            len(products),
            skipped_count,
            skipped_count / (len(products) + skipped_count) * 100,
        )
        return products

    async def _load_page(self, path: str, **kwargs) -> BeautifulSoup:
        url = self._url_prefix + path if path.startswith("/") else path
        resp = await self._client.get(url, **kwargs)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup

    async def parse_item_details(self, url: str) -> XboxItemDetails | None:
        soup = await self._load_page(url)
        xbox_link_tag = soup.find(
            "a",
            attrs={
                "rel": "nofollow noopener",
                "target": "_blank",
                "title": re.compile(r".+"),
            },
        )
        assert isinstance(xbox_link_tag, Tag)
        self._logger.info("Parsing details for item: %s", xbox_link_tag.get("title"))
        next_url = str(xbox_link_tag.get("href"))
        try:
            soup = await self._load_page(
                next_url.replace("en-us", "ru-RU"), follow_redirects=True
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self._logger.warning("Details page for url: %s not found", url)
                return None
            self._logger.warning(
                "Failed to parse product details due to request failure. Url: %s, status: %d",
                url,
                e.response.status_code,
            )
            raise
        item_container = soup.find("div", role="main", id="PageContent")
        try:
            assert item_container, "Page content wasn't found"
            return _ItemDetailsParser(item_container).parse()
        except AssertionError as e:
            self._logger.warning(
                "Failed to parse product for url: %s. Error: %s", url, e, exc_info=True
            )
            return None

    async def parse(
        self, regions: Iterable[str], limit: int | None = None
    ) -> list[XboxParsedItem]:
        self._regions = super()._normalize_regions(regions)
        soup = await self._load_page("/deal-list")
        maybe_products: Maybe[list[XboxParsedItem]] = (
            Maybe.from_optional(soup.find("div", class_="content-wrapper"))
            .bind_optional(lambda el: cast(Tag, el).find("section", class_="content"))
            .bind_optional(
                lambda content: cast(Tag, content).find_all(
                    "div", class_="box-body comparison-table-entry", limit=limit
                )
            )
            .bind_optional(lambda products: self._parse_items(products))
        )
        return maybe_products.unwrap()
