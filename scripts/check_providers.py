"""Safely check configured provider connectivity without printing credentials."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import AdapterRegistry  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    registry = AdapterRegistry(get_settings())
    try:
        results = await asyncio.gather(
            registry.get("Momo").health_check(),
            registry.get("Bobby").health_check(),
        )
        print(json.dumps(results, indent=2))
        return 0 if all(item.get("reachable") for item in results) else 1
    finally:
        await registry.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
