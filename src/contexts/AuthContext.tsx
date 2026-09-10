import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { authApi } from '@/api/auth';
import {
  setAccessToken,
  setUnauthorizedHandler,
} from '@/api/client';
import type { LoginRequest, MemberRole, RegisterRequest, TokenResponse, User } from '@/types/auth';

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
  const authOperation = useRef(0);

  const reset = useCallback(() => {
    authOperation.current += 1;
    setAccessToken(null);
    setUser(null);
    setOrganizationId(null);
    setRole(null);
    setIsLoading(false);
  }, []);

  const hydrate = useCallback(async () => {
    const operation = ++authOperation.current;
    try {
      const me = await authApi.me();
      if (operation !== authOperation.current) return;
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
    } catch {
      // /auth/me failed even after the client tried a silent refresh.
      // We're really logged out.
      if (operation === authOperation.current) reset();
    } finally {
      if (operation === authOperation.current) setIsLoading(false);
    }
  }, [reset]);

  // On mount, try to re-establish a session using the refresh cookie.
  // The apiClient itself does silent refresh on 401, so we can just call
  // /auth/me directly and let the client handle the first 401 under the hood.
  useEffect(() => {
    hydrate();
    return () => { authOperation.current += 1; };
  }, [hydrate]);

  // Wire client-level terminal 401 → reset auth state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      reset();
    });
    return () => setUnauthorizedHandler(null);
  }, [reset]);

  const refresh = hydrate;

  const authenticate = useCallback(
    async (request: () => Promise<TokenResponse>) => {
      // Invalidate old requests before starting an explicit identity change.
      reset();
      const operation = authOperation.current;
      const assertCurrent = () => {
        if (operation !== authOperation.current) {
          throw new Error('Authentication attempt was superseded. Please try again.');
        }
      };
      try {
        const res = await request();
        assertCurrent();
        setAccessToken(res.access_token);
        const me = await authApi.me();
        assertCurrent();
        setUser(me.user);
        setOrganizationId(me.organization_id);
        setRole(me.role);
        return me.user;
      } catch (error) {
        if (operation === authOperation.current) reset();
        throw error;
      }
    },
    [reset],
  );

  const login = useCallback(
    (data: LoginRequest) => authenticate(() => authApi.login(data)),
    [authenticate],
  );

  const register = useCallback(
    (data: RegisterRequest) => authenticate(() => authApi.register(data)),
    [authenticate],
  );

  const logout = useCallback(async () => {
    try {
      // Dispatch with the current credential, then immediately retire it locally.
      let pending: Promise<void>;
      try {
        pending = authApi.logout();
      } finally {
        reset();
      }
      await pending;
    } catch {
      // Network error on logout is fine — we still clear local state.
    }
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
