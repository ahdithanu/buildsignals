import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@/contexts/AuthContext';

function SessionCache({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient());

  useEffect(() => () => client.clear(), [client]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

export function SessionQueryProvider({ children }: { children: ReactNode }) {
  const { user, organizationId, role } = useAuth();
  // Remount consumers as well as the cache. Late responses and local component
  // state from a previous identity must not enter the next identity's UI.
  const scope = JSON.stringify([user?.id ?? null, organizationId, role]);
  return <SessionCache key={scope}>{children}</SessionCache>;
}
