import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layout } from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingState, ErrorState } from "@/components/DataStates";
import { auditApi, type AuditLogEntry } from "@/api/audit";
import { ChevronLeft, ChevronRight, History } from "lucide-react";
import { motion } from "framer-motion";

const PAGE_SIZE = 50;

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function actorLabel(entry: AuditLogEntry): string {
  if (entry.actor_name) return entry.actor_name;
  if (entry.actor_email) return entry.actor_email;
  return entry.actor_id ? `user:${entry.actor_id.slice(0, 8)}` : "system";
}

export default function AuditLog() {
  const [page, setPage] = useState(0);
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");

  const params = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      entity_type: entityType.trim() || undefined,
      action: action.trim() || undefined,
    }),
    [page, entityType, action],
  );

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit", params],
    queryFn: () => auditApi.list(params),
    staleTime: 15_000,
  });

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstRow = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const lastRow = Math.min(total, (page + 1) * PAGE_SIZE);

  const resetFilters = () => {
    setEntityType("");
    setAction("");
    setPage(0);
  };

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-5 md:space-y-6 max-w-[1400px] mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg md:text-xl font-semibold font-display">
              Audit Log
            </h2>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Who changed what, and when. Admin-only.
          </p>
        </motion.div>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Filters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="entity_type">Entity type</Label>
                <Input
                  id="entity_type"
                  placeholder="deal, memo, membership…"
                  value={entityType}
                  onChange={(e) => {
                    setPage(0);
                    setEntityType(e.target.value);
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="action">Action</Label>
                <Input
                  id="action"
                  placeholder="create, update, delete…"
                  value={action}
                  onChange={(e) => {
                    setPage(0);
                    setAction(e.target.value);
                  }}
                />
              </div>
              <div className="flex items-end">
                <Button
                  variant="outline"
                  onClick={resetFilters}
                  disabled={!entityType && !action}
                >
                  Clear filters
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {isLoading ? (
          <LoadingState message="Loading audit log…" />
        ) : error ? (
          <ErrorState
            message="Failed to load audit log."
            onRetry={() => refetch()}
          />
        ) : (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-sm">
                {total === 0
                  ? "No entries"
                  : `Showing ${firstRow}–${lastRow} of ${total}`}
              </CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-xs text-muted-foreground">
                  {page + 1} / {pageCount}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => p + 1)}
                  aria-label="Next page"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="text-left p-3 font-medium">When</th>
                      <th className="text-left p-3 font-medium">Actor</th>
                      <th className="text-left p-3 font-medium">Entity</th>
                      <th className="text-left p-3 font-medium">Action</th>
                      <th className="text-left p-3 font-medium">Changes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.items.map((entry) => (
                      <tr
                        key={entry.id}
                        className="border-t align-top hover:bg-muted/20"
                      >
                        <td className="p-3 whitespace-nowrap text-muted-foreground">
                          {formatTimestamp(entry.created_at)}
                        </td>
                        <td className="p-3">{actorLabel(entry)}</td>
                        <td className="p-3">
                          <span className="font-medium">{entry.entity_type}</span>
                          <span className="text-muted-foreground">
                            :{entry.entity_id.slice(0, 8)}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 rounded bg-muted text-xs">
                            {entry.action}
                          </span>
                        </td>
                        <td className="p-3 max-w-md">
                          {entry.new_values || entry.old_values ? (
                            <pre className="text-xs whitespace-pre-wrap break-words text-muted-foreground font-mono">
                              {JSON.stringify(
                                entry.new_values ?? entry.old_values,
                                null,
                                2,
                              )}
                            </pre>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
