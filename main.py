import asyncio
import time
import sys

from httpx import AsyncClient
from gamesparser.psn import PsnParser
from gamesparser.xbox import XboxParser


async def main():
    try:
        limit_per_platform = int(sys.argv[1]) // 2
    except Exception:
        limit_per_platform = None
    print(
        "Start parsing%ssales..."
        % (
            f" up to {limit_per_platform * 2} "
            if limit_per_platform is not None
            else " "
        )
    )
    async with AsyncClient() as client:
        psn_parser = PsnParser(client)
        xbox_parser = XboxParser(client)
        t1 = time.perf_counter()
        psn_sales, xbox_sales = await asyncio.gather(
            psn_parser.parse(["tr", "ua"], limit_per_platform),
            xbox_parser.parse(["us"], limit_per_platform),
        )
        psn_details = await psn_parser.parse_item_details(psn_sales[0].url)
        print("PSN DETAILS SAMPLE", psn_details)
        xbox_details = await xbox_parser.parse_item_details(xbox_sales[0].url)
        print("XBOX DETAILS SAMPLE", xbox_details)
    sales = psn_sales + xbox_sales
    print(
        "%s sales succesfully parsed, which took: %s seconds"
        % (
            len(sales),
            round(time.perf_counter() - t1, 1),
        )
    )
    print(psn_sales[:3])
    print(xbox_sales[:3])


if __name__ == "__main__":
    asyncio.run(main())
