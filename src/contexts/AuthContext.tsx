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
  setAccessToken,
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
  /** Clear token + server-side refresh cookie. */
  logout: () => Promise<void>;
  /** Refetch /auth/me using the current token. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [role, setRole] = useState<MemberRole | null>(null);
  // Start loading — we need to attempt a silent refresh before we know
  // whether the user is authenticated.
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const reset = useCallback(() => {
    setUser(null);
    setOrganizationId(null);
    setRole(null);
  }, []);

  const hydrate = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
    } catch {
      // /auth/me failed even after the client tried a silent refresh.
      // We're really logged out.
      reset();
    } finally {
      setIsLoading(false);
    }
  }, [reset]);

  // On mount, try to re-establish a session using the refresh cookie.
  // The apiClient itself does silent refresh on 401, so we can just call
  // /auth/me directly and let the client handle the first 401 under the hood.
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Wire client-level terminal 401 → reset auth state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      reset();
    });
    return () => setUnauthorizedHandler(null);
  }, [reset]);

  const refresh = hydrate;

  const login = useCallback(
    async (data: LoginRequest) => {
      const res = await authApi.login(data);
      setAccessToken(res.access_token);
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
      return me.user;
    },
    [],
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      const res = await authApi.register(data);
      setAccessToken(res.access_token);
      const me = await authApi.me();
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
      return me.user;
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Network error on logout is fine — we still clear local state.
    }
    setAccessToken(null);
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
    [user, organizationId, role, isLoading, login, register, logout, refresh],
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
