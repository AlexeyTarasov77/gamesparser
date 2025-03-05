from collections.abc import Sequence
from dataclasses import asdict
import psycopg
from psycopg import sql
import httpx
from itertools import chain
import time
from constants import (
    PSN_PARSE_REGIONS,
    PSN_SALES_URL,
    XBOX_PARSE_REGIONS,
    XBOX_SALES_URL,
)
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
    table_name_id = sql.Identifier(table_name)

    def convert_item(item: ParsedItem, category: str):
        item_dump = asdict(item)
        item_dump["base_price"] = item.base_price.value
        item_dump["base_price_currency"] = item.base_price.currency_code
        item_dump["discounted_price"] = item.discounted_price.value
        item_dump["discounted_price_currency"] = item.discounted_price.currency_code
        item_dump["category"] = category
        return item_dump

    query = sql.SQL("""INSERT INTO {}(
        name, base_price, base_price_currency, discounted_price,
        discounted_price_currency, discount, deal_until, image_url, region, with_gp, category)
        VALUES (%(name)s, %(base_price)s, %(base_price_currency)s,
        %(discounted_price)s, %(discounted_price_currency)s, %(discount)s,
        %(deal_until)s, %(image_url)s, %(region)s, %(with_gp)s, %(category)s)""").format(
        table_name_id
    )
    async with conn, conn.cursor() as cur:
        await cur.execute(sql.SQL("TRUNCATE TABLE {}").format(table_name_id))
        coros = [
            cur.executemany(query, [convert_item(item, "XBOX") for item in xbox_items]),
            cur.executemany(query, [convert_item(item, "PSN") for item in psn_items]),
        ]
        await asyncio.gather(*coros)


def parse_cli():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("-l", "--limit", type=int)
    cli_parser.add_argument("-s", "--db-dsn")
    cli_parser.add_argument("-t", "--table-name")
    args = cli_parser.parse_args()
    return args


async def main():
    args = parse_cli()
    db_dsn: str | None = args.db_dsn or os.getenv("DB_DSN")
    table_name: str | None = args.table_name or os.getenv("DB_TABLE_NAME")
    assert (
        db_dsn and table_name
    ), "Specify storage dsn and table_name to load data to. You can do it whether using cli flag(-s / -t) or set environment variable(DB_DSN / DB_TABLE_NAME)"
    limit: int | None = args.limit
    async with httpx.AsyncClient() as client:
        xbox_parser = XboxParser(XBOX_PARSE_REGIONS, XBOX_SALES_URL, client, limit)
        psn_parser = PsnParser(PSN_PARSE_REGIONS, PSN_SALES_URL, client, limit)
        t1 = time.perf_counter()
        res = await psn_parser.parse()
        print("PSN PARSED", len(res))

        # res = await asyncio.gather(xbox_parser.parse(), psn_parser.parse())
        print("Time elapsed", time.perf_counter() - t1)
    # total_parsed = 0
    # for sublist in res:
    #     total_parsed += len(sublist)
    # print("total parsed", total_parsed)
    # xbox_items, psn_items = res
    # await load_to_db(db_dsn, table_name, xbox_items, psn_items)


if __name__ == "__main__":
    asyncio.run(main())
