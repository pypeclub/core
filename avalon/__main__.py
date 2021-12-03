import os
import argparse

from . import pipeline, version, api


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true", help=(
        "Print version and exit"))
    parser.add_argument("--root",
                        help="Absolute path to root directory of assets")

    args, unknown = parser.parse_known_args()
    host = pipeline.debug_host()
    pipeline.register_host(host)

    if args.version:
        print("avalon==%s" % version.version)
        exit(0)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
