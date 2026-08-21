import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock, Network } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/DataStates";
import { Layout } from "@/components/Layout";
import { Badge } from "@/components/ui/badge";
import { useGraphRelationshipReviewQueue } from "@/hooks/useGraphRelationship";

function label(value: string) {
  return value.replace(/_/g, " ");
}

function formatDate(value?: string) {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export default function GraphVerificationQueue() {
  const { data = [], isLoading, error, refetch } = useGraphRelationshipReviewQueue(14);

  return (
    <Layout>
      <div className="mx-auto max-w-[1120px] space-y-4 p-4 md:p-6">
        <header className="flex items-start gap-3">
          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card">
            <CalendarClock className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">Graph Verification</h2>
            <p className="mt-1 text-sm text-muted-foreground">Relationships overdue or due for evidence review within 14 days.</p>
          </div>
        </header>

        {isLoading ? (
          <LoadingState message="Loading verification queue..." />
        ) : error ? (
          <ErrorState message="The graph verification queue is unavailable." onRetry={() => refetch()} />
        ) : data.length === 0 ? (
          <EmptyState title="Verification queue is clear" description="No current relationships need evidence review." />
        ) : (
          <section className="overflow-hidden rounded-md border bg-card card-shadow">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <Network className="h-4 w-4 text-muted-foreground" />
                Evidence review
              </div>
              <span className="text-xs text-muted-foreground">{data.length} relationship{data.length === 1 ? "" : "s"}</span>
            </div>
            <div className="divide-y">
              {data.map((item) => (
                <Link
                  key={item.relationship.id}
                  to={`/graph/relationships/${item.relationship.id}`}
                  className="grid gap-3 px-4 py-3 transition-colors hover:bg-secondary/35 md:grid-cols-[minmax(0,1fr)_180px_130px_auto] md:items-center"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {item.source_entity.display_name} to {item.target_entity.display_name}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {label(item.relationship.relationship_type)} · {item.relationship.evidence.length} evidence item{item.relationship.evidence.length === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    <p>Due {formatDate(item.relationship.verification_due_at)}</p>
                    <p className="mt-1">Verified {formatDate(item.relationship.last_verified_at)}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={item.relationship.verification_status === "stale" ? "destructive" : "outline"} className="capitalize">
                      {item.relationship.verification_status || "due"}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground">{Math.round(item.relationship.confidence * 100)}%</span>
                  </div>
                  <ArrowRight className="hidden h-4 w-4 text-muted-foreground md:block" />
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </Layout>
  );
}
