from collections.abc import Sequence
import psycopg
import httpx
from itertools import chain
import time
from models import ParsedItem
from psn import PsnParser
import asyncio
import os
from xbox import XboxParser
import argparse


async def load_to_db(
    dsn: str,
    table_name: str,
    xbox_items: Sequence[ParsedItem],
    psn_items: Sequence[ParsedItem],
):
    conn = await psycopg.AsyncConnection.connect(dsn)

    def extract_fields_values(item: ParsedItem, category: str):
        return (
            item.name,
            item.default_price.value,
            item.default_price.currency_code,
            item.discounted_price.value,
            item.discounted_price.currency_code,
            item.discount,
            item.deal_until,
            item.image_url,
            item.region,
            category,
        )

    query = f"""INSERT INTO "{table_name}"(
        name, base_price, base_price_currency, discounted_price,
        discounted_price_currency, discount, deal_until, image_url, region, category)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    async with conn, conn.cursor() as cur:
        await cur.execute(f"TRUNCATE TABLE {table_name}")
        coros = [
            cur.executemany(
                query, [extract_fields_values(item, "XBOX") for item in xbox_items]
            ),
            cur.executemany(
                query, [extract_fields_values(item, "PSN") for item in psn_items]
            ),
        ]
        await asyncio.gather(*coros)


async def main():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("-l", "--limit", type=int)
    cli_parser.add_argument("-s", "--db-dsn")
    cli_parser.add_argument("-t", "--table-name")
    args = cli_parser.parse_args()
    db_dsn: str | None = args.db_dsn or os.getenv("DB_DSN")
    table_name: str | None = args.table_name or os.getenv("DB_TABLE_NAME")

    assert (
        db_dsn and table_name
    ), "Specify storage dsn and table_name to load data to. You can do it whether using cli flag(-s / -t) or set environment variable(DB_DSN / DB_TABLE_NAME)"
    psn_parse_regions = ("ru-ua", "en-tr")
    XBOX_SALES_URL = "https://www.xbox-now.com/en/deal-list"
    # PSN_SALES_URL_UA = "https://store.playstation.com/ru-ua/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    # PSN_SALES_URL_TR = "https://store.playstation.com/en-tr/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    limit: int | None = args.limit
    async with httpx.AsyncClient() as client:
        xbox_parser = XboxParser(XBOX_SALES_URL, client, limit)
        psn_parsers = [
            PsnParser(
                f"https://store.playstation.com/{region.lower()}/category/3f772501-f6f8-49b7-abac-874a88ca4897/",
                client,
                limit,
            )
            for region in psn_parse_regions
        ]
        t1 = time.perf_counter()
        res = await asyncio.gather(
            *[parser.parse() for parser in (xbox_parser, *psn_parsers)]
        )
        print("Time elapsed", time.perf_counter() - t1)
    total_parsed = 0
    for sublist in res:
        total_parsed += len(sublist)
    print("total parsed", total_parsed)
    xbox_items = res[0]
    psn_items = list(chain.from_iterable(res[1:]))
    await load_to_db(db_dsn, table_name, xbox_items, psn_items)


if __name__ == "__main__":
    asyncio.run(main())
