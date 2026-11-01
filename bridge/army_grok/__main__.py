from __future__ import annotations

import argparse
import asyncio
import logging

from .config import load_settings
from .connector import GrokConnector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    connector = GrokConnector(load_settings(args.config))
    try:
        asyncio.run(connector.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
