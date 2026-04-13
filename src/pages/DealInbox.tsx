import { useState } from "react";
import { Layout } from "@/components/Layout";
import { DealScoreBadge, StatusBadge } from "@/components/DealBadges";
import { formatCurrency, stageLabels } from "@/lib/formatters";
import { useDeals, useCreateDeal } from "@/hooks/useDeals";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import type { Deal } from "@/types/deal";
import { useNavigate } from "react-router-dom";
import { Plus, Upload, Sparkles, Search, X, ChevronRight, Filter, Loader2, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AddDealModal } from "@/components/AddDealModal";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";

const tabs = [
  { key: 'all', label: 'All Deals' },
  { key: 'new', label: 'New' },
  { key: 'review', label: 'Needs Review' },
  { key: 'priority', label: 'High Priority' },
  { key: 'dead', label: 'Archived' },
];

const assetTypes = ['All', 'Multifamily', 'Retail', 'Industrial', 'Mixed Use'];
const markets = ['All', 'Phoenix, AZ', 'Tampa, FL', 'Austin, TX', 'Nashville, TN', 'Charlotte, NC', 'Dallas, TX', 'Denver, CO', 'Atlanta, GA', 'Orlando, FL'];

export default function DealInbox() {
  const navigate = useNavigate();
  const { data: allDeals, isLoading, error, refetch } = useDeals();
  const createDeal = useCreateDeal();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState('all');
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [filterAsset, setFilterAsset] = useState('All');
  const [filterMarket, setFilterMarket] = useState('All');
  const [search, setSearch] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [enrichProgress, setEnrichProgress] = useState(0);

  const deals = allDeals ?? [];

  const handleAddDeal = (form: { name: string; address: string; market: string; assetClass: string; askingPrice: string; source: string }) => {
    createDeal.mutate(
      {
        name: form.name,
        address: form.address || undefined,
        market: form.market,
        assetClass: form.assetClass,
        askingPrice: form.askingPrice ? parseInt(form.askingPrice.replace(/\D/g, '')) : undefined,
        source: form.source || undefined,
      },
      {
        onSuccess: () => {
          toast({ title: "Deal added", description: `${form.name} has been added to your inbox.` });
        },
        onError: () => {
          toast({ title: "Failed to add deal", description: "Backend unavailable.", variant: "destructive" });
        },
      }
    );
  };

  // Enrichment is a backend batch operation — we show a progress indicator
  // while waiting for the API to complete, then refetch
  const handleEnrichment = async () => {
    if (enriching || deals.length === 0) return;
    setEnriching(true);
    setEnrichProgress(0);

    try {
      // Enrich all deals via their individual endpoints
      const enrichPromises = deals.map(d =>
        fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/deals/${d.id}/enrich`, { method: 'POST' })
      );

      // Track progress as promises resolve
      let completed = 0;
      await Promise.allSettled(
        enrichPromises.map(p =>
          p.then(res => {
            completed++;
            setEnrichProgress(Math.round((completed / deals.length) * 100));
            return res;
          })
        )
      );

      toast({ title: "AI Enrichment Complete", description: `${deals.length} deals enriched.` });
      refetch();
    } catch {
      toast({ title: "Enrichment failed", description: "Could not reach the backend.", variant: "destructive" });
    } finally {
      setEnriching(false);
      setEnrichProgress(0);
    }
  };

  const filtered = deals.filter((deal) => {
    if (activeTab === 'new' && deal.status !== 'new') return false;
    if (activeTab === 'review' && deal.dealScore < 70) return false;
    if (activeTab === 'priority' && deal.dealScore < 80) return false;
    if (activeTab === 'dead' && deal.status !== 'dead') return false;
    if (activeTab === 'all' && deal.status === 'dead') return false;
    if (filterAsset !== 'All' && deal.assetClass !== filterAsset) return false;
    if (filterMarket !== 'All' && deal.market !== filterMarket) return false;
    if (search && !deal.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (isLoading) {
    return <Layout><LoadingState message="Loading deals..." /></Layout>;
  }

  if (error) {
    return <Layout><ErrorState message="Failed to load deals." onRetry={() => refetch()} /></Layout>;
  }

  return (
    <Layout>
      <div className="p-4 md:p-6 max-w-[1400px] mx-auto">
        {/* Enrichment Progress Banner */}
        <AnimatePresence>
          {enriching && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="mb-4 rounded-xl border bg-card p-4 flex items-center gap-4"
            >
              <div className="shrink-0">
                {enrichProgress < 100 ? (
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                ) : (
                  <CheckCircle2 className="h-5 w-5 text-green-500 dark:text-green-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {enrichProgress < 100 ? 'Running AI Enrichment...' : 'Enrichment Complete'}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {enrichProgress < 100 ? 'Analyzing market data, comps, and risk signals' : 'All deals updated with latest insights'}
                </p>
                <Progress value={enrichProgress} className="mt-2 h-1.5" />
              </div>
              <span className="text-xs font-medium text-muted-foreground tabular-nums">{enrichProgress}%</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 md:mb-6">
          <div>
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Deal Inbox</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Triage and manage incoming opportunities</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button className="hidden sm:flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary/80 transition-colors">
              <Upload className="h-3.5 w-3.5" /> Import CSV
            </button>
            <button
              onClick={handleEnrichment}
              disabled={enriching}
              className="hidden md:flex items-center gap-2 rounded-lg bg-accent/15 px-3 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/25 transition-colors disabled:opacity-60"
            >
              {enriching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {enriching ? 'Enriching...' : 'Run AI Enrichment'}
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Add Deal
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-4 border-b overflow-x-auto scrollbar-hide">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 md:px-4 py-2.5 text-sm font-medium transition-colors relative whitespace-nowrap ${
                activeTab === tab.key ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
              {activeTab === tab.key && (
                <motion.div layoutId="inbox-tab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
              )}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
          <div className="flex items-center gap-2 rounded-lg bg-card border px-3 py-1.5 w-full sm:w-auto">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search deals..."
              className="bg-transparent text-sm outline-none w-full sm:w-48 placeholder:text-muted-foreground" />
          </div>
          <button className="sm:hidden flex items-center gap-2 text-sm text-muted-foreground" onClick={() => setShowFilters(!showFilters)}>
            <Filter className="h-3.5 w-3.5" /> Filters
          </button>
          <div className={`${showFilters ? 'flex' : 'hidden'} sm:flex items-center gap-3 flex-wrap`}>
            <select value={filterAsset} onChange={e => setFilterAsset(e.target.value)} className="rounded-lg border bg-card px-3 py-1.5 text-sm text-foreground outline-none">
              {assetTypes.map(t => <option key={t}>{t}</option>)}
            </select>
            <select value={filterMarket} onChange={e => setFilterMarket(e.target.value)} className="rounded-lg border bg-card px-3 py-1.5 text-sm text-foreground outline-none">
              {markets.map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
        </div>

        <div className="flex gap-5 md:gap-6">
          {/* Table */}
          <div className={`flex-1 rounded-xl border bg-card card-shadow overflow-hidden min-w-0 ${selectedDeal ? 'hidden lg:block lg:max-w-[calc(100%-380px)]' : ''}`}>
            {filtered.length === 0 ? (
              <EmptyState title="No deals found" description="Try adjusting your filters or add a new deal." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-muted-foreground bg-secondary/50">
                      <th className="px-4 md:px-5 py-3 text-left font-medium">Deal Name</th>
                      <th className="px-3 py-3 text-left font-medium hidden sm:table-cell">Source</th>
                      <th className="px-3 py-3 text-left font-medium hidden md:table-cell">Market</th>
                      <th className="px-3 py-3 text-left font-medium hidden lg:table-cell">Type</th>
                      <th className="px-3 py-3 text-right font-medium hidden sm:table-cell">Asking Price</th>
                      <th className="px-3 py-3 text-right font-medium hidden xl:table-cell">Est. NOI</th>
                      <th className="px-3 py-3 text-center font-medium">Score</th>
                      <th className="px-3 py-3 text-left font-medium hidden md:table-cell">Status</th>
                      <th className="px-3 py-3 text-left font-medium hidden xl:table-cell">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((deal) => (
                      <tr
                        key={deal.id}
                        onClick={() => setSelectedDeal(deal)}
                        onDoubleClick={() => navigate(`/deal/${deal.id}`)}
                        className={`border-t cursor-pointer transition-colors ${selectedDeal?.id === deal.id ? 'bg-secondary' : 'hover:bg-secondary/30'}`}
                      >
                        <td className="px-4 md:px-5 py-3 font-medium text-foreground">{deal.name}</td>
                        <td className="px-3 py-3 text-muted-foreground hidden sm:table-cell">{deal.source}</td>
                        <td className="px-3 py-3 text-muted-foreground hidden md:table-cell">{(deal.market || '').split(',')[0]}</td>
                        <td className="px-3 py-3 text-muted-foreground hidden lg:table-cell">{deal.assetClass}</td>
                        <td className="px-3 py-3 text-right font-medium tabular-nums hidden sm:table-cell">{formatCurrency(deal.askingPrice)}</td>
                        <td className="px-3 py-3 text-right tabular-nums text-muted-foreground hidden xl:table-cell">{formatCurrency(deal.noi)}</td>
                        <td className="px-3 py-3 text-center"><DealScoreBadge score={deal.dealScore} /></td>
                        <td className="px-3 py-3 hidden md:table-cell"><StatusBadge status={deal.status} label={stageLabels[deal.status]} /></td>
                        <td className="px-3 py-3 text-muted-foreground text-xs hidden xl:table-cell">{deal.lastUpdated}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Quick Preview Drawer */}
          <AnimatePresence>
            {selectedDeal && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="w-full lg:w-[360px] shrink-0 rounded-xl border bg-card card-shadow overflow-hidden"
              >
                <div className="p-4 md:p-5 border-b flex items-start justify-between">
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-foreground truncate">{selectedDeal.name}</h3>
                    <p className="text-xs text-muted-foreground mt-1 truncate">{selectedDeal.address}</p>
                  </div>
                  <button onClick={() => setSelectedDeal(null)} className="text-muted-foreground hover:text-foreground shrink-0 ml-2">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="p-4 md:p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Deal Score</span>
                    <DealScoreBadge score={selectedDeal.dealScore} size="lg" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><p className="text-xs text-muted-foreground">Asking Price</p><p className="text-sm font-semibold mt-0.5">{formatCurrency(selectedDeal.askingPrice)}</p></div>
                    <div><p className="text-xs text-muted-foreground">NOI</p><p className="text-sm font-semibold mt-0.5">{formatCurrency(selectedDeal.noi)}</p></div>
                    <div><p className="text-xs text-muted-foreground">Projected IRR</p><p className="text-sm font-semibold mt-0.5">{selectedDeal.projectedIrr}%</p></div>
                    <div><p className="text-xs text-muted-foreground">Equity Multiple</p><p className="text-sm font-semibold mt-0.5">{selectedDeal.equityMultiple}x</p></div>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1.5">Summary</p>
                    <p className="text-xs text-foreground leading-relaxed line-clamp-4">{selectedDeal.summary}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <StatusBadge status={selectedDeal.status} label={stageLabels[selectedDeal.status]} />
                    <StatusBadge status={selectedDeal.riskLevel} label={`${selectedDeal.riskLevel} risk`} />
                  </div>
                  <button
                    onClick={() => navigate(`/deal/${selectedDeal.id}`)}
                    className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    Open Deal <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      <AddDealModal open={showAddModal} onOpenChange={setShowAddModal} onAdd={handleAddDeal} />
    </Layout>
  );
}
