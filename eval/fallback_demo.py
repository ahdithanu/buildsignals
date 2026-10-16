from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_client import OpenRouterClient  # noqa: E402


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is required to run the fallback demo.", file=sys.stderr)
        return 2

    client = OpenRouterClient()
    response = client.chat_completion(
        primary_model="buildsignals/simulated-invalid-model",
        fallback_models=["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku"],
        messages=[
            {"role": "system", "content": "Return one short sentence."},
            {
                "role": "user",
                "content": "This is a simulated unavailable-primary failure. Confirm the fallback answered.",
            },
        ],
        temperature=0,
        max_tokens=120,
    )
    print("Simulated fallback request complete.")
    print(f"Requested primary: {response.requested_model}")
    print(f"Answered by: {response.served_model}")
    print(f"Latency ms: {response.latency_ms}")
    print(f"Cost: {response.cost}")
    print(f"Response: {response.content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
