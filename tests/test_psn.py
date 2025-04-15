import httpx
import asyncio
import pytest

from gamesparser.psn import PsnParser
from tests.conftest import PARSE_LIMIT, check_parsed_unique_with_regions


@pytest.mark.parametrize(
    "allowed_regions",
    [
        ("ua", "tr"),
        ("tr",),
        ("ua",),
    ],
)
@pytest.mark.asyncio
async def test_psn(httpx_client: httpx.AsyncClient, allowed_regions: tuple[str, ...]):
    parser = PsnParser(httpx_client, PARSE_LIMIT)
    await check_parsed_unique_with_regions(parser, allowed_regions)


@pytest.mark.asyncio
async def test_psn_with_details(httpx_client: httpx.AsyncClient):
    parser = PsnParser(httpx_client, PARSE_LIMIT)
    products = await parser.parse(("ua",))
    for product in products:
        await asyncio.sleep(1)  # use timeout to avoid blocking
        await parser.parse_item_details(product.url)
