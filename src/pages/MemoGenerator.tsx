import { useState, useEffect } from "react";
import { Layout } from "@/components/Layout";
import { useDeals } from "@/hooks/useDeals";
import { useMemo as useDealMemo, useGenerateMemo, useUpdateMemo } from "@/hooks/useMemo";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import { motion } from "framer-motion";
import { FileEdit, RefreshCw, Download, Copy, Share2, ChevronDown, ChevronRight } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import type { Memo } from "@/types/memo";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

const sections = [
  { key: 'executiveSummary', label: 'Executive Summary' },
  { key: 'whyThisDeal', label: 'Why This Deal' },
  { key: 'propertyOverview', label: 'Property Overview' },
  { key: 'marketOverview', label: 'Market Overview' },
  { key: 'financialSummary', label: 'Financial Summary' },
  { key: 'risksAndMitigants', label: 'Risks & Mitigants' },
  { key: 'valueCreationPlan', label: 'Value Creation Plan' },
  { key: 'recommendedAction', label: 'Recommended Action' },
] as const;

type SectionKey = typeof sections[number]['key'];

export default function MemoGenerator() {
  const { data: deals, isLoading: dealsLoading, error: dealsError, refetch: refetchDeals } = useDeals();
  const dealList = deals ?? [];

  const [selectedDealId, setSelectedDealId] = useState('');
  const [localMemo, setLocalMemo] = useState<Record<string, string>>({});
  const [activeSection, setActiveSection] = useState<string>('executiveSummary');
  const [regeneratingKey, setRegeneratingKey] = useState<string | null>(null);
  const generateMemo = useGenerateMemo();
  const updateMemo = useUpdateMemo();
  const { toast } = useToast();

  useEffect(() => {
    if (dealList.length > 0 && !selectedDealId) {
      setSelectedDealId(dealList[0].id);
    }
  }, [dealList, selectedDealId]);

  const deal = dealList.find((d) => d.id === selectedDealId);

  // Fetch memo from dedicated endpoint
  const { data: backendMemo, isLoading: memoLoading } = useDealMemo(selectedDealId);

  // Seed local state from backend memo
  useEffect(() => {
    if (backendMemo) {
      setLocalMemo({ ...(backendMemo as unknown as Record<string, string>) });
    }
  }, [backendMemo, selectedDealId]);

  if (dealsLoading) {
    return <Layout><LoadingState message="Loading deals..." /></Layout>;
  }

  if (dealsError) {
    return <Layout><ErrorState message="Failed to load deals." onRetry={() => refetchDeals()} /></Layout>;
  }

  if (dealList.length === 0) {
    return <Layout><EmptyState title="No deals available" description="Add deals to generate memos." /></Layout>;
  }

  if (!deal) {
    return <Layout><EmptyState title="Select a deal" description="Choose a deal from the dropdown." /></Layout>;
  }

  const handleGenerate = () => {
    generateMemo.mutate(deal.id, {
      onSuccess: (data) => {
        setLocalMemo({ ...(data as unknown as Record<string, string>) });
        toast({ title: "Memo generated", description: `Investment memo created for ${deal.name}.` });
      },
      onError: () => {
        toast({ title: "Generation failed", description: "Could not generate memo. Check backend connection.", variant: "destructive" });
      },
    });
  };

  const handleRegenerate = (key: string) => {
    if (regeneratingKey) return;  // one section at a time — avoids interleaved writes
    const prior = localMemo[key] ?? '';  // snapshot to restore on failure/empty
    setRegeneratingKey(key);
    setLocalMemo(prev => ({ ...prev, [key]: 'Regenerating...' }));
    generateMemo.mutate(deal.id, {
      onSuccess: (data) => {
        const section = (data as unknown as Record<string, string>)[key];
        // Fall back to the PRIOR content (not the "Regenerating..." placeholder)
        // if the response has nothing for this section.
        setLocalMemo(prev => ({ ...prev, [key]: section || prior }));
      },
      onError: () => {
        setLocalMemo(prev => ({ ...prev, [key]: prior }));  // restore — no stuck placeholder
        toast({ title: "Regeneration failed", description: "Could not regenerate section.", variant: "destructive" });
      },
      onSettled: () => setRegeneratingKey(null),
    });
  };

  const handleSaveMemo = () => {
    updateMemo.mutate(
      { dealId: deal.id, data: localMemo as unknown as Memo },
      {
        onSuccess: () => toast({ title: "Memo saved" }),
        onError: () => toast({ title: "Save failed", variant: "destructive" }),
      }
    );
  };

  return (
    <Layout>
      <div className="p-6 max-w-[1400px] mx-auto">
        <motion.div {...fadeIn} className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-5 md:mb-6">
          <div>
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Memo Generator</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Investment Committee Memo</p>
          </div>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
            <Select value={selectedDealId} onValueChange={setSelectedDealId}>
              <SelectTrigger className="w-full sm:w-[260px]">
                <SelectValue placeholder="Select a deal" />
              </SelectTrigger>
              <SelectContent>
                {dealList.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.name} — {d.market}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <button onClick={handleGenerate} disabled={generateMemo.isPending}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50">
                <FileEdit className="h-3.5 w-3.5" />
                {generateMemo.isPending ? 'Generating...' : 'Generate Memo'}
              </button>
              <button onClick={handleSaveMemo} disabled={updateMemo.isPending}
                className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50">
                {updateMemo.isPending ? 'Saving...' : 'Save'}
              </button>
              <button className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary/80 transition-colors">
                <Download className="h-3.5 w-3.5" /> Export PDF
              </button>
              <button className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary/80 transition-colors">
                <Copy className="h-3.5 w-3.5" /> Copy
              </button>
              <button className="flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground hover:bg-secondary/80 transition-colors">
                <Share2 className="h-3.5 w-3.5" /> Share
              </button>
            </div>
          </div>
        </motion.div>

        {memoLoading ? (
          <LoadingState message="Loading memo..." />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Left: Section editor */}
            <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="lg:col-span-2 space-y-3">
              {sections.map(s => (
                <div key={s.key} className="rounded-xl border bg-card card-shadow overflow-hidden">
                  <button
                    onClick={() => setActiveSection(activeSection === s.key ? '' : s.key)}
                    className="flex items-center justify-between w-full p-4 text-left hover:bg-secondary/30 transition-colors"
                  >
                    <span className="text-sm font-medium text-foreground">{s.label}</span>
                    {activeSection === s.key ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                  </button>
                  {activeSection === s.key && (
                    <div className="px-4 pb-4">
                      <textarea
                        value={localMemo[s.key] || ''}
                        onChange={e => setLocalMemo(prev => ({ ...prev, [s.key]: e.target.value }))}
                        rows={5}
                        className="w-full rounded-lg border bg-background p-3 text-sm text-foreground outline-none resize-none focus:ring-1 focus:ring-ring"
                      />
                      <button
                        onClick={() => handleRegenerate(s.key)}
                        disabled={regeneratingKey !== null}
                        className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                      >
                        <RefreshCw className={`h-3 w-3 ${regeneratingKey === s.key ? 'animate-spin' : ''}`} />
                        {regeneratingKey === s.key ? 'Regenerating…' : 'Regenerate section'}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </motion.div>

            {/* Right: Live Preview */}
            <motion.div {...fadeIn} transition={{ delay: 0.2 }} className="lg:col-span-3">
              <div className="rounded-xl border bg-card card-shadow overflow-hidden">
                <div className="bg-primary px-8 py-6">
                  <p className="text-xs font-medium text-primary-foreground/60 uppercase tracking-widest">Investment Memorandum</p>
                  <h2 className="text-2xl font-bold font-display text-primary-foreground mt-2">{deal.name}</h2>
                  <p className="text-sm text-primary-foreground/70 mt-1">{deal.address}</p>
                  <div className="flex items-center gap-4 mt-3 text-xs text-primary-foreground/60">
                    <span>{deal.assetClass}</span>
                    <span>•</span>
                    <span>{deal.market}</span>
                    <span>•</span>
                    <span>{new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</span>
                  </div>
                </div>

                <div className="px-8 py-6 space-y-6">
                  {sections.map(s => {
                    const content = localMemo[s.key];
                    if (!content) return null;
                    return (
                      <div key={s.key}>
                        <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider mb-2">{s.label}</h3>
                        <p className="text-sm text-muted-foreground leading-relaxed">{content}</p>
                      </div>
                    );
                  })}

                  {Object.values(localMemo).every(v => !v) && (
                    <EmptyState title="No memo content" description="Click 'Generate Memo' to create an investment memo." />
                  )}

                  {/* Key Metrics Table */}
                  <div>
                    <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider mb-2">Key Metrics</h3>
                    <div className="grid grid-cols-4 gap-3">
                      {[
                        { label: 'IRR', value: `${deal.projectedIrr ?? 0}%` },
                        { label: 'Equity Multiple', value: `${deal.equityMultiple ?? 0}x` },
                        { label: 'Cash on Cash', value: `${deal.cashOnCash ?? 0}%` },
                        { label: 'Deal Score', value: `${deal.dealScore ?? 0}/100` },
                      ].map((m, i) => (
                        <div key={i} className="rounded-lg bg-secondary/50 p-3 text-center">
                          <p className="text-xs text-muted-foreground">{m.label}</p>
                          <p className="text-sm font-semibold mt-0.5">{m.value}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="border-t pt-4">
                    <p className="text-xs text-muted-foreground text-center">
                      Confidential — Prepared with DealSignal
                    </p>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </Layout>
  );
}
