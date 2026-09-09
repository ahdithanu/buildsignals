import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { BuildSignalsLogo } from '@/components/BuildSignalsLogo';
import { useAuth } from '@/contexts/AuthContext';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/';

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-background">
      <section className="mx-auto flex w-full max-w-lg flex-col px-5 py-10 sm:px-8 sm:py-16">
        <div>
          <BuildSignalsLogo />
          <p className="mt-2 text-[9px] uppercase text-muted-foreground">Infrastructure opportunities. Early.</p>
        </div>

        <div className="mt-10 w-full">
          <p className="section-label">Enterprise access</p>
          <h1 className="mt-3 text-2xl font-semibold">Sign in</h1>
          <p className="mt-1 text-xs text-muted-foreground">Permit, development and ownership intelligence.</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <label className="block">
              <span className="section-label">Work email</span>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>

            <label className="block">
              <span className="flex items-center justify-between">
                <span className="section-label">Password</span>
                <Link to="/forgot-password" className="text-[10px] font-medium text-destructive hover:underline">Forgot password</Link>
              </span>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>

            {error && <p className="border-l-2 border-destructive pl-3 text-xs text-destructive" role="alert">{error}</p>}

            <button type="submit" disabled={submitting} className="flex h-11 w-full items-center justify-between bg-foreground px-4 text-xs font-semibold text-background disabled:opacity-50">
              {submitting ? 'Signing in...' : 'Sign in'}
              <ArrowRight className="h-4 w-4" />
            </button>

          </form>
        </div>

        <p className="mt-6 text-sm text-muted-foreground">
          No account? <Link to="/register" className="font-semibold text-foreground hover:underline">Create account</Link>
        </p>
      </section>

    </main>
  );
}
