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
  setSessionRefreshHandler,
  setUnauthorizedHandler,
} from '@/api/client';
import type { LoginRequest, MemberRole, RegisterRequest, TokenResponse, User } from '@/types/auth';

interface AuthState {
  user: User | null;
  organizationId: string | null;
  role: MemberRole | null;
  isAuthenticated: boolean;
  isDemo: boolean;
  isInternalOperator: boolean;
  isLoading: boolean;
  /** Login + persist token. Returns the resolved user. */
  login: (data: LoginRequest) => Promise<User>;
  /** Demo login + persist token. Returns the resolved demo user. */
  demoLogin: () => Promise<User>;
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
  const [isDemo, setIsDemo] = useState(false);
  const [isInternalOperator, setIsInternalOperator] = useState(false);
  // Start loading — we need to attempt a silent refresh before we know
  // whether the user is authenticated.
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const authOperation = useRef(0);
  const authenticatedIdentity = useRef<Pick<TokenResponse, 'user_id' | 'organization_id' | 'role'> | null>(null);
  // Older /auth/me responses cannot restore a grant revoked by token rotation.
  const authorizationRevision = useRef(0);
  const refreshedOperator = useRef(false);

  const reset = useCallback(() => {
    authOperation.current += 1;
    authorizationRevision.current += 1;
    refreshedOperator.current = false;
    authenticatedIdentity.current = null;
    setAccessToken(null);
    setUser(null);
    setOrganizationId(null);
    setRole(null);
    setIsDemo(false);
    setIsInternalOperator(false);
    setIsLoading(false);
  }, []);

  const hydrate = useCallback(async () => {
    const operation = ++authOperation.current;
    const revision = authorizationRevision.current;
    try {
      const me = await authApi.me();
      if (operation !== authOperation.current) return;
      authenticatedIdentity.current = { user_id: me.user.id, organization_id: me.organization_id, role: me.role };
      setUser(me.user);
      setOrganizationId(me.organization_id);
      setRole(me.role);
      setIsDemo(me.is_demo === true);
      setIsInternalOperator(me.is_internal_operator === true && me.is_demo !== true
        && (revision === authorizationRevision.current || refreshedOperator.current));
    } catch {
      // /auth/me failed even after the client tried a silent refresh.
      // We're really logged out.
      if (operation === authOperation.current) reset();
    } finally {
      if (operation === authOperation.current) setIsLoading(false);
    }
  }, [reset]);

  useEffect(() => {
    setSessionRefreshHandler(response => {
      const identity = authenticatedIdentity.current;
      // Refresh cookies are shared across tabs; never rotate into another scope.
      if (identity && (response.user_id !== identity.user_id
        || response.organization_id !== identity.organization_id || response.role !== identity.role)) {
        reset();
        return false;
      }
      authorizationRevision.current += 1;
      refreshedOperator.current = response.is_internal_operator === true && response.is_demo !== true;
      setIsInternalOperator(refreshedOperator.current);
      return true;
    });
    return () => setSessionRefreshHandler(null);
  }, [reset]);

  // The client can silently refresh the initial /auth/me request on 401.
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
        const revision = authorizationRevision.current;
        const me = await authApi.me();
        assertCurrent();
        authenticatedIdentity.current = { user_id: me.user.id, organization_id: me.organization_id, role: me.role };
        setUser(me.user);
        setOrganizationId(me.organization_id);
        setRole(me.role);
        setIsDemo(me.is_demo === true);
        setIsInternalOperator(me.is_internal_operator === true && me.is_demo !== true
          && (revision === authorizationRevision.current || refreshedOperator.current));
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

  const demoLogin = useCallback(() => authenticate(() => authApi.demo()), [authenticate]);

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
      isDemo,
      isInternalOperator,
      isLoading,
      login,
      demoLogin,
      register,
      logout,
      refresh,
    }),
    [user, organizationId, role, isDemo, isInternalOperator, demoLogin, isLoading, login, register, logout, refresh],
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
