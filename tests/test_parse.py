from collections.abc import Sequence
import pytest
import httpx

from gamesparser.models import AbstractParser
from gamesparser.psn import PsnParser
from gamesparser.xbox import XboxParser
import pytest_asyncio


@pytest_asyncio.fixture
async def httpx_client():
    async with httpx.AsyncClient() as client:
        yield client


async def _check_parsed_unique_with_regions(
    parser: AbstractParser, allowed_regions: Sequence[str]
):
    allowed_regions = [region.lower() for region in allowed_regions]
    res = await parser.parse()
    checked_names: list[str] = []
    for obj in res:
        assert obj not in checked_names
        for region in obj.prices:
            assert region.lower() in allowed_regions
        checked_names.append(obj.name)


@pytest.mark.parametrize(
    "allowed_regions", [("us", "tr", "ar"), ("us", "eg"), ("tr", "ar")]
)
@pytest.mark.asyncio
async def test_xbox(httpx_client: httpx.AsyncClient, allowed_regions: tuple[str, ...]):
    parser = XboxParser(allowed_regions, httpx_client)
    await _check_parsed_unique_with_regions(parser, allowed_regions)


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
    parser = PsnParser(allowed_regions, httpx_client, 50)
    await _check_parsed_unique_with_regions(parser, allowed_regions)
