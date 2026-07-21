"""Run one short streamed generation to verify the configured Responses adapter."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import AdapterRegistry, GenerationRequest  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    registry = AdapterRegistry(get_settings())
    try:
        adapter = registry.get("Momo")
        request = GenerationRequest(
            system="Respond with one short sentence. This is a connectivity test.",
            messages=[{"role": "user", "content": "State that the academic roundtable is ready."}],
            max_output_tokens=120,
            reasoning_effort="low",
            verbosity="low",
        )
        chunks = []
        async for chunk in adapter.stream(request):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        print(f"Streamed response received: {bool(text)}; characters: {len(text)}")
        return 0 if text else 1
    finally:
        await registry.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
