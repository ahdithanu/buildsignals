import { useState } from "react";
import { Layout } from "@/components/Layout";
import { stageLabels, formatCurrency } from "@/lib/formatters";
import { useDeals, useMoveStage } from "@/hooks/useDeals";
import { DealScoreBadge, StatusBadge } from "@/components/DealBadges";
import { LoadingState, ErrorState } from "@/components/DataStates";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { Inbox } from "lucide-react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Calendar, User } from "lucide-react";
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd";
import { useToast } from "@/hooks/use-toast";
import type { Deal } from "@/types/deal";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

const columns = ['new', 'qualified', 'underwriting', 'ic-review', 'loi-sent', 'psa', 'closing', 'dead'] as const;

export default function Pipeline() {
  const navigate = useNavigate();
  const { data: fetchedDeals, isLoading, error, refetch } = useDeals();
  const moveStage = useMoveStage();
  const { toast } = useToast();

  // Local state for optimistic drag-and-drop
  const [localDeals, setLocalDeals] = useState<Deal[] | null>(null);
  const dealData = localDeals ?? (fetchedDeals as Deal[] | undefined) ?? [];

  // Sync from server when data arrives
  if (fetchedDeals && !localDeals) {
    // Will set on first render after data loads
  }

  const grouped = columns.map(col => ({
    key: col,
    label: stageLabels[col] ?? col,
    deals: dealData.filter((d) => d.status === col),
  }));

  const onDragEnd = (result: DropResult) => {
    const { source, destination } = result;
    if (!destination) return;
    if (source.droppableId === destination.droppableId && source.index === destination.index) return;

    const sourceCol = source.droppableId as Deal['status'];
    const destCol = destination.droppableId as Deal['status'];
    const currentDeals = [...dealData];

    const sourceDeals = currentDeals.filter((d) => d.status === sourceCol);
    const [moved] = sourceDeals.splice(source.index, 1);
    const updatedDeal = { ...moved, status: destCol };

    if (sourceCol === destCol) {
      sourceDeals.splice(destination.index, 0, updatedDeal);
      const otherDeals = currentDeals.filter((d) => d.status !== sourceCol);
      setLocalDeals([...otherDeals, ...sourceDeals]);
    } else {
      const destDeals = currentDeals.filter((d) => d.status === destCol);
      destDeals.splice(destination.index, 0, updatedDeal);
      const otherDeals = currentDeals.filter((d) => d.status !== sourceCol && d.status !== destCol);
      setLocalDeals([...otherDeals, ...sourceDeals, ...destDeals]);

      // Call API
      moveStage.mutate(
        { dealId: moved.id, data: { targetStage: destCol } },
        {
          onError: () => {
            toast({ title: "Move failed", description: "Could not update stage on server.", variant: "destructive" });
          },
        }
      );

      toast({
        title: "Deal moved",
        description: `${moved.name} → ${stageLabels[destCol]}`,
      });
    }
  };

  const analyticsData = columns.filter(c => c !== 'dead').map(col => ({
    stage: stageLabels[col] ?? col,
    count: dealData.filter((d) => d.status === col).length,
  }));

  // Source distribution derived from current deal data
  const sourceMap = new Map<string, number>();
  dealData.forEach(d => {
    const src = d.source || 'Unknown';
    sourceMap.set(src, (sourceMap.get(src) || 0) + 1);
  });
  const totalDeals = dealData.length || 1;
  const sourceDistribution = Array.from(sourceMap.entries())
    .map(([source, count]) => ({ source, rate: Math.round((count / totalDeals) * 100) }))
    .sort((a, b) => b.rate - a.rate)
    .slice(0, 5);

  if (isLoading) {
    return <Layout><LoadingState message="Loading pipeline..." /></Layout>;
  }

  if (error) {
    return <Layout><ErrorState message="Failed to load pipeline." onRetry={() => refetch()} /></Layout>;
  }

  if (dealData.length === 0) {
    return (
      <Layout>
        <div className="p-4 md:p-6 max-w-[1600px] mx-auto">
          <div className="mb-5 md:mb-6">
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Pipeline</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Track acquisition progress from sourcing to close</p>
          </div>
          <Card className="card-shadow">
            <CardContent className="flex flex-col items-center justify-center text-center py-16 px-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary mb-4">
                <Inbox className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-base font-semibold text-foreground">Your pipeline is empty</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                Add deals from the inbox and drag them across stages to track progress.
              </p>
              <Button asChild className="mt-4">
                <Link to="/inbox">Add your first deal</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-4 md:p-6 max-w-[1600px] mx-auto">
        <motion.div {...fadeIn} className="mb-5 md:mb-6">
          <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Pipeline</h2>
          <p className="text-sm text-muted-foreground mt-0.5">Track acquisition progress from sourcing to close</p>
        </motion.div>

        {/* Kanban */}
        <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="overflow-x-auto pb-4 mb-6 md:mb-8 -mx-4 md:mx-0 px-4 md:px-0">
          <DragDropContext onDragEnd={onDragEnd}>
            <div className="flex gap-3 md:gap-4" style={{ minWidth: `${columns.length * 200}px` }}>
              {grouped.map(col => (
                <Droppable key={col.key} droppableId={col.key}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`w-48 md:w-56 shrink-0 rounded-lg p-2 transition-colors ${
                        snapshot.isDraggingOver ? 'bg-primary/5 ring-1 ring-primary/20' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3 px-1">
                        <span className="text-[10px] md:text-xs font-semibold text-foreground uppercase tracking-wider">{col.label}</span>
                        <span className="text-[10px] md:text-xs text-muted-foreground bg-secondary rounded-full px-2 py-0.5">{col.deals.length}</span>
                      </div>
                      <div className="space-y-2 md:space-y-2.5 min-h-[200px]">
                        {col.deals.map((deal, index: number) => (
                          <Draggable key={deal.id} draggableId={deal.id} index={index}>
                            {(provided, snapshot) => (
                              <div
                                ref={provided.innerRef}
                                {...provided.draggableProps}
                                {...provided.dragHandleProps}
                                onClick={() => navigate(`/deal/${deal.id}`)}
                                className={`rounded-lg border bg-card p-3 md:p-3.5 card-shadow cursor-grab active:cursor-grabbing hover:card-shadow-hover transition-shadow ${
                                  snapshot.isDragging ? 'shadow-lg ring-2 ring-primary/30 rotate-1' : ''
                                }`}
                              >
                                <div className="flex items-start justify-between mb-2">
                                  <p className="text-xs md:text-sm font-medium text-foreground leading-tight">{deal.name}</p>
                                  <DealScoreBadge score={deal.dealScore} />
                                </div>
                                <p className="text-[10px] md:text-xs text-muted-foreground mb-2">{deal.market}</p>
                                <div className="flex items-center justify-between text-[10px] md:text-xs">
                                  <span className="text-muted-foreground">{deal.projectedIrr}% IRR</span>
                                  <StatusBadge status={deal.riskLevel} label={deal.riskLevel} />
                                </div>
                                <div className="flex items-center justify-between mt-2 pt-2 border-t text-[10px] md:text-xs text-muted-foreground">
                                  <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{deal.dueDate || '—'}</span>
                                  <span className="flex items-center gap-1"><User className="h-3 w-3" />{(deal.owner || '').split(' ')[0]}</span>
                                </div>
                              </div>
                            )}
                          </Draggable>
                        ))}
                        {provided.placeholder}
                      </div>
                    </div>
                  )}
                </Droppable>
              ))}
            </div>
          </DragDropContext>
        </motion.div>

        {/* Pipeline Analytics */}
        <motion.div {...fadeIn} transition={{ delay: 0.2 }}>
          <h3 className="text-sm font-semibold text-foreground mb-4">Pipeline Analytics</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-6">
            <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Deals by Stage</h4>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={analyticsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 13% 91%)" />
                  <XAxis dataKey="stage" tick={{ fontSize: 9, fill: 'hsl(215 13% 50%)' }} />
                  <YAxis tick={{ fontSize: 10, fill: 'hsl(215 13% 50%)' }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="hsl(215 28% 17%)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Deals by Source</h4>
              <div className="space-y-3">
                {sourceDistribution.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No data available.</p>
                ) : sourceDistribution.map(s => (
                  <div key={s.source}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted-foreground">{s.source}</span>
                      <span className="text-xs font-semibold text-foreground">{s.rate}%</span>
                    </div>
                    <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-accent rounded-full" style={{ width: `${s.rate}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">Pipeline Summary</h4>
              <div className="space-y-4">
                {[
                  { label: 'Total Active Deals', value: String(dealData.filter(d => d.status !== 'dead').length) },
                  { label: 'Pipeline Value', value: formatCurrency(dealData.filter(d => d.status !== 'dead').reduce((a, d) => a + (d.askingPrice ?? 0), 0)) },
                  { label: 'Avg Deal Score', value: dealData.length > 0 ? String(Math.round(dealData.reduce((a, d) => a + (d.dealScore ?? 0), 0) / dealData.length)) : '—' },
                  { label: 'High Priority (≥80)', value: String(dealData.filter(d => (d.dealScore ?? 0) >= 80).length) },
                  { label: 'Dead / Archived', value: String(dealData.filter(d => d.status === 'dead').length) },
                ].map((m, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{m.label}</span>
                    <span className="text-sm font-semibold text-foreground">{m.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </Layout>
  );
}
