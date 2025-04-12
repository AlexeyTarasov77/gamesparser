from collections.abc import Iterable
from typing import Final
import pytest
import os
import httpx

from gamesparser.models import AbstractParser
from gamesparser.psn import PsnParser
from gamesparser.xbox import XboxParser
import pytest_asyncio

# can be changed to None to avoid limiting but tests run will take longer
_limit = os.getenv("TESTS_PARSE_LIMIT")
PARSE_LIMIT: Final[int | None] = int(_limit) if _limit is not None else None


@pytest_asyncio.fixture
async def httpx_client():
    async with httpx.AsyncClient() as client:
        yield client


async def _check_parsed_unique_with_regions(
    parser: AbstractParser,
    allowed_regions: Iterable[str],
):
    allowed_regions = set(region.lower() for region in allowed_regions)
    res = await parser.parse()
    checked_names: list[str] = []
    for obj in res:
        assert obj not in checked_names
        for region in obj.prices:
            assert region.lower() in allowed_regions
        checked_names.append(obj.name)


@pytest.mark.parametrize(
    "allowed_regions",
    [("tr", "ar", "us"), ("eg"), ("us", "ar")],
)
@pytest.mark.asyncio
async def test_xbox(httpx_client: httpx.AsyncClient, allowed_regions: tuple[str, ...]):
    parser = XboxParser(allowed_regions, httpx_client, PARSE_LIMIT)
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
    parser = PsnParser(allowed_regions, httpx_client, PARSE_LIMIT)
    await _check_parsed_unique_with_regions(parser, allowed_regions)
