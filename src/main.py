import httpx
from psn import PsnParser
import asyncio
import os
from xbox import XboxParser
import argparse


async def main():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("-l", "--limit", type=int)
    cli_parser.add_argument("-s", "--db-dsn", dest="db_dsn")
    args = cli_parser.parse_args()
    db_dsn = args.db_dsn
    if not db_dsn:
        db_dsn = os.getenv("DB_DSN")
    # assert db_dsn, "Specify storage dsn to load data. You can do it whether using cli flag(-s) or set environment variable(DB_DSN)"
    XBOX_SALES_URL = "https://www.xbox-now.com/en/deal-list"
    PSN_SALES_URL_UA = "https://store.playstation.com/ru-ua/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    PSN_SALES_URL_TR = "https://store.playstation.com/en-tr/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    limit: int = args.limit
    async with httpx.AsyncClient() as client:
        xbox_parser = XboxParser(XBOX_SALES_URL, client, limit)
        psn_ua_parser = PsnParser(PSN_SALES_URL_UA, client, limit)
        psn_tr_parser = PsnParser(PSN_SALES_URL_TR, client, limit)
        res = await psn_tr_parser.parse()
        print(res[0])
    #     t1 = time.perf_counter()
    #     res = await asyncio.gather(
    #         *[parser.parse() for parser in (xbox_parser, psn_ua_parser, psn_tr_parser)]
    #     )
    #     print("Time elapsed", time.perf_counter() - t1)
    # total_parsed = 0
    # for sublist in res:
    #     total_parsed += len(sublist)
    # print("total parsed", total_parsed)


if __name__ == "__main__":
    asyncio.run(main())
