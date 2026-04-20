import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { authApi } from '@/api/auth';
import {
  getStoredToken,
  setStoredToken,
  setUnauthorizedHandler,
} from '@/api/client';
import type { LoginRequest, MemberRole, RegisterRequest, User } from '@/types/auth';

interface AuthState {
  user: User | null;
  organizationId: string | null;
  role: MemberRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** Login + persist token. Returns the resolved user. */
  login: (data: LoginRequest) => Promise<User>;
  /** Register + persist token. */
  register: (data: RegisterRequest) => Promise<User>;
  /** Clear token and reset state. */
  logout: () => void;
  /** Refetch /auth/me using the current token. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [role, setRole] = useState<MemberRole | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(!!getStoredToken());

  const reset = useCallback(() => {
    setUser(null);
    setOrganizationId(null);
    setRole(null);
  }, []);

  const refresh = useCallback(async () => {
    if (!getStoredToken()) {
      reset();
      setIsLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
    } catch {
      // 401 handler in client.ts already cleared the token.
      reset();
    } finally {
      setIsLoading(false);
    }
  }, [reset]);

  // Hydrate on mount if a token is already stored.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Wire client-level 401 → reset auth state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      reset();
    });
    return () => setUnauthorizedHandler(null);
  }, [reset]);

  const login = useCallback(
    async (data: LoginRequest) => {
      const res = await authApi.login(data);
      setStoredToken(res.access_token);
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
      return me.user;
    },
    []
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      const res = await authApi.register(data);
      setStoredToken(res.access_token);
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
      return me.user;
    },
    []
  );

  const logout = useCallback(() => {
    setStoredToken(null);
    reset();
  }, [reset]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      organizationId,
      role,
      isAuthenticated: user !== null,
      isLoading,
      login,
      register,
      logout,
      refresh,
    }),
    [user, organizationId, role, isLoading, login, register, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
