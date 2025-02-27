from psn import PsnParser
from xbox import XboxParser
import argparse


def main():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("-l", "--limit", type=int)
    args = cli_parser.parse_args()
    XBOX_SALES_URL = "https://www.xbox-now.com/en/deal-list"
    PSN_SALES_URL_UA = "https://store.playstation.com/ru-ua/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    PSN_SALES_URL_TR = "https://store.playstation.com/en-tr/category/3f772501-f6f8-49b7-abac-874a88ca4897/"
    xbox_parser = XboxParser(XBOX_SALES_URL, args.limit)
    psn_ua_parser = PsnParser(PSN_SALES_URL_UA, args.limit)
    psn_tr_parser = PsnParser(PSN_SALES_URL_TR, args.limit)
    print(psn_ua_parser.parse())


if __name__ == "__main__":
    main()
