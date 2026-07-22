"""Run one short streamed generation for either configured participant."""

from __future__ import annotations

import asyncio
import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters import AdapterRegistry, GenerationRequest  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--participant", choices=("Momo", "Bobby"), default="Momo")
    parser.add_argument("--profile", choices=("connectivity", "academic"), default="connectivity")
    parser.add_argument("--repeat", type=int, default=1)
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
        if args.profile == "academic":
            system = (
                "You are Bobby in a concise academic roundtable. Develop the strongest defensible "
                "case, distinguish evidence from inference, and respond in 90 to 130 words."
            )
            prompts = [
                "Explain how longitudinal cognitive trajectories could predict later health without assuming the association is causal.",
                "Now respond to a critic who argues that baseline health and measurement error explain the entire association.",
            ]
        else:
            system = "Respond with one short sentence. This is a connectivity test."
            prompts = ["State that the academic roundtable is ready."]

        attempts = max(1, min(args.repeat, 5))
        success = True
        for index in range(attempts):
            request = GenerationRequest(
                system=system,
                messages=[{"role": "user", "content": prompts[index % len(prompts)]}],
                max_output_tokens=max_output_tokens,
                reasoning_effort="low",
                verbosity="low",
            )
            chunks = []
            started = time.perf_counter()
            first_token_seconds = None
            async for chunk in adapter.stream(request):
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - started
                chunks.append(chunk)
            total_seconds = time.perf_counter() - started
            text = "".join(chunks).strip()
            success = success and bool(text)
            print(
                f"attempt={index + 1}; participant={args.participant}; received={bool(text)}; "
                f"first_token_seconds={first_token_seconds if first_token_seconds is not None else 'none'}; "
                f"total_seconds={total_seconds:.3f}; chunks={len(chunks)}; characters={len(text)}; "
                f"words={len(text.split())}; token_allowance={max_output_tokens}"
            )
        return 0 if success else 1
    finally:
        await registry.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
