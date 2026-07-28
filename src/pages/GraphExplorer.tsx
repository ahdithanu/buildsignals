import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Clock3, Network, Search, X } from "lucide-react";

import { Layout } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/DataStates";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useGraphEntitySearch } from "@/hooks/useGraphSearch";
import type { GraphEntitySearchResult } from "@/types/graph";

const ENTITY_TYPES = [
  { value: "", label: "All types" },
  { value: "property", label: "Property" },
  { value: "parcel", label: "Parcel" },
  { value: "developer", label: "Developer" },
  { value: "owner", label: "Owner" },
  { value: "general_contractor", label: "Contractor" },
  { value: "architect", label: "Architect" },
  { value: "engineer", label: "Engineer" },
  { value: "permit", label: "Permit" },
  { value: "company", label: "Company" },
  { value: "broker", label: "Broker" },
  { value: "lender", label: "Lender" },
] as const;

function typeLabel(value: string) {
  return value.replace(/_/g, " ");
}

function SearchResultRow({ entity }: { entity: GraphEntitySearchResult }) {
  return (
    <Link
      to={`/graph/entities/${entity.id}`}
      className="block rounded-md border bg-card px-3 py-3 transition-colors hover:bg-secondary/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">{entity.display_name}</h3>
            <Badge variant="secondary" className="capitalize">
              {typeLabel(entity.entity_type)}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {entity.source_system || "Source unknown"}
            {entity.source_id ? ` · ${entity.source_id}` : ""}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Verified {new Date(entity.last_verified_at).toLocaleDateString()}
            {entity.normalized_address ? ` · ${entity.normalized_address}` : ""}
          </p>
        </div>
        <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      </div>
      {entity.aliases.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entity.aliases.slice(0, 4).map((alias) => (
            <span
              key={alias}
              className="rounded-md border bg-secondary/25 px-2 py-0.5 text-[11px] text-muted-foreground"
            >
              {alias}
            </span>
          ))}
        </div>
      )}
      <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="rounded-md border bg-secondary/25 px-2 py-0.5">
          {Math.round(entity.confidence * 100)}% confidence
        </span>
      </div>
    </Link>
  );
}

export default function GraphExplorer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [entityType, setEntityType] = useState(searchParams.get("type") ?? "");
  const debouncedQuery = useDebouncedValue(query, 250);

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (debouncedQuery.trim()) {
      params.set("q", debouncedQuery.trim());
    } else {
      params.delete("q");
    }
    if (entityType) {
      params.set("type", entityType);
    } else {
      params.delete("type");
    }
    const next = params.toString();
    if (next !== searchParams.toString()) {
      setSearchParams(params, { replace: true });
    }
  }, [debouncedQuery, entityType, searchParams, setSearchParams]);

  const { data, isLoading, error } = useGraphEntitySearch(debouncedQuery, entityType || undefined);
  const results = useMemo(() => data ?? [], [data]);

  return (
    <Layout>
      <div className="mx-auto max-w-[1080px] space-y-4 p-4 md:p-6">
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-card">
            <Network className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">Knowledge Graph</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Search entities by name, alias, source id, or normalized match.
            </p>
          </div>
        </div>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px_auto] md:items-end">
            <label className="min-w-0 text-xs text-muted-foreground">
              Search entities
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search developers, owners, parcels, permits, or aliases"
                className="mt-1 h-9"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Entity type
              <select
                value={entityType}
                onChange={(event) => setEntityType(event.target.value)}
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              >
                {ENTITY_TYPES.map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9"
              onClick={() => {
                setQuery("");
                setEntityType("");
              }}
              disabled={!query && !entityType}
            >
              <X className="h-4 w-4" />
              Clear
            </Button>
          </div>
        </section>

        {!debouncedQuery.trim() ? (
          <EmptyState
            title="Search the graph"
            description="Try an entity name, alias, or source id to open the node detail page."
          />
        ) : isLoading ? (
          <LoadingState message="Searching graph..." />
        ) : error ? (
          <ErrorState message="Graph search is unavailable." onRetry={() => setQuery(debouncedQuery)} />
        ) : results.length === 0 ? (
          <EmptyState
            title="No entities found"
            description="Try a broader name, a different type, or a source id from the original record."
          />
        ) : (
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Search className="h-3.5 w-3.5" />
                <span>{results.length} matches</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock3 className="h-3.5 w-3.5" />
                <span>Latest matching nodes first</span>
              </div>
            </div>
            <div className="space-y-2">
              {results.map((entity) => (
                <SearchResultRow key={entity.id} entity={entity} />
              ))}
            </div>
          </section>
        )}
      </div>
    </Layout>
  );
}

function useDebouncedValue(value: string, delayMs: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs, value]);
  return debounced;
}
