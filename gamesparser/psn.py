import asyncio
from collections.abc import Iterable, Mapping
from datetime import datetime
import logging
import re
import random
import math
import json

from bs4 import BeautifulSoup, Tag
import httpx
import pytz
from .models import AbstractParser, Price, PsnItemDetails, PsnParsedItem


class _ItemDetailsParser:
    def __init__(self, item_tag):
        self._item_tag = item_tag

    def _parse_deal_until(self) -> datetime | None:
        pattern = re.compile(
            r"(?P<day>\d+)(?P<sep>\.|\/)(?P<month>[1-9]|1[0-2])(?:\.|\/)(?P<year>\d{4})\s(?:(?P<hour>\d{2}):(?P<min>\d{2}))\s(?P<format>AM|PM)?\s?(?P<tz>\w+)"
        )
        span_tag = self._item_tag.find("span", string=pattern)
        if span_tag is None:
            # product is not on discount anymore
            return None
        match = pattern.search(span_tag.string)
        assert match is not None
        tzname = match.group("tz").lower()
        if tzname == "CEST":
            tzname = "Europe/Paris"
        tz = pytz.timezone(tzname)
        # remove timezone (last part)
        date_string = match.group()[: match.group().rfind(" ")]
        is_12_h = match.group("format") is not None
        sep = match.group("sep")
        date_format = f"%d{sep}%m{sep}%Y"
        hour_format = "%H:%M"
        if is_12_h:
            hour_format = "%I:%M %p"
        dt = datetime.strptime(date_string, date_format + " " + hour_format)
        dt = tz.localize(dt)
        if tzname == "utc":
            return dt
        return dt.astimezone(pytz.utc)

    def _parse_description(self) -> str:
        p_tag = self._item_tag.find(
            "p", attrs={"data-qa": "mfe-game-overview#description"}
        )
        assert p_tag is not None
        return p_tag.decode_contents()

    def parse(self) -> PsnItemDetails:
        return PsnItemDetails(self._parse_description(), self._parse_deal_until())


class _ItemPartialParser:
    def __init__(self, data: Mapping):
        self._data = data

    def _parse_price(self) -> Price:
        s = self._data["price"]["discountedPrice"]
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
        return Price(discounted_value=float(normalized_value), currency_code=curr)

    def _parse_discount(self) -> int:
        s: str = self._data["price"]["discountText"]  # eg.: -60%
        assert s is not None
        return abs(int(s.replace("%", "")))

    def _parse_preview_and_media(self) -> tuple[str, list[str]]:
        preview: str | None = None
        other_media: list[dict] = []
        for el in self._data["media"]:
            if el["role"] == "MASTER":
                preview = el["url"]
            else:
                other_media.append(el)
        if preview is None:
            preview = str(
                random.choice(
                    [el["url"] for el in other_media if el["type"] == "IMAGE"]
                )
            )
        return preview, [el["url"] for el in other_media]

    def parse(self, region: str, item_url: str) -> PsnParsedItem:
        preview_img_url, media = self._parse_preview_and_media()
        return PsnParsedItem(
            id=self._data["id"],
            name=self._data["name"],
            url=item_url,
            discount=self._parse_discount(),
            prices={region: self._parse_price()},
            preview_img_url=preview_img_url,
            media=media,
            platforms=self._data["platforms"],
            with_sub=self._data["price"]["isTiedToSubscription"],
        )


