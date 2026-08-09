import { Layout } from "@/components/Layout";
import { KpiCard } from "@/components/KpiCard";
import { DealScoreBadge, StatusBadge } from "@/components/DealBadges";
import { formatCurrency, stageLabels } from "@/lib/formatters";
import { useDashboardKpis, useTopOpportunities, usePipelineSnapshot, useRecentSignals, useAiInsights } from "@/hooks/useDashboard";
import { LoadingState, ErrorState } from "@/components/DataStates";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { GraphCoverageCard } from "@/components/GraphCoverageCard";
import { Inbox } from "lucide-react";
import { TrendingUp, Target, Star, DollarSign, BarChart3, Lightbulb, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";

const fadeIn = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4 },
};

const signalTypeIcon: Record<string, string> = {
  zoning: '🏗️', permit: '📋', listing: '🏠', ownership: '🔄', competitor: '⚡', demographic: '📊',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: kpis, isLoading: kpisLoading, error: kpisError, refetch: refetchKpis } = useDashboardKpis();
  const { data: topDeals } = useTopOpportunities();
  const { data: pipelineSnapshot } = usePipelineSnapshot();
  const { data: recentSignals } = useRecentSignals();
  const { data: insights } = useAiInsights();

  if (kpisLoading) {
    return <Layout><LoadingState message="Loading dashboard..." /></Layout>;
  }

  if (kpisError) {
    return <Layout><ErrorState message="Failed to load dashboard." onRetry={() => refetchKpis()} /></Layout>;
  }

  const activeCount = kpis?.pipelineDeals ?? 0;
  const hasNoDeals = (topDeals ?? []).length === 0 && activeCount === 0;

  if (hasNoDeals) {
    return (
      <Layout>
        <div className="p-4 md:p-6 max-w-[1400px] mx-auto">
          <div className="mb-5 md:mb-6">
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Dashboard</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Your acquisition engine at a glance</p>
          </div>
          <Card className="card-shadow">
            <CardContent className="flex flex-col items-center justify-center text-center py-16 px-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary mb-4">
                <Inbox className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-base font-semibold text-foreground">No deals yet</h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                Paste a listing URL or add a deal manually to start building your pipeline.
              </p>
              <Button asChild className="mt-4">
                <Link to="/inbox">Go to Deal Inbox</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-5 md:space-y-6 max-w-[1400px] mx-auto">
        <motion.div {...fadeIn}>
          <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Dashboard</h2>
          <p className="text-sm text-muted-foreground mt-0.5">Your acquisition engine at a glance</p>
        </motion.div>

        {/* KPIs */}
        <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
          <KpiCard label="Pipeline Deals" value={String(kpis?.pipelineDeals ?? 0)} change="+2 this week" changeType="positive" icon={<BarChart3 className="h-4 w-4" />} />
          <KpiCard label="Scored This Week" value={String(kpis?.scoredThisWeek ?? 0)} change="All enriched" changeType="neutral" icon={<Target className="h-4 w-4" />} />
          <KpiCard label="Avg Deal Score" value={String(kpis?.avgDealScore ?? 0)} change="+3 vs last week" changeType="positive" icon={<Star className="h-4 w-4" />} />
          <KpiCard label="High Priority" value={String(kpis?.highPriorityCount ?? 0)} change="Deals ≥ 80 score" changeType="neutral" icon={<TrendingUp className="h-4 w-4" />} />
          <KpiCard label="Pipeline Value" value={formatCurrency(kpis?.pipelineValue ?? 0)} change={kpis?.weeklyChange ?? ''} changeType="positive" icon={<DollarSign className="h-4 w-4" />} />
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 md:gap-6">
          {/* Top Opportunities */}
          <motion.div {...fadeIn} transition={{ delay: 0.2 }} className="lg:col-span-2">
            <div className="rounded-xl border bg-card card-shadow">
              <div className="flex items-center justify-between p-4 md:p-5 pb-3">
                <h3 className="text-sm font-semibold text-foreground">Top Opportunities</h3>
                <button onClick={() => navigate('/inbox')} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors">
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t text-xs text-muted-foreground">
                      <th className="px-4 md:px-5 py-3 text-left font-medium">Property</th>
                      <th className="px-3 py-3 text-left font-medium hidden sm:table-cell">Market</th>
                      <th className="px-3 py-3 text-left font-medium hidden md:table-cell">Type</th>
                      <th className="px-3 py-3 text-center font-medium">Score</th>
                      <th className="px-3 py-3 text-right font-medium hidden sm:table-cell">IRR</th>
                      <th className="px-3 py-3 text-left font-medium hidden lg:table-cell">Status</th>
                      <th className="px-3 py-3 text-left font-medium hidden xl:table-cell">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(topDeals ?? []).map((deal) => (
                      <tr
                        key={deal.id}
                        role="button"
                        tabIndex={0}
                        aria-label={`Open deal ${deal.name}`}
                        onClick={() => navigate(`/deal/${deal.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            navigate(`/deal/${deal.id}`);
                          }
                        }}
                        className="border-t cursor-pointer hover:bg-secondary/50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                      >
                        <td className="px-4 md:px-5 py-3 font-medium text-foreground">{deal.name}</td>
                        <td className="px-3 py-3 text-muted-foreground hidden sm:table-cell">{(deal.market || '').split(',')[0]}</td>
                        <td className="px-3 py-3 text-muted-foreground hidden md:table-cell">{deal.assetClass}</td>
                        <td className="px-3 py-3 text-center"><DealScoreBadge score={deal.dealScore} /></td>
                        <td className="px-3 py-3 text-right font-medium text-foreground hidden sm:table-cell">{deal.projectedIrr}%</td>
                        <td className="px-3 py-3 hidden lg:table-cell"><StatusBadge status={deal.status} label={stageLabels[deal.status]} /></td>
                        <td className="px-3 py-3 hidden xl:table-cell"><StatusBadge status={deal.riskLevel} label={deal.riskLevel} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>

          <div className="space-y-5 md:space-y-6">
            {/* Pipeline Snapshot */}
            <motion.div {...fadeIn} transition={{ delay: 0.3 }}>
              <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <h3 className="text-sm font-semibold text-foreground mb-4">Pipeline Snapshot</h3>
                <div className="space-y-3">
                  {(pipelineSnapshot ?? []).map((stage) => (
                    <div key={stage.stage} className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">{stage.label}</span>
                      <div className="flex items-center gap-3">
                        <div className="w-24 h-2 bg-secondary rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary/60 rounded-full transition-all"
                            style={{ width: `${activeCount > 0 ? (stage.count / activeCount) * 100 : 0}%` }}
                          />
                        </div>
                        <span className="text-sm font-semibold text-foreground w-4 text-right">{stage.count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>

            <motion.div {...fadeIn} transition={{ delay: 0.35 }}>
              <GraphCoverageCard opportunities={topDeals ?? []} />
            </motion.div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 md:gap-6">
          {/* Recent Market Signals */}
          <motion.div {...fadeIn} transition={{ delay: 0.4 }}>
            <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-foreground">Recent Signals</h3>
                <button onClick={() => navigate('/signals')} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                  View all <ArrowRight className="h-3 w-3" />
                </button>
              </div>
              <div className="space-y-3">
                {(recentSignals ?? []).map(signal => (
                  <div key={signal.id} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                    <span className="text-lg">{signalTypeIcon[signal.type]}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-foreground truncate">{signal.property}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{signal.summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* AI Insights */}
          <motion.div {...fadeIn} transition={{ delay: 0.5 }} className="lg:col-span-2">
            <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <div className="flex items-center gap-2 mb-4">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15">
                  <Lightbulb className="h-3.5 w-3.5 text-accent" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">AI Insights</h3>
              </div>
              <div className="space-y-3">
                {(insights ?? []).map((insight, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/50">
                    <div className="mt-0.5 h-1.5 w-1.5 rounded-full bg-accent shrink-0" />
                    <p className="text-sm text-muted-foreground leading-relaxed">{insight}</p>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </Layout>
  );
}
