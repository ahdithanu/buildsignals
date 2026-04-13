import { useState } from "react";
import { Layout } from "@/components/Layout";
import { LoadingState, ErrorState } from "@/components/DataStates";
import { motion } from "framer-motion";
import { MapPin, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { signalsApi } from "@/api/signals";
import { queryKeys } from "@/lib/queryKeys";
import type { Signal } from "@/types/activity";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };

const signalTypeLabel: Record<string, string> = {
  zoning: 'Zoning Change', permit: 'Permit Activity', listing: 'Broker Listing',
  ownership: 'Ownership Transfer', competitor: 'Competitor Activity', demographic: 'Demographic Shift',
};

const signalTypeEmoji: Record<string, string> = {
  zoning: '🏗️', permit: '📋', listing: '🏠', ownership: '🔄', competitor: '⚡', demographic: '📊',
};

const impactIcon = {
  positive: <TrendingUp className="h-3.5 w-3.5 text-success" />,
  negative: <TrendingDown className="h-3.5 w-3.5 text-destructive" />,
  neutral: <Minus className="h-3.5 w-3.5 text-muted-foreground" />,
};

const confidenceStyle = {
  high: 'bg-success/10 text-success',
  medium: 'bg-warning/10 text-warning',
  low: 'bg-muted text-muted-foreground',
};

const watchlists = ['Phoenix, AZ', 'Dallas, TX', 'Tampa, FL', 'Austin, TX', 'Atlanta, GA', 'Denver, CO', 'Nashville, TN'];

export default function MarketSignals() {
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);

  const { data: signals, isLoading, error, refetch } = useQuery<Signal[]>({
    queryKey: queryKeys.signals.all,
    queryFn: () => signalsApi.list(),
    retry: 1,
  });

  const allSignals = signals ?? [];

  const filtered = allSignals.filter(s => {
    if (selectedMarket && !s.property.toLowerCase().includes(selectedMarket.split(',')[0].toLowerCase())) return false;
    return true;
  });

  if (isLoading) {
    return <Layout><LoadingState message="Loading signals..." /></Layout>;
  }

  if (error) {
    return <Layout><ErrorState message="Failed to load signals." onRetry={() => refetch()} /></Layout>;
  }

  return (
    <Layout>
      <div className="p-6 max-w-[1400px] mx-auto">
        <motion.div {...fadeIn} className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold font-display text-foreground">Market Signals</h2>
            <p className="text-sm text-muted-foreground mt-0.5">External signals that impact your deal pipeline</p>
          </div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar: Watchlists */}
          <motion.div {...fadeIn} transition={{ delay: 0.1 }}>
            <div className="rounded-xl border bg-card p-5 card-shadow">
              <h3 className="text-sm font-semibold text-foreground mb-3">Watchlists</h3>
              <div className="space-y-1">
                <button
                  onClick={() => setSelectedMarket(null)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    !selectedMarket ? 'bg-primary text-primary-foreground font-medium' : 'text-muted-foreground hover:bg-secondary'
                  }`}
                >
                  All Markets
                </button>
                {watchlists.map(m => {
                  const count = allSignals.filter(s => s.property.toLowerCase().includes(m.split(',')[0].toLowerCase())).length;
                  return (
                    <button
                      key={m}
                      onClick={() => setSelectedMarket(m)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedMarket === m ? 'bg-primary text-primary-foreground font-medium' : 'text-muted-foreground hover:bg-secondary'
                      }`}
                    >
                      <span className="flex items-center gap-2"><MapPin className="h-3 w-3" />{m}</span>
                      {count > 0 && <span className="text-xs">{count}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </motion.div>

          {/* Signal Feed */}
          <motion.div {...fadeIn} transition={{ delay: 0.15 }} className="lg:col-span-3 space-y-4">
            {filtered.length === 0 && (
              <div className="rounded-xl border bg-card p-12 text-center text-muted-foreground card-shadow">
                No signals found for this market.
              </div>
            )}
            {filtered.map(signal => (
              <div key={signal.id} className="rounded-xl border bg-card p-5 card-shadow hover:card-shadow-hover transition-shadow">
                <div className="flex items-start gap-4">
                  <div className="text-2xl">{signalTypeEmoji[signal.type]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{signalTypeLabel[signal.type]}</span>
                          {impactIcon[signal.impact]}
                        </div>
                        <h4 className="text-sm font-semibold text-foreground">{signal.property}</h4>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-xs font-medium rounded-md px-2 py-0.5 ${confidenceStyle[signal.confidence]}`}>
                          {signal.confidence} confidence
                        </span>
                        <span className="text-xs text-muted-foreground">{signal.date}</span>
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{signal.summary}</p>
                    <div className="flex items-center gap-2 mt-3">
                      <span className={`text-xs font-medium capitalize ${signal.impact === 'positive' ? 'text-success' : signal.impact === 'negative' ? 'text-destructive' : 'text-muted-foreground'}`}>
                        {signal.impact} impact
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </motion.div>
        </div>
      </div>
    </Layout>
  );
}
