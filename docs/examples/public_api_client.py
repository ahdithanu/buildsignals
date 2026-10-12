"""Minimal Build Signals Public API client.

Set BUILD_SIGNALS_API_KEY before running:

    BUILD_SIGNALS_API_KEY=bs_live_... python docs/examples/public_api_client.py
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class BuildSignalsRateLimitError(RuntimeError):
    """Raised when a public API key has exhausted its current rate-limit window."""

    def __init__(self, *, retry_after: int | None, reset_after: int | None, body: str) -> None:
        self.retry_after = retry_after
        self.reset_after = reset_after
        wait_seconds = retry_after if retry_after is not None else reset_after
        message = "Build Signals API rate limit exceeded"
        if wait_seconds is not None:
            message = f"{message}; retry after {wait_seconds} seconds"
        if body:
            message = f"{message}: {body}"
        super().__init__(message)


class BuildSignalsAPIError(RuntimeError):
    """Raised for non-successful public API responses."""


def _parse_int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


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
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as error:
            body = error.read().decode("utf-8")
            if error.code == 429:
                raise BuildSignalsRateLimitError(
                    retry_after=_parse_int_header(error.headers.get("Retry-After")),
                    reset_after=_parse_int_header(error.headers.get("X-API-Key-RateLimit-Reset")),
                    body=body,
                ) from error
            raise BuildSignalsAPIError(
                f"Build Signals API {error.code}: {body or error.reason}"
            ) from error

    def get_self(self) -> dict[str, Any]:
        return self._request("/public/me")

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

    def get_workflow_history(self, deal_id: str, *, limit_per_signal: int = 25) -> dict[str, Any]:
        return self._request(
            f"/public/deals/{deal_id}/workflow-history",
            {"limit_per_signal": limit_per_signal},
        )

    def list_signals(self, *, deal_id: str, limit: int = 25) -> list[dict[str, Any]]:
        return self._request("/public/signals", {"deal_id": deal_id, "limit": limit})

    def list_signal_assessment_revisions(
        self,
        signal_id: str,
        *,
        limit: int = 25,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        return self._request(
            f"/public/signals/{signal_id}/assessment-revisions",
            {"limit": limit, "skip": skip},
        )

    def list_revision_reviews(self, revision_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        return self._request(
            f"/public/assessment-revisions/{revision_id}/reviews",
            {"limit": limit},
        )

    def list_revision_publications(self, revision_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        return self._request(
            f"/public/assessment-revisions/{revision_id}/publication",
            {"limit": limit},
        )

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
    self_check = client.get_self()
    deals = client.list_deals(limit=10)
    if not deals:
        print("No deals returned for this tenant.")
        return

    deal = client.get_deal(deals[0]["id"])
    graph = client.get_graph_context(deal["id"])
    workflow = client.get_workflow_history(deal["id"])
    eval_runs = client.list_eval_runs(limit=5)
    graph_buckets = [
        "companies",
        "developers",
        "parcels",
        "owners",
        "contractors",
        "architects",
        "engineers",
        "permits",
        "cities",
        "lenders",
        "brokers",
        "other",
    ]
    print(
        json.dumps(
            {
                "api_key_prefix": self_check.get("api_key", {}).get("key_prefix"),
                "api_key_scopes": self_check.get("api_key", {}).get("scopes", []),
                "rate_limit": self_check.get("rate_limit"),
                "deal": deal.get("name"),
                "city": deal.get("city"),
                "root_entity_count": len(graph.get("root_entities", [])),
                "relationship_count": sum(len(graph.get(bucket, [])) for bucket in graph_buckets),
                "workflow_signal_count": len(workflow.get("signals", [])),
                "recent_eval_runs": len(eval_runs),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
