from collections.abc import Iterable
import os
from typing import Final

import httpx
import pytest_asyncio

from gamesparser.models import AbstractParser


_limit = os.getenv("TESTS_PARSE_LIMIT")
# if equals to None - limit will be disabled and tests will run longer
PARSE_LIMIT: Final[int | None] = int(_limit) if _limit is not None else None
print("Running tests with TESTS_PARSE_LIMIT=", PARSE_LIMIT)


@pytest_asyncio.fixture
async def httpx_client():
    async with httpx.AsyncClient() as client:
        yield client


async def check_parsed_unique_with_regions(
    parser: AbstractParser,
    allowed_regions: Iterable[str],
):
    allowed_regions = set(region.lower() for region in allowed_regions)
    parsed_products = await parser.parse(allowed_regions)
    checked_names: list[str] = []
    for obj in parsed_products:
        assert obj not in checked_names
        for region in obj.prices:
            assert region.lower() in allowed_regions
        checked_names.append(obj.name)
    return parsed_products
