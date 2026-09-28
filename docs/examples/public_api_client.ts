/**
 * Minimal Build Signals Public API client.
 *
 * Set BUILD_SIGNALS_API_KEY before running with tsx, ts-node, or after compiling:
 *
 *   BUILD_SIGNALS_API_KEY=bs_live_... npx tsx docs/examples/public_api_client.ts
 */

type JsonRecord = Record<string, unknown>;
declare const process: {
  argv: string[];
  env: Record<string, string | undefined>;
};

export class BuildSignalsClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor({ apiKey, baseUrl = "https://buildsignals.ai/v1" }: { apiKey: string; baseUrl?: string }) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }

    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Build Signals API ${response.status}: ${body || response.statusText}`);
    }

    return (await response.json()) as T;
  }

  listDeals(params: { city?: string; limit?: number; skip?: number } = {}): Promise<JsonRecord[]> {
    return this.request<JsonRecord[]>("/public/deals", {
      city: params.city,
      limit: params.limit ?? 50,
      skip: params.skip ?? 0,
    });
  }

  getDeal(dealId: string): Promise<JsonRecord> {
    return this.request<JsonRecord>(`/public/deals/${dealId}`);
  }

  getGraphContext(dealId: string): Promise<JsonRecord> {
    return this.request<JsonRecord>(`/public/deals/${dealId}/graph-context`);
  }

  listSignals(params: { dealId: string; limit?: number }): Promise<JsonRecord[]> {
    return this.request<JsonRecord[]>("/public/signals", {
      deal_id: params.dealId,
      limit: params.limit ?? 25,
    });
  }

  listEvalRuns(params: { status?: string; limit?: number; skip?: number } = {}): Promise<JsonRecord[]> {
    return this.request<JsonRecord[]>("/public/eval-runs", {
      status: params.status ?? "completed",
      limit: params.limit ?? 25,
      skip: params.skip ?? 0,
    });
  }

  getEvalRun(runId: string): Promise<JsonRecord> {
    return this.request<JsonRecord>(`/public/eval-runs/${runId}`);
  }
}

async function main() {
  const apiKey = process.env.BUILD_SIGNALS_API_KEY;
  if (!apiKey) {
    throw new Error("Set BUILD_SIGNALS_API_KEY before running this example.");
  }

  const client = new BuildSignalsClient({ apiKey });
  const deals = await client.listDeals({ limit: 10 });
  if (deals.length === 0) {
    console.log("No deals returned for this tenant.");
    return;
  }

  const deal = await client.getDeal(String(deals[0].id));
  const graph = await client.getGraphContext(String(deal.id));
  const evalRuns = await client.listEvalRuns({ limit: 5 });
  console.log(
    JSON.stringify(
      {
        deal: deal.name,
        city: deal.city,
        relatedEntityCount: Array.isArray(graph.entities) ? graph.entities.length : 0,
        relationshipCount: Array.isArray(graph.relationships) ? graph.relationships.length : 0,
        recentEvalRuns: evalRuns.length,
      },
      null,
      2,
    ),
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main();
}
