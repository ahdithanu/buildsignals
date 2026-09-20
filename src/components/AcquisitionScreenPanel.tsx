import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface Screen {
  status: string;
  counts: { pass: number; fail: number; unknown: number };
  criteria: { key: string; label: string; target: string; status: string;
    value: string | number | null; basis: string | null; reason: string }[];
}

export function AcquisitionScreenPanel({ dealId }: { dealId: string }) {
  const { organizationId, user } = useAuth();
  const [profile, setProfile] = useState('small_multifamily');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [market, setMarket] = useState<{ market_city?: string; market_state?: string }>({});
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ['acquisition-screen', organizationId, user?.id, dealId, profile, market],
    enabled: !!organizationId && !!user,
    queryFn: () => apiClient.get<Screen>(`/deals/${dealId}/acquisition-screen`, { profile, ...market }),
  });
  return <section className="border-y py-5" aria-label="Acquisition buy-box screen">
    <h3 className="mb-3 text-sm font-semibold">Acquisition buy-box screen</h3>
    <label className="block text-sm">Profile
      <select className="my-2 block w-full border bg-background p-2" value={profile} onChange={e => setProfile(e.target.value)}>
        <option value="small_multifamily">Small multifamily</option><option value="small_bay_retail">Small-bay retail</option>
      </select>
    </label>
    <form className="flex flex-wrap items-end gap-2" onSubmit={e => {
      e.preventDefault(); setMarket(city.trim() && state.length === 2 ? { market_city: city.trim(), market_state: state } : {});
    }}>
      <label className="min-w-0 flex-1 text-sm">Target city<input className="mt-1 block w-full border bg-background p-2" value={city} maxLength={100} onChange={e => setCity(e.target.value)} /></label>
      <label className="text-sm">State<input className="mt-1 block w-16 border bg-background p-2" value={state} maxLength={2} onChange={e => setState(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))} /></label>
      <button className="border px-3 py-2 text-sm" disabled={!!(city.trim() || state) && !(city.trim() && state.length === 2)}>Apply</button>
    </form>
    <p className="my-3 text-xs text-muted-foreground">Preliminary comparison of saved deal facts. Source verification and underwriting remain outstanding.</p>
    {error ? <p role="alert">Screen unavailable. <button className="underline" onClick={() => refetch()}>Retry screen</button></p>
      : isPending ? <p role="status">Loading acquisition screen...</p>
      : <>
        <p className="mb-3 text-sm font-semibold">{data.status === 'outside_buy_box' ? 'Outside recorded criteria' : 'Diligence required'}: {data.counts.pass} pass, {data.counts.fail} fail, {data.counts.unknown} unknown</p>
        <ul className="divide-y">
          {data.criteria.map(c => <li key={c.key} className="py-3 text-sm">
            <div className="flex items-start justify-between gap-3"><span className="font-semibold">{c.label}</span><span className="shrink-0 uppercase">{c.status}</span></div>
            <p className="mt-1">{c.target}</p>
            <p className="mt-1 text-xs text-muted-foreground">{c.value == null ? 'Not established' : `Recorded: ${c.value}`} · {c.reason}</p>
          </li>)}
        </ul>
      </>}
  </section>;
}
