"""Run one short streamed generation for either configured participant."""

from __future__ import annotations

import asyncio
import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import AdapterRegistry, GenerationRequest  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant", choices=("Momo", "Bobby"), default="Momo")
    args = parser.parse_args()
    settings = get_settings()
    registry = AdapterRegistry(settings)
    try:
        adapter = registry.get(args.participant)
        max_output_tokens = (
            settings.momo_live_max_output_tokens
            if args.participant == "Momo"
            else settings.bobby_live_max_output_tokens
        )
        request = GenerationRequest(
            system="Respond with one short sentence. This is a connectivity test.",
            messages=[{"role": "user", "content": "State that the academic roundtable is ready."}],
            max_output_tokens=max_output_tokens,
            reasoning_effort="low",
            verbosity="low",
        )
        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        print(
            f"{args.participant} streamed response received: {bool(text)}; "
            f"characters: {len(text)}; token allowance: {max_output_tokens}"
        )
        return 0 if text else 1
    finally:
        await registry.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
