from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .bridge import ArmyBridge
from .config import load_settings


async def main_async(config_path: str) -> None:
    bridge = ArmyBridge(load_settings(config_path))
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(getattr(signal, signame), bridge.stop)
    await bridge.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Army Hub mention-only Matrix-to-ACP bridge")
    parser.add_argument("--config", required=True, help="Path to the runtime YAML configuration")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main_async(args.config))


if __name__ == "__main__":
    main()