class PsnParser(AbstractParser[PsnItemDetails]):
    """Parses sales from psn official website. CAUTION: there might be products which looks absolutely the same but have different discount and prices.
    That's due to the fact that on psn price depends on product platform (ps4, ps5, etc). Such products aren't handled in parser."""

    _url_prefix = "https://store.playstation.com/{region}"

    def __init__(
        self,
        client: httpx.AsyncClient,
        logger: logging.Logger | None = None,
        max_concurrent_req: int = 5,
    ):
        super().__init__(client, logger)
        self._sem = asyncio.Semaphore(max_concurrent_req)
        self._items_mapping: dict[str, PsnParsedItem] = {}
        self._curr_locale: str | None = None
        self._skipped_count = 0
        self._cookies = None

    def _build_curr_url(self, page_num: int | None = None) -> str:
        assert self._curr_locale is not None
        url = (
            self._url_prefix.format(region=self._curr_locale)
            + "/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
        )
        if page_num is not None:
            url += str(page_num)
        return url

    def _build_product_url(self, product_id: str) -> str:
        assert self._curr_locale is not None
        return (
            self._url_prefix.format(region=self._curr_locale) + "/product/" + product_id
        )

    async def _load_page(self, url: str, **kwargs) -> BeautifulSoup:
        async with self._sem:
            resp = await self._client.get(
                url,
                timeout=None,
                cookies=self._cookies,
                headers={
                    "accept": "application/json",
                    "accept-encoding": "gzip, deflate, br, zstd",
                    "accept-language": "ru-UA",
                    "content-type": "application/json",
                    "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
                },
                **kwargs,
            )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise Exception(
                    "Rate limit exceed! Please wait some time and try again later"
                ) from e
            raise

        if self._cookies:
            self._cookies.update(resp.cookies)
        else:
            self._cookies = resp.cookies
        return BeautifulSoup(resp.text, "html.parser")

    def _extract_json(self, soup: BeautifulSoup) -> dict:
        json_data_container = soup.find("script", id="__NEXT_DATA__")
        assert isinstance(json_data_container, Tag) and json_data_container.string
        return json.loads(json_data_container.string)["props"]["apolloState"]

    async def _get_last_page_num_with_page_size(self) -> tuple[int, int]:
        soup = await self._load_page(self._build_curr_url())
        data = self._extract_json(soup)
        page_info = None
        for key, value in data.items():
            if key.lower().startswith("categorygrid"):
                page_info = value["pageInfo"]
        assert page_info, "Failed to find page_info in json data"
        return math.ceil(page_info["totalCount"] / page_info["size"]), page_info["size"]

    async def _parse_single_page(self, page_num: int):
        url = self._build_curr_url(page_num)
        soup = await self._load_page(url)
        self._logger.info("Page %d loaded", page_num)
        data = self._extract_json(soup)
        soup.decompose()
        for key, value in data.items():
            if not key.lower().startswith("product:") or value["price"]["isFree"]:
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
        self._logger.info("Page %d succesfully parsed", page_num)

    async def _parse_all_for_region(self, locale: str, limit: int | None):
        self._curr_locale = locale
        last_page_num, page_size = await self._get_last_page_num_with_page_size()
        if limit is not None:
            last_page_num = math.ceil(limit / page_size)
        self._logger.info("Parsing up to %d page", last_page_num)
        coros = [self._parse_single_page(i) for i in range(1, last_page_num + 1)]
        await asyncio.gather(*coros)

    async def parse_item_details(self, url: str) -> PsnItemDetails | None:
        soup = await self._load_page(url, follow_redirects=True)
        item_container = soup.find("main")
        try:
            parsed = _ItemDetailsParser(item_container).parse()
            if parsed.deal_until is None:
                self._logger.warning(
                    "Product under url: %s is not discounted anymore", url
                )
            return parsed
        except AssertionError as e:
            self._logger.warning(
                "Failed to parse product for url: %s. Error: %s", url, e, exc_info=True
            )
            return None

    async def parse(
        self, regions: Iterable[str], limit: int | None = None
    ) -> list[PsnParsedItem]:
        regions = super()._normalize_regions(regions)
        lang_mapping = {"ua": "ru"}
        locales = [f"{lang_mapping.get(region, 'en')}-{region}" for region in regions]
        [await self._parse_all_for_region(locale, limit) for locale in locales]
        products = list(self._items_mapping.values())
        if not products and not self._skipped_count:
            self._logger.warning("Couldn't find any products for provided regions")
            return []
        self._logger.info(
            "Parsed: %s items, skipped: %d (%.1f%%)",
            len(products),
            self._skipped_count,
            self._skipped_count / (len(products) + self._skipped_count) * 100,
        )
        return products[:limit]
