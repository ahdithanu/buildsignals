import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface SavedBox {
  id: string;
  acquisition_criteria: null | {
    profile: string; market_city: string; market_state: string;
    min_price: number; max_price: number; min_size: number; max_size: number;
  };
}

export function SavedAcquisitionCriteria({ value, onChange }: {
  value: string; onChange: (id: string) => void;
}) {
  const { organizationId, user } = useAuth();
  const query = useQuery({
    queryKey: ['saved-acquisition-criteria', organizationId, user?.id],
    enabled: !!organizationId && !!user,
    queryFn: async () => {
      const boxes = await apiClient.get<SavedBox[]>('/buy-box', { limit: 200 });
      if (!Array.isArray(boxes)) throw new Error('Invalid saved criteria response');
      return boxes;
    },
  });
  const boxes = query.data?.filter(box => box.acquisition_criteria) ?? [];
  return <div className="mb-3">
    <label className="block text-sm">Saved buy box
      <select className="mt-1 block w-full border bg-background p-2" value={value}
        onChange={event => onChange(event.target.value)}>
        <option value="">Default criteria</option>
        {value && !boxes.some(box => box.id === value) && <option value={value}>Selected buy box</option>}
        {boxes.map(box => {
          const c = box.acquisition_criteria!;
          return <option key={box.id} value={box.id}>
            {c.market_city}, {c.market_state} · {c.profile === 'small_multifamily' ? 'Multifamily' : 'Retail'} · {c.min_size}–{c.max_size} {c.profile === 'small_multifamily' ? 'units' : 'SF'} · ${c.min_price.toLocaleString()}–${c.max_price.toLocaleString()} · {box.id.slice(0, 8)}
          </option>;
        })}
      </select>
    </label>
    {query.isPending && <p role="status" className="text-xs">Loading saved buy boxes...</p>}
    {query.isError && <p role="alert" className="text-xs">Saved buy boxes unavailable. <button onClick={() => query.refetch()} className="underline">Retry buy boxes</button></p>}
    {query.data?.length === 200 && <p className="text-xs">Showing the first 200 buy boxes.</p>}
  </div>;
}
