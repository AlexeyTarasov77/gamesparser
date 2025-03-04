import pytest
import httpx

from constants import XBOX_SALES_URL
from xbox import XboxParser
import pytest_asyncio


@pytest_asyncio.fixture
async def httpx_client():
    async with httpx.AsyncClient() as client:
        yield client


@pytest.mark.parametrize("regions", [("us", "eg"), ("tr", "ar")])
@pytest.mark.asyncio
async def test_parse(httpx_client, regions: tuple[str]):
    parser = XboxParser(regions, XBOX_SALES_URL, httpx_client)
    res = await parser.parse()
    checked_names: dict[str, int] = {}
    for i, obj in enumerate(res):
        if obj.name in checked_names:
            assert obj.region != res[checked_names[obj.name]]
        assert obj.region.lower() in regions
        checked_names[obj.name] = i
