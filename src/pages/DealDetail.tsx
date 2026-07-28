import { useParams, useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DealScoreBadge, RiskChip, StatusBadge } from "@/components/DealBadges";
import { formatCurrency, stageLabels, getScoreColor } from "@/lib/formatters";
import { useDealDetail } from "@/hooks/useDealDetail";
import { useActivities } from "@/hooks/useActivities";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import { OpportunityGraphPanel } from "@/components/OpportunityGraphPanel";
import { RetailPermitSignalsPanel } from "@/components/RetailPermitSignalsPanel";
import { NearbyParcelsPanel } from "@/components/NearbyParcelsPanel";
import { ArrowLeft, MapPin, Building2, Calendar, Ruler, User, FileText, Lightbulb, AlertTriangle, CheckCircle, MessageSquare, Zap } from "lucide-react";
import { motion } from "framer-motion";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

export default function DealDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: deal, isLoading, error, refetch } = useDealDetail(id);
  const { data: activities } = useActivities(id || '');

  const activityIcons: Record<string, React.ReactNode> = {
    note: <MessageSquare className="h-3.5 w-3.5" />,
    status: <CheckCircle className="h-3.5 w-3.5" />,
    comment: <MessageSquare className="h-3.5 w-3.5" />,
    enrichment: <Zap className="h-3.5 w-3.5" />,
    score: <Lightbulb className="h-3.5 w-3.5" />,
  };

  if (isLoading) {
    return <Layout><LoadingState message="Loading deal..." /></Layout>;
  }

  if (error) {
    return <Layout><ErrorState message="Failed to load deal." onRetry={() => refetch()} /></Layout>;
  }

  if (!deal) {
    return (
      <Layout>
        <EmptyState title="Deal not found" description="This deal may have been removed or the ID is invalid." />
      </Layout>
    );
  }

  const activityList = activities ?? [];

  return (
    <Layout>
      <div className="p-4 md:p-6 max-w-[1400px] mx-auto">
        {/* Header */}
        <motion.div {...fadeIn} className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5 md:mb-6">
          <button onClick={() => navigate(-1)} className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-muted-foreground hover:text-foreground transition-colors shrink-0 self-start">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground truncate">{deal.name}</h2>
            <p className="text-sm text-muted-foreground truncate">{deal.address}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={deal.status} label={stageLabels[deal.status] ?? deal.status} />
            <StatusBadge status={deal.riskLevel} label={`${deal.riskLevel} risk`} />
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 md:gap-6">
          {/* Left Column */}
          <div className="lg:col-span-2 space-y-4 md:space-y-5">
            {/* Property Overview */}
            <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <h3 className="text-sm font-semibold text-foreground mb-4">Property Overview</h3>
              <div className="space-y-3">
                {[
                  { icon: <MapPin className="h-3.5 w-3.5" />, label: 'Market', value: deal.market },
                  { icon: <Building2 className="h-3.5 w-3.5" />, label: 'Asset Type', value: deal.assetClass },
                  { icon: <Calendar className="h-3.5 w-3.5" />, label: 'Year Built', value: String(deal.yearBuilt ?? '—') },
                  { icon: <Ruler className="h-3.5 w-3.5" />, label: (deal.units ?? 0) > 0 ? 'Units' : 'Square Feet', value: (deal.units ?? 0) > 0 ? `${deal.units} units` : `${(deal.squareFeet ?? 0).toLocaleString()} SF` },
                  { icon: <User className="h-3.5 w-3.5" />, label: 'Broker', value: deal.broker ?? '—' },
                  { icon: <FileText className="h-3.5 w-3.5" />, label: 'Source', value: deal.source ?? '—' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      {item.icon}
                      <span className="text-xs">{item.label}</span>
                    </div>
                    <span className="text-sm font-medium text-foreground">{item.value}</span>
                  </div>
                ))}
                <div className="pt-2 border-t flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Asking Price</span>
                  <span className="text-lg font-semibold font-display text-foreground">{formatCurrency(deal.askingPrice)}</span>
                </div>
              </div>
              <div className="mt-4 h-36 rounded-lg bg-secondary flex items-center justify-center text-xs text-muted-foreground">
                <MapPin className="h-4 w-4 mr-1" /> Map view
              </div>
            </motion.div>

            {/* Deal Score */}
            {deal.subscores && (
              <motion.div {...fadeIn} transition={{ delay: 0.15 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-foreground">Deal Score</h3>
                  <DealScoreBadge score={deal.dealScore} size="lg" />
                </div>
                <div className="space-y-3">
                  {[
                    { label: 'Market Attractiveness', score: deal.subscores.marketAttractiveness },
                    { label: 'Financial Upside', score: deal.subscores.financialUpside },
                    { label: 'Operational Complexity', score: deal.subscores.operationalComplexity },
                    { label: 'Permitting Risk', score: deal.subscores.permittingRisk },
                    { label: 'Execution Speed', score: deal.subscores.executionSpeed },
                  ].map((item, i) => (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-muted-foreground">{item.label}</span>
                        <span className={`text-xs font-semibold ${getScoreColor(item.score)}`}>{item.score}</span>
                      </div>
                      <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-primary/50 transition-all" style={{ width: `${item.score}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* Risk Flags */}
            {(deal.riskFlags?.length ?? 0) > 0 && (
              <motion.div {...fadeIn} transition={{ delay: 0.2 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <h3 className="text-sm font-semibold text-foreground mb-3">Risk Flags</h3>
                <div className="flex flex-wrap gap-2">
                  {deal.riskFlags.map((flag, i) => <RiskChip key={i} label={flag} />)}
                </div>
              </motion.div>
            )}

            {/* Document Vault */}
            {(deal.documents?.length ?? 0) > 0 && (
              <motion.div {...fadeIn} transition={{ delay: 0.25 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <h3 className="text-sm font-semibold text-foreground mb-3">Document Vault</h3>
                <div className="space-y-2">
                  {deal.documents.map((doc, i) => (
                    <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors cursor-pointer">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="text-sm text-foreground truncate">{doc.name}</span>
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0 ml-2">{doc.type}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </div>

          {/* Right Column */}
          <div className="lg:col-span-3 space-y-4 md:space-y-5">
            {/* Key Metrics */}
            <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Projected IRR', value: `${deal.projectedIrr ?? 0}%` },
                { label: 'Equity Multiple', value: `${deal.equityMultiple ?? 0}x` },
                { label: 'Cash on Cash', value: `${deal.cashOnCash ?? 0}%` },
                { label: 'Est. NOI', value: formatCurrency(deal.noi ?? 0) },
              ].map((m, i) => (
                <div key={i} className="rounded-xl border bg-card p-3 md:p-4 card-shadow text-center">
                  <p className="text-xs text-muted-foreground">{m.label}</p>
                  <p className="text-lg md:text-xl font-semibold font-display mt-1 text-foreground">{m.value}</p>
                </div>
              ))}
            </motion.div>

            <motion.div {...fadeIn} transition={{ delay: 0.12 }}>
              <RetailPermitSignalsPanel dealId={id} />
            </motion.div>

            <motion.div {...fadeIn} transition={{ delay: 0.12 }}>
              <NearbyParcelsPanel dealId={id} />
            </motion.div>

            <motion.div {...fadeIn} transition={{ delay: 0.12 }}>
              <OpportunityGraphPanel dealId={id} />
            </motion.div>

            {/* AI Summary */}
            {deal.summary && (
              <motion.div {...fadeIn} transition={{ delay: 0.15 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <div className="flex items-center gap-2 mb-3">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15">
                    <Lightbulb className="h-3.5 w-3.5 text-accent" />
                  </div>
                  <h3 className="text-sm font-semibold text-foreground">AI Summary</h3>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">{deal.summary}</p>
              </motion.div>
            )}

            {/* Investment Thesis */}
            {deal.thesis && (
              <motion.div {...fadeIn} transition={{ delay: 0.2 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <h3 className="text-sm font-semibold text-foreground mb-3">Investment Thesis</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{deal.thesis}</p>
              </motion.div>
            )}

            {/* Key Risks */}
            {(deal.risks?.length ?? 0) > 0 && (
              <motion.div {...fadeIn} transition={{ delay: 0.25 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className="h-4 w-4 text-warning" />
                  <h3 className="text-sm font-semibold text-foreground">Key Risks</h3>
                </div>
                <ul className="space-y-2">
                  {deal.risks.map((risk, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-warning shrink-0" />
                      {risk}
                    </li>
                  ))}
                </ul>
              </motion.div>
            )}

            {/* Next Steps */}
            {(deal.nextSteps?.length ?? 0) > 0 && (
              <motion.div {...fadeIn} transition={{ delay: 0.3 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <h3 className="text-sm font-semibold text-foreground mb-3">Recommended Next Actions</h3>
                <ul className="space-y-2">
                  {deal.nextSteps.map((step, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <CheckCircle className="h-4 w-4 text-success shrink-0 mt-0.5" />
                      {step}
                    </li>
                  ))}
                </ul>
              </motion.div>
            )}

            {/* Activity Feed — from dedicated endpoint */}
            <motion.div {...fadeIn} transition={{ delay: 0.35 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
              <h3 className="text-sm font-semibold text-foreground mb-4">Activity</h3>
              {activityList.length === 0 ? (
                <p className="text-sm text-muted-foreground">No activity yet.</p>
              ) : (
                <div className="space-y-4">
                  {activityList.map((item) => (
                    <div key={item.id} className="flex gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-muted-foreground">
                        {activityIcons[item.type]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground">{item.content}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{item.user} · {item.date}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
