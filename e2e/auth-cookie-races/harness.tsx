import React, { useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider, useAuth } from '../../src/contexts/AuthContext';
import { apiClient, getAccessToken, setAccessToken } from '../../src/api/client';
import { authApi } from '../../src/api/auth';

// Mounted only by reproduce.mjs, never imported by the product entry point.
const password = 'Local-Auth-Race-Diagnostic-42!';
const tasks: Record<string, Promise<unknown>> = {};
let rememberedCredential: string | null = null;
const rememberTask = (name: string, pending: Promise<unknown>) => {
  tasks[name] = pending.then(() => ({ ok: true }), error => ({ error: error.message, status: error.status }));
};

function Harness() {
  const auth = useAuth();
  useEffect(() => {
    Object.assign(window, {
      authRace: {
        ready: !auth.isLoading,
        email: auth.user?.email ?? null,
        organizationId: auth.organizationId,
        register: async (email: string) => {
          await auth.register({ email, password, full_name: 'Synthetic auth QA' });
        },
        login: async (email: string) => { await auth.login({ email, password }); },
        start: (task: 'refresh' | 'logout') => {
          // The local probe returns the same 401 as expired access, preserving
          // the real signed identity used to bind automatic retry and logout.
          const pending = task === 'refresh' ? apiClient.get('/probe-expired-access') : auth.logout();
          tasks[task] = pending.then(
            () => ({ settled: true }),
            (error: unknown) => ({ settled: true, error: (error as Error).name }),
          );
        },
        settle: (task: string) => tasks[task],
        rememberLogout: () => { rememberedCredential = getAccessToken(); },
        prepareWorkspace: () => apiClient.post<{ organization_id: string }>('/probe-workspace'),
        switchOrganization: (organizationId: string) => auth.switchOrganization(organizationId),
        startRememberedSwitch: (organizationId: string) => rememberTask('rememberedSwitch', authApi.switchOrg(organizationId, rememberedCredential)),
        startRememberedLogout: () => rememberTask('rememberedLogout', authApi.logout(rememberedCredential)),
        startMutation: () => rememberTask('mutation', apiClient.post('/probe-expired-write', { intent: 'original workspace only' })),
        unknownMutation: async (credential: string | null) => {
          setAccessToken(credential);
          try { await apiClient.post('/probe-write', { intent: 'must never replay' }); return { ok: true }; }
          catch (error) { return { status: (error as { status: number }).status }; }
        },
        probeAfterExpiry: async () => {
          return apiClient.get<{ email: string; organization_id: string }>('/probe-identity');
        },
      },
    });
  }, [auth]);
  return <output>{auth.isLoading ? 'Loading' : auth.user?.email ?? 'Signed out'}</output>;
}

createRoot(document.getElementById('root')!).render(<AuthProvider><Harness /></AuthProvider>);
