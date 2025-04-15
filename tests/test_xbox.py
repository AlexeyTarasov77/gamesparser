import asyncio
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
    parser = XboxParser(httpx_client, PARSE_LIMIT)
    await check_parsed_unique_with_regions(parser, allowed_regions)


@pytest.mark.asyncio
async def test_xbox_with_details(httpx_client: httpx.AsyncClient):
    parser = XboxParser(httpx_client, PARSE_LIMIT)
    products = await parser.parse(("us", "eg"))
    coros = [parser.parse_item_details(product.url) for product in products]
    res = await asyncio.gather(*coros)
    print(
        "Succefully parsed %s out of %s"
        % (
            len([el for el in res if el is not None]),
            len(res),
        )
    )
