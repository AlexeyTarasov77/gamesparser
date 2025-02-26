from xbox import XboxParser
import argparse


def main():
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument("-l", "--limit", type=int)
    args = cli_parser.parse_args()
    XBOX_SALES_URL = "https://www.xbox-now.com/en/deal-list"
    xbox_parser = XboxParser(XBOX_SALES_URL, args.limit)
    print(xbox_parser.parse())
