"""Minimal Build Signals Public API client.

Set BUILD_SIGNALS_API_KEY before running:

    BUILD_SIGNALS_API_KEY=bs_live_... python docs/examples/public_api_client.py
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BuildSignalsClient:
    api_key: str
    base_url: str = "https://buildsignals.ai/v1"
    timeout_seconds: int = 20

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}{path}{query}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None

    def list_deals(
        self,
        *,
        city: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if city:
            params["city"] = city
        return self._request("/public/deals", params)

    def get_deal(self, deal_id: str) -> dict[str, Any]:
        return self._request(f"/public/deals/{deal_id}")

    def get_graph_context(self, deal_id: str) -> dict[str, Any]:
        return self._request(f"/public/deals/{deal_id}/graph-context")

    def list_signals(self, *, deal_id: str, limit: int = 25) -> list[dict[str, Any]]:
        return self._request("/public/signals", {"deal_id": deal_id, "limit": limit})

    def list_eval_runs(
        self,
        *,
        status: str | None = "completed",
        limit: int = 25,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if status:
            params["status"] = status
        return self._request("/public/eval-runs", params)

    def get_eval_run(self, run_id: str) -> dict[str, Any]:
        return self._request(f"/public/eval-runs/{run_id}")


def main() -> None:
    api_key = os.environ["BUILD_SIGNALS_API_KEY"]
    client = BuildSignalsClient(api_key=api_key)
    deals = client.list_deals(limit=10)
    if not deals:
        print("No deals returned for this tenant.")
        return

    deal = client.get_deal(deals[0]["id"])
    graph = client.get_graph_context(deal["id"])
    eval_runs = client.list_eval_runs(limit=5)
    print(
        json.dumps(
            {
                "deal": deal.get("name"),
                "city": deal.get("city"),
                "related_entity_count": len(graph.get("entities", [])),
                "relationship_count": len(graph.get("relationships", [])),
                "recent_eval_runs": len(eval_runs),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
