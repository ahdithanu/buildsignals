import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bookmark,
  ChevronRight,
  CircleAlert,
  FileText,
  Network,
  Search,
  Sparkles,
} from "lucide-react";
import { Layout } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/DataStates";
import { signalsApi } from "@/api/signals";
import { queryKeys } from "@/lib/queryKeys";
import { signalStageFor } from "@/lib/signalStage";
import { cn } from "@/lib/utils";
import type { Signal } from "@/types/activity";

const savedViews = ["Priority queue", "Pre-approval", "Chain entries", "Changed records"];
const filters = ["Stage", "Market", "Opportunity", "Confidence", "Priority", "Named party"];

function stageFor(signal: Signal) {
  return signalStageFor(signal.type);
}

function confidenceFor(signal: Signal) {
  return signal.confidence === "high" ? 0.91 : signal.confidence === "medium" ? 0.74 : 0.58;
}

function priorityFor(signal: Signal, index: number) {
  const confidence = confidenceFor(signal);
  return Math.max(42, Math.round(confidence * 100) - index * 3);
}

function marketFor(signal: Signal) {
  const match = signal.property.match(/(?:—|·)\s*([^·—]+,\s*[A-Z]{2})/);
  return match?.[1] || "Market intelligence";
}

export default function MarketSignals() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState(savedViews[0]);
  const [query, setQuery] = useState("");
  const [watched, setWatched] = useState<Set<string>>(new Set());

  const { data: signals, isLoading, error, refetch } = useQuery<Signal[]>({
    queryKey: queryKeys.signals.all,
    queryFn: () => signalsApi.list(),
    retry: 1,
  });

  const filtered = useMemo(() => {
    const rows = signals ?? [];
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((signal) => `${signal.property} ${signal.summary}`.toLowerCase().includes(normalized));
  }, [query, signals]);

  const selected = filtered.find((signal) => signal.id === selectedId) || filtered[0];
  const selectedIndex = selected ? Math.max(filtered.findIndex((signal) => signal.id === selected.id), 0) : 0;

  function toggleWatch(id: string) {
    setWatched((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (isLoading) return <Layout><LoadingState message="Loading signals..." /></Layout>;
  if (error) return <Layout><ErrorState message="Failed to load signals." onRetry={() => refetch()} /></Layout>;

  return (
    <Layout>
      <div className="flex min-h-[calc(100vh-48px)] flex-col">
        <div className="flex flex-col border-b-2 border-foreground bg-card">
          <div className="flex min-h-11 flex-wrap items-center gap-2 px-3 md:px-5">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search signal, address, permit or named party"
                className="h-9 min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
              />
            </div>
            <p className="text-[10px] text-muted-foreground">{filtered.length} active signals · refreshed 14m ago</p>
          </div>
          <div className="flex min-w-0 overflow-x-auto border-t border-border px-3 md:px-5">
            {savedViews.map((view) => (
              <button
                key={view}
                type="button"
                onClick={() => setActiveView(view)}
                className={cn(
                  "shrink-0 border-r border-border px-3 py-2 text-[10px] font-medium first:border-l",
                  activeView === view ? "bg-foreground text-background" : "hover:bg-secondary",
                )}
              >
                {view}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 border-b border-border bg-background px-3 py-2 md:px-5">
          <span className="section-label mr-1">Filters</span>
          {filters.map((filter) => (
            <button key={filter} type="button" className="border border-input bg-card px-2 py-1 text-[10px] hover:border-foreground">{filter} +</button>
          ))}
          <button type="button" className="ml-auto text-[10px] text-muted-foreground hover:text-foreground">Save view</button>
        </div>

        {filtered.length === 0 ? (
          <EmptyState title="No signals found" description="Adjust the active filters or search terms." />
        ) : (
          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(330px,452px)_1fr]">
            <section className="min-h-0 border-r-2 border-foreground bg-card" aria-label="Ranked signal queue">
              <div className="grid grid-cols-[36px_1fr_auto] border-b-2 border-foreground px-3 py-2 text-[9px] font-semibold uppercase text-muted-foreground">
                <span>Rank</span><span>Signal</span><span>Priority</span>
              </div>
              <div className="max-h-[calc(100vh-166px)] overflow-y-auto">
                {filtered.map((signal, index) => {
                  const active = selected?.id === signal.id;
                  const stage = stageFor(signal);
                  return (
                    <button
                      type="button"
                      key={signal.id}
                      onClick={() => setSelectedId(signal.id)}
                      className={cn(
                        "grid w-full grid-cols-[36px_1fr_auto] gap-2 border-b border-border px-3 py-3 text-left hover:bg-secondary/70",
                        stage === "PRE-APPROVAL" && "border-l-2 border-l-destructive",
                        active && "bg-secondary",
                      )}
                    >
                      <span className="font-mono text-[9px] text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold">{signal.property}</span>
                        <span className="mt-1 block truncate text-[10px] text-muted-foreground">{marketFor(signal)} · {new Date(signal.date).toLocaleDateString()}</span>
                        <span className={cn("mt-2 inline-block px-1.5 py-0.5 text-[8px] font-semibold", stage === "PRE-APPROVAL" ? "stage-preapproval" : "stage-approved")}>{stage}</span>
                      </span>
                      <span className="text-sm font-semibold">{priorityFor(signal, index)}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            {selected && (
              <section className="min-w-0 bg-background" aria-label="Selected signal diligence">
                <div className="flex flex-wrap items-start gap-3 border-b-2 border-foreground bg-card px-4 py-4 md:px-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={cn("px-1.5 py-0.5 text-[9px] font-semibold", stageFor(selected) === "PRE-APPROVAL" ? "stage-preapproval" : "stage-approved")}>{stageFor(selected)}</span>
                      <span className="text-[10px] text-muted-foreground">Priority {priorityFor(selected, selectedIndex)}</span>
                      <span className="text-[10px] text-muted-foreground">Confidence {confidenceFor(selected).toFixed(2)}</span>
                    </div>
                    <h1 className="mt-2 text-lg font-semibold md:text-xl">{selected.property}</h1>
                    <p className="mt-1 text-xs text-muted-foreground">{marketFor(selected)} · filing intelligence record</p>
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => toggleWatch(selected.id)}
                      className={cn("inline-flex h-8 items-center gap-1.5 border border-foreground px-2.5 text-[10px] font-semibold", watched.has(selected.id) && "bg-foreground text-background")}
                    >
                      <Bookmark className="h-3.5 w-3.5" /> {watched.has(selected.id) ? "Watching" : "Watch"}
                    </button>
                    <button type="button" className="h-8 bg-foreground px-3 text-[10px] font-semibold text-background">Create memo</button>
                  </div>
                </div>

                <div className="grid gap-0 xl:grid-cols-[1.15fr_.85fr]">
                  <div className="border-foreground xl:border-r-2">
                    <section className="border-b-2 border-foreground p-4 md:p-5">
                      <p className="section-label">Decision summary</p>
                      <div className="mt-3 grid gap-4 md:grid-cols-2">
                        <Decision label="Why it matters" value={selected.summary || "A newly detected filing creates an early window to identify the operator, land position and decision makers."} icon={Sparkles} />
                        <Decision label="Recommended next action" value="Resolve the named parties, verify the filing source, and review adjacent parcel availability before the next jurisdiction milestone." icon={ChevronRight} />
                        <Decision label="Missing facts" value="Final tenant, lender and broker relationships remain unverified." icon={CircleAlert} />
                        <Decision label="Latest change" value={`${stageFor(selected) === "PRE-APPROVAL" ? "Application entered review" : "Approval milestone recorded"} · ${new Date(selected.date).toLocaleDateString()}`} icon={FileText} />
                      </div>
                    </section>

                    <section className="border-b-2 border-foreground p-4 md:p-5">
                      <p className="section-label">Filing lifecycle</p>
                      <div className="mt-4 grid grid-cols-4 gap-0">
                        {["Filed", "In review", "Approved", "Issued"].map((step, index) => {
                          const current = stageFor(selected) === "PRE-APPROVAL" ? index === 1 : index === 2;
                          const complete = stageFor(selected) === "PRE-APPROVAL" ? index < 1 : index < 3;
                          return (
                            <div key={step} className="relative border-t-2 border-foreground pt-3">
                              <span className={cn("absolute -top-[5px] left-0 h-2 w-2 border border-foreground bg-background", (current || complete) && "bg-foreground")} />
                              <p className={cn("text-[10px]", current ? "font-semibold" : "text-muted-foreground")}>{step}</p>
                              <p className="mt-1 text-[9px] text-muted-foreground">{complete || current ? new Date(selected.date).toLocaleDateString() : "Pending"}</p>
                            </div>
                          );
                        })}
                      </div>
                    </section>

                    <section className="p-4 md:p-5">
                      <p className="section-label">Connected parties</p>
                      <div className="mt-3 grid sm:grid-cols-2">
                        {[
                          ["Developer", "Vestar Development", "Verified"],
                          ["Owner", "Gilbert Land Partners", "Verified"],
                          ["General contractor", "Unresolved", "Missing"],
                          ["Architect", "Studio 8 Design", "Inferred"],
                          ["Lender", "Unresolved", "Missing"],
                          ["Broker", "Phoenix Retail Advisory", "Inferred"],
                        ].map(([role, name, status]) => (
                          <div key={role} className="grid grid-cols-[120px_1fr_auto] gap-2 border-t border-border py-2 text-[10px]">
                            <span className="text-muted-foreground">{role}</span><span className="font-medium">{name}</span><span className="text-muted-foreground">{status}</span>
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>

                  <aside className="min-w-0 bg-card p-4 md:p-5">
                    <div className="flex items-center gap-2">
                      <Network className="h-4 w-4" />
                      <p className="section-label text-foreground">Relationship context</p>
                    </div>
                    <div className="mt-3 border-y-2 border-foreground">
                      {[
                        [selected.property, "site", "Current filing"],
                        ["Vestar Development", "developer", "Verified · 0.94"],
                        ["Gilbert Land Partners", "owner", "Verified · 0.98"],
                        ["Studio 8 Design", "architect", "Inferred · 0.72"],
                      ].map(([name, role, evidence]) => (
                        <div key={`${name}-${role}`} className="flex items-center justify-between gap-3 border-b border-border py-3 last:border-b-0">
                          <div className="min-w-0"><p className="truncate text-xs font-semibold">{name}</p><p className="text-[9px] uppercase text-muted-foreground">{role}</p></div>
                          <p className="shrink-0 text-[9px] text-muted-foreground">{evidence}</p>
                        </div>
                      ))}
                    </div>
                    <button type="button" className="mt-3 inline-flex items-center gap-1 text-[10px] font-semibold hover:underline">Open graph context <ChevronRight className="h-3 w-3" /></button>

                    <div className="mt-8">
                      <p className="section-label">Evidence</p>
                      <div className="mt-3 border-t-2 border-foreground">
                        <Evidence label="Official filing" value="Permit application and lifecycle status" />
                        <Evidence label="Record ID" value={selected.id} />
                        <Evidence label="Last verified" value={new Date(selected.date).toLocaleString()} />
                        <Evidence label="Source count" value="4 independent observations" />
                      </div>
                    </div>
                  </aside>
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}

function Decision({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Sparkles }) {
  return (
    <div className="border-t border-foreground pt-2">
      <div className="flex items-center gap-1.5"><Icon className="h-3 w-3" /><p className="text-[9px] font-semibold uppercase text-muted-foreground">{label}</p></div>
      <p className="mt-1.5 text-xs leading-relaxed">{value}</p>
    </div>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return <div className="border-b border-border py-2"><p className="text-[9px] uppercase text-muted-foreground">{label}</p><p className="mt-1 break-words text-[10px] font-medium">{value}</p></div>;
}
