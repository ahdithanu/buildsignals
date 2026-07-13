import { useState, useEffect, useRef } from "react";
import { Layout } from "@/components/Layout";
import { formatCurrency } from "@/lib/formatters";
import { useDeals } from "@/hooks/useDeals";
import { useAssumptions, useUpdateAssumptions, useOutputs } from "@/hooks/useAssumptions";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import { motion } from "framer-motion";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Lightbulb } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Assumptions } from "@/types/assumptions";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

export default function Underwriting() {
  const { data: deals, isLoading: dealsLoading, error: dealsError, refetch: refetchDeals } = useDeals();
  const dealList = deals ?? [];

  const [selectedDealId, setSelectedDealId] = useState('');

  useEffect(() => {
    if (dealList.length > 0 && !selectedDealId) {
      setSelectedDealId(dealList[0].id);
    }
  }, [dealList, selectedDealId]);

  const deal = dealList.find((d) => d.id === selectedDealId);

  // Fetch assumptions and outputs from dedicated endpoints
  const { data: backendAssumptions, isLoading: assumptionsLoading } = useAssumptions(selectedDealId);
  const { data: backendOutputs, isLoading: outputsLoading } = useOutputs(selectedDealId);
  const updateAssumptions = useUpdateAssumptions();

  // Local assumptions state for the sliders, seeded from backend.
  const [localAssumptions, setLocalAssumptions] = useState<Partial<Assumptions>>({});

  // Seed ONCE per deal. Previously this re-ran on every backendAssumptions
  // refetch (e.g. window focus), silently wiping the user's unsaved slider
  // edits. The ref makes it seed only when the selected deal actually changes.
  const seededDealRef = useRef<string | null>(null);
  useEffect(() => {
    if (backendAssumptions && seededDealRef.current !== selectedDealId) {
      setLocalAssumptions({ ...backendAssumptions });
      seededDealRef.current = selectedDealId;
    }
  }, [selectedDealId, backendAssumptions]);

  if (dealsLoading) {
    return <Layout><LoadingState message="Loading deals..." /></Layout>;
  }

  if (dealsError) {
    return <Layout><ErrorState message="Failed to load deals." onRetry={() => refetchDeals()} /></Layout>;
  }

  if (dealList.length === 0) {
    return <Layout><EmptyState title="No deals available" description="Add deals to start underwriting." /></Layout>;
  }

  if (!deal) {
    return <Layout><EmptyState title="Select a deal" description="Choose a deal from the dropdown above." /></Layout>;
  }

  const assumptions = localAssumptions as Assumptions;

  const update = (key: keyof Assumptions, value: number) => {
    setLocalAssumptions(prev => ({ ...prev, [key]: value }));
  };

  const handleRecalculate = () => {
    if (!selectedDealId || !assumptions) return;
    // The backend recomputes outputs from SAVED assumptions, so the current
    // on-screen slider values must be persisted first. PUT /assumptions saves
    // AND auto-recalculates outputs — so "Recalculate" now reflects what the
    // user actually sees, instead of the last-saved values.
    updateAssumptions.mutate({ dealId: selectedDealId, data: assumptions });
  };

  const handleSaveAssumptions = () => {
    if (!selectedDealId || !assumptions) return;
    updateAssumptions.mutate({ dealId: selectedDealId, data: assumptions });
  };

  // Use backend outputs when available, otherwise show empty
  const outputs = backendOutputs;
  const projectionData = outputs?.projections?.map(p => ({
    year: `Year ${p.year}`,
    NOI: Math.round(p.noi),
    Value: Math.round(p.value),
  })) ?? [];
  const scenarios = outputs?.scenarios ?? [];

  const fields: { label: string; key: keyof Assumptions; suffix: string; step: number }[] = [
    { label: 'Purchase Price', key: 'purchasePrice', suffix: '', step: 100000 },
    { label: 'Closing Costs', key: 'closingCosts', suffix: '', step: 10000 },
    { label: 'Renovation Cost', key: 'renovationCost', suffix: '', step: 50000 },
    { label: 'Exit Cap Rate', key: 'exitCapRate', suffix: '%', step: 0.25 },
    { label: 'Hold Period', key: 'holdPeriod', suffix: ' yrs', step: 1 },
    { label: 'Rent Growth', key: 'rentGrowth', suffix: '%', step: 0.5 },
    { label: 'Vacancy', key: 'vacancy', suffix: '%', step: 1 },
    { label: 'OpEx Ratio', key: 'opexRatio', suffix: '%', step: 1 },
    { label: 'LTV', key: 'ltv', suffix: '%', step: 5 },
    { label: 'Interest Rate', key: 'interestRate', suffix: '%', step: 0.25 },
    { label: 'Stabilization', key: 'stabilizationMonths', suffix: ' mo', step: 3 },
  ];

  return (
    <Layout>
      <div className="p-4 md:p-6 max-w-[1400px] mx-auto">
        <motion.div {...fadeIn} className="mb-5 md:mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div>
            <h2 className="text-lg md:text-xl font-semibold font-display text-foreground">Underwriting</h2>
            <p className="text-sm text-muted-foreground mt-0.5">Adjust assumptions and recalculate outputs</p>
          </div>
          <Select value={selectedDealId} onValueChange={setSelectedDealId}>
            <SelectTrigger className="w-full sm:w-[280px]">
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
        </motion.div>

        {assumptionsLoading ? (
          <LoadingState message="Loading assumptions..." />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 md:gap-6">
            {/* Left: Assumptions */}
            <div className="space-y-4 md:space-y-5">
              <motion.div {...fadeIn} transition={{ delay: 0.1 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-foreground">Assumptions</h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleRecalculate}
                      disabled={updateAssumptions.isPending}
                      className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                      {updateAssumptions.isPending ? 'Calculating...' : 'Recalculate'}
                    </button>
                    <button
                      onClick={handleSaveAssumptions}
                      disabled={updateAssumptions.isPending}
                      className="rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/80 transition-colors disabled:opacity-50"
                    >
                      {updateAssumptions.isPending ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                </div>
                <div className="space-y-3 md:space-y-4">
                  {fields.map(f => (
                    <div key={f.key} className="flex items-center justify-between gap-3 md:gap-4">
                      <label className="text-xs md:text-sm text-muted-foreground shrink-0 w-28 md:w-32">{f.label}</label>
                      <div className="flex items-center gap-1.5 md:gap-2">
                        <button
                          onClick={() => update(f.key, (assumptions[f.key] || 0) - f.step)}
                          className="h-7 w-7 rounded-md bg-secondary text-muted-foreground hover:text-foreground text-xs font-bold transition-colors shrink-0"
                        >−</button>
                        <span className="text-xs md:text-sm font-medium text-foreground tabular-nums w-20 md:w-24 text-center">
                          {f.suffix === '' ? formatCurrency(assumptions[f.key] || 0) : `${assumptions[f.key] || 0}${f.suffix}`}
                        </span>
                        <button
                          onClick={() => update(f.key, (assumptions[f.key] || 0) + f.step)}
                          className="h-7 w-7 rounded-md bg-secondary text-muted-foreground hover:text-foreground text-xs font-bold transition-colors shrink-0"
                        >+</button>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Right: Outputs */}
            <div className="space-y-4 md:space-y-5">
              {outputsLoading ? (
                <LoadingState message="Loading outputs..." />
              ) : !outputs ? (
                <EmptyState title="No outputs yet" description="Click Recalculate to generate outputs from the backend." />
              ) : (
                <>
                  <motion.div {...fadeIn} transition={{ delay: 0.15 }} className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {[
                      { label: 'Projected IRR', value: `${outputs.irr.toFixed(1)}%` },
                      { label: 'Equity Multiple', value: `${outputs.equityMultiple.toFixed(2)}x` },
                      { label: 'Cash on Cash', value: `${outputs.cashOnCash.toFixed(1)}%` },
                      { label: 'NOI Growth', value: `${outputs.noiGrowth.toFixed(1)}%` },
                      { label: 'Required Equity', value: formatCurrency(outputs.requiredEquity) },
                      { label: 'Break-even Occ.', value: `${outputs.breakEvenOccupancy.toFixed(1)}%` },
                    ].map((m, i) => (
                      <div key={i} className="rounded-xl border bg-card p-3 md:p-4 card-shadow text-center">
                        <p className="text-xs text-muted-foreground">{m.label}</p>
                        <p className="text-base md:text-lg font-semibold font-display mt-1 text-foreground">{m.value}</p>
                      </div>
                    ))}
                  </motion.div>

                  {/* Scenarios */}
                  {scenarios.length > 0 && (
                    <motion.div {...fadeIn} transition={{ delay: 0.2 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                      <h3 className="text-sm font-semibold text-foreground mb-4">Scenario Analysis</h3>
                      <div className="grid grid-cols-3 gap-2 md:gap-3">
                        {scenarios.map((s, i) => (
                          <div key={i} className={`rounded-lg p-3 md:p-4 text-center ${s.name === 'Base' ? 'bg-primary/5 border border-primary/20' : 'bg-secondary/50'}`}>
                            <p className="text-xs font-medium text-muted-foreground mb-1.5 md:mb-2">{s.name}</p>
                            <p className="text-base md:text-lg font-semibold font-display text-foreground">{s.irr.toFixed(1)}%</p>
                            <p className="text-xs text-muted-foreground">IRR</p>
                            <p className="text-sm font-semibold mt-1.5 md:mt-2 text-foreground">{s.equityMultiple.toFixed(2)}x</p>
                            <p className="text-xs text-muted-foreground">EM</p>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* Chart */}
                  {projectionData.length > 0 && (
                    <motion.div {...fadeIn} transition={{ delay: 0.25 }} className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
                      <h3 className="text-sm font-semibold text-foreground mb-4">Projected NOI & Value</h3>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={projectionData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 13% 91%)" />
                          <XAxis dataKey="year" tick={{ fontSize: 10, fill: 'hsl(215 13% 50%)' }} />
                          <YAxis tick={{ fontSize: 10, fill: 'hsl(215 13% 50%)' }} tickFormatter={v => `$${(v / 1000000).toFixed(1)}M`} />
                          <Tooltip formatter={(v: number) => formatCurrency(v)} />
                          <Line type="monotone" dataKey="NOI" stroke="hsl(37 90% 51%)" strokeWidth={2} dot={false} />
                          <Line type="monotone" dataKey="Value" stroke="hsl(215 28% 17%)" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </motion.div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
