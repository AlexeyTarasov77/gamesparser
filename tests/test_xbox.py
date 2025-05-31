import asyncio
from urllib.parse import urlparse
import httpx
import pytest

from gamesparser.xbox import XboxParser
from tests.conftest import PARSE_LIMIT, check_parsed_unique_with_regions


@pytest.mark.parametrize(
    "allowed_regions",
    [("tr", "ar", "us"), ("eg",), ("us", "ar")],
)
@pytest.mark.asyncio
async def test_xbox(httpx_client: httpx.AsyncClient, allowed_regions: tuple[str, ...]):
    parser = XboxParser(httpx_client)
    products = await parser.parse(allowed_regions, PARSE_LIMIT)
    sample_product = products[0]
    assert not urlparse(sample_product.preview_img_url).query
    await check_parsed_unique_with_regions(allowed_regions, products)


@pytest.mark.asyncio
async def test_xbox_with_details(httpx_client: httpx.AsyncClient):
    parser = XboxParser(httpx_client)
    products = await parser.parse(("us", "eg"), PARSE_LIMIT)
    coros = [parser.parse_item_details(product.url) for product in products]
    details = await asyncio.gather(*coros)
    # check that details of at least half of products were succesfully parsed
    assert len([obj for obj in details if obj is not None]) > len(products) * 0.5
