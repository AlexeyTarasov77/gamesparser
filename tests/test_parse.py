from collections.abc import Sequence
import pytest
import httpx

from constants import (
    PSN_PARSE_REGIONS,
    PSN_SALES_URL,
    XBOX_PARSE_REGIONS,
    XBOX_SALES_URL,
)
from models import AbstractParser
from psn import PsnParser
from xbox import XboxParser
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
    "allowed_regions", [XBOX_PARSE_REGIONS, ("us", "eg"), ("tr", "ar")]
)
@pytest.mark.asyncio
async def test_xbox(httpx_client, allowed_regions: tuple[str, ...]):
    parser = XboxParser(allowed_regions, XBOX_SALES_URL, httpx_client)
    await _check_parsed_unique_with_regions(parser, allowed_regions)


@pytest.mark.parametrize(
    "allowed_regions",
    [
        PSN_PARSE_REGIONS,
        ("tr",),
        ("ua",),
    ],
)
@pytest.mark.asyncio
async def test_psn(httpx_client, allowed_regions: tuple[str, ...]):
    parser = PsnParser(allowed_regions, PSN_SALES_URL, httpx_client, 100)
    await _check_parsed_unique_with_regions(parser, allowed_regions)
