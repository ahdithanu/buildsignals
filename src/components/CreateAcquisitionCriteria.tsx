import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Save, X } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

export function CreateAcquisitionCriteria({ onCreated }: { onCreated: (id: string) => void }) {
  const { organizationId, user, role } = useAuth();
  const cache = useQueryClient();
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState('small_multifamily');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [values, setValues] = useState({ min_price: '1000000', max_price: '3000000', min_size: '16', max_size: '32', min_year_built: '1980' });
  const save = useMutation({
    mutationFn: () => apiClient.post<{ id: string }>('/buy-box', { acquisition_criteria: {
      version: 1, profile, market_city: city.trim(), market_state: state,
      ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Number(value)])),
    } }),
    onSuccess: result => {
      void cache.invalidateQueries({ queryKey: ['saved-acquisition-criteria', organizationId, user?.id] });
      onCreated(result.id); setOpen(false);
    },
  });
  if (role !== 'admin' && role !== 'editor') return null;
  const valid = city.trim() && /^[A-Z]{2}$/.test(state)
    && Object.values(values).every(value => value.trim() && Number.isFinite(Number(value)) && Number(value) > 0)
    && Number(values.min_price) <= Number(values.max_price)
    && Number(values.min_size) <= Number(values.max_size)
    && ['min_size', 'max_size', 'min_year_built'].every(key => Number.isInteger(Number(values[key as keyof typeof values])))
    && Number(values.min_year_built) >= 1000 && Number(values.min_year_built) <= 9999;
  if (!open) return <button type="button" className="mt-2 inline-flex items-center gap-2 border p-2 text-sm"
    onClick={() => { save.reset(); setOpen(true); }}><Plus size={16} />New buy box</button>;
  return <form className="mt-3 space-y-3 border-y py-3" aria-label="New acquisition buy box"
    onSubmit={event => { event.preventDefault(); if (valid && !save.isPending) save.mutate(); }}>
    <fieldset disabled={save.isPending} className="space-y-3">
      <label className="block text-sm">Asset profile<select className="mt-1 block w-full border bg-background p-2" value={profile}
        onChange={event => {
          const next = event.target.value; setProfile(next);
          setValues(next === 'small_multifamily'
            ? { min_price: '1000000', max_price: '3000000', min_size: '16', max_size: '32', min_year_built: '1980' }
            : { min_price: '1500000', max_price: '4000000', min_size: '8000', max_size: '25000', min_year_built: '1985' });
        }}><option value="small_multifamily">Small multifamily</option><option value="small_bay_retail">Small-bay retail</option></select></label>
      <div className="grid grid-cols-[minmax(0,1fr)_5rem] gap-2">
        <label className="text-sm">Market city<input required maxLength={100} className="mt-1 w-full border bg-background p-2" value={city} onChange={e => setCity(e.target.value)} /></label>
        <label className="text-sm">Market state<input required maxLength={2} className="mt-1 w-full border bg-background p-2" value={state} onChange={e => setState(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))} /></label>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(values).map(([key, value]) => <label className="min-w-0 text-sm" key={key}>
          {{ min_price: 'Minimum price ($)', max_price: 'Maximum price ($)', min_size: `Minimum ${profile === 'small_multifamily' ? 'units' : 'SF'}`, max_size: `Maximum ${profile === 'small_multifamily' ? 'units' : 'SF'}`, min_year_built: 'Earliest construction year' }[key]}
          <input required type="number" min={key === 'min_year_built' ? 1000 : 1} max={key === 'min_year_built' ? 9999 : undefined}
            step={key.includes('price') ? 'any' : 1} className="mt-1 w-full min-w-0 border bg-background p-2" value={value}
            onChange={e => setValues(previous => ({ ...previous, [key]: e.target.value }))} />
        </label>)}
      </div>
      <div className="flex gap-2">
        <button disabled={!valid || save.isPending} className="inline-flex items-center gap-2 border p-2 text-sm"><Save size={16} />Save buy box</button>
        <button type="button" className="border p-2" aria-label="Cancel buy box" title="Cancel buy box" onClick={() => setOpen(false)}><X size={16} /></button>
      </div>
    </fieldset>
    {save.isError && <p role="alert" className="text-sm">Buy box could not be saved. Check the criteria and try again.</p>}
  </form>;
}
