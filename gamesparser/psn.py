import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime
import logging
import re
import math
import json

from bs4 import BeautifulSoup, Tag
import httpx
import pytz
from .models import AbstractParser, Price, PsnItemDetails, PsnParsedItem


class _ItemDetailsParser:
    def __init__(self, item_tag):
        self._item_tag = item_tag

    def _parse_deal_until(self) -> datetime:
        pattern = re.compile(
            r"(?<day>\d+)(?:\.|\/)(?<month>[1-9]|1[0-2])(?:\.|\/)(?<year>\d{4})\s(?:(?<hour>\d{2}):(?<min>\d{2}))\s(?<tz>\w+)$"
        )
        span_tag = self._item_tag.find("span", string=pattern)
        match = pattern.search(span_tag.string)
        assert match is not None
        tzname = match.group("tz").lower()
        if tzname == "CEST":
            tzname = "Europe/Paris"
        tz = pytz.timezone(tzname)
        dt = datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("min")),
        )
        dt = tz.localize(dt)
        if tzname == "utc":
            return dt
        return dt.astimezone(pytz.utc)

    def _parse_description(self) -> str:
        p_tag = self._item_tag.find(
            "p", attrs={"data-qa": "mfe-game-overview#description"}
        )
        assert p_tag is not None
        return p_tag.string

    def parse(self) -> PsnItemDetails:
        return PsnItemDetails(self._parse_description(), self._parse_deal_until())


class _ItemPartialParser:
    def __init__(self, data: Mapping):
        self._data = data

    def _parse_price(self) -> Price:
        s = self._data["price"]["basePrice"]
        price_regex = re.compile(
            r"(?:(?P<price>\d[\d\s.,]*)\s*([A-Z]{2,3})|([A-Z]{2,3})\s*(\d[\d\s.,]*))"
        )
        price_match = price_regex.search(s)
        assert price_match is not None
        # may be 2 different variations of price form on page
        value, currency_code = None, None
        if price_match.group(1) is not None:
            value, currency_code = price_match.group(1, 2)
        elif price_match.group(3) is not None:
            value, currency_code = price_match.group(4, 3)
        assert value is not None and currency_code is not None, "Unable to parse price"
        normalized_value = (
            value.replace(".", "")
            .replace(",", ".")
            .replace(" ", "")
            .replace("\xa0", "")
        )
        curr = currency_code.strip()
        if curr == "TL":
            curr = "TRY"  # change abbreviated to official currency code for turkish
        return Price(value=float(normalized_value), currency_code=curr)

    def _parse_discount(self) -> int:
        s: str = self._data["price"]["discountText"]  # eg.: -60%
        return abs(int(s.replace("%", "")))

    def _find_cover_url(self) -> str | None:
        for el in self._data["media"]:
            if el["type"] == "IMAGE" and el["role"] == "MASTER":
                return el["url"]
        return None

    def parse(self, region: str, item_url: str) -> PsnParsedItem:
        name = self._data["name"]
        base_price = self._parse_price()
        discount = self._parse_discount()
        image_url = self._find_cover_url()
        return PsnParsedItem(
            name,
            item_url,
            discount,
            {region: base_price},
            image_url or "",
            self._data["platforms"],
            self._data["price"]["isTiedToSubscription"],
        )


class PsnParser(AbstractParser):
    """Parses sales from psn official website. CAUTION: there might be products which looks absolutely the same but have different discount and prices.
    That's due to the fact that on psn price depends on product platform (ps4, ps5, etc). Such products aren't handled in parser."""

    # _url = "httls://store.playstation.com/{region}/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    _url_prefix = "https://store.playstation.com/{region}"

    def __init__(
        self,
        parse_regions: Sequence[str],
        client: httpx.AsyncClient,
        limit: int | None = None,
        max_concurrent_req: int = 5,
        logger: logging.Logger | None = None,
    ):
        super().__init__(parse_regions, client, limit, logger)
        lang_to_region_mapping = {"tr": "en", "ua": "ru"}
        self._regions = {
            f"{lang_to_region_mapping.get( region, "en" )}-{region}"
            for region in parse_regions
        }
        self._sem = asyncio.Semaphore(max_concurrent_req)
        self._items_mapping: dict[str, PsnParsedItem] = {}
        self._curr_region: str | None = None
        self._skipped_count = 0

    def _build_curr_url(self, page_num: int | None = None) -> str:
        assert self._curr_region is not None
        url = (
            self._url_prefix.format(region=self._curr_region)
            + "/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
        )
        if page_num is not None:
            url += str(page_num)
        return url

    def _build_product_url(self, product_id: str) -> str:
        assert self._curr_region is not None
        return (
            self._url_prefix.format(region=self._curr_region) + "/product/" + product_id
        )

    async def _load_page(self, url: str) -> BeautifulSoup:
        async with self._sem:
            resp = await self._client.get(url, timeout=None)
        return BeautifulSoup(resp.text, "html.parser")

    async def _get_last_page_num_with_page_size(self) -> tuple[int, int]:
        soup = await self._load_page(self._build_curr_url())
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert (
            isinstance(json_data_container, Tag) and json_data_container.string
        ), "Rate limit exceed! Please wait some time and try again later"
        data = json.loads(json_data_container.string)["props"]["apolloState"]
        page_info = None
        for key, value in data.items():
            if key.lower().startswith("categorygrid"):
                page_info = value["pageInfo"]
        assert page_info
        return math.ceil(page_info["totalCount"] / page_info["size"]), page_info["size"]

    async def _parse_single_page(self, page_num: int):
        self._logger.info("Parsing page %d", page_num)
        url = self._build_curr_url(page_num)
        soup = await self._load_page(url)
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert isinstance(json_data_container, Tag) and json_data_container.string
        data = json.loads(json_data_container.string)["props"]["apolloState"]
        for key, value in data.items():
            if not key.lower().startswith("product:") or value["isFree"]:
                continue
            _, product_id, locale = key.split(":")
            region = locale.split("-")[1]
            try:
                parsed_product = _ItemPartialParser(value).parse(
                    region, self._build_product_url(product_id)
                )
            except AssertionError as e:
                self._logger.info(
                    "Failed to parse product: %s. KEY: %s, VALUE: %s", e, key, value
                )
                self._skipped_count += 1
                continue
            if product_id in self._items_mapping:
                self._items_mapping[product_id].prices.update(parsed_product.prices)
            else:
                self._items_mapping[product_id] = parsed_product
        self._logger.info("Page %d parsed", page_num)

    async def _parse_all_for_region(self, region: str):
        self._curr_region = region
        last_page_num, page_size = await self._get_last_page_num_with_page_size()
        if self._limit is not None:
            last_page_num = math.ceil(self._limit / page_size)
        self._logger.info("Parsing up to %d page", last_page_num)
        coros = [self._parse_single_page(i) for i in range(1, last_page_num + 1)]
        await asyncio.gather(*coros)

    async def parse_item_details(
        self, url: str | None = None, product_id: str | None = None
    ) -> PsnItemDetails:
        assert url or product_id, "whether url or product_id must be supplied"
        url = url or self._build_product_url(str(product_id))
        soup = await self._load_page(url)
        item_container = soup.find("main")
        return _ItemDetailsParser(item_container).parse()

    async def parse(self) -> list[PsnParsedItem]:
        [await self._parse_all_for_region(region) for region in self._regions]
        products = list(self._items_mapping.values())
        self._logger.info(
            "Parsed: %s items, skipped: %d (%.1f)",
            len(products),
            self._skipped_count,
            self._skipped_count / len(products) * 100,
        )
        return products[: self._limit]
