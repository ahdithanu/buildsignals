import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, CheckSquare } from 'lucide-react';
import { BuildSignalsLogo } from '@/components/BuildSignalsLogo';
import { useAuth } from '@/contexts/AuthContext';

const proofSignals = [
  ['Grocery-format shell, tenant TBD', 'Gilbert, AZ', 'filed 8/11 · 15 days before hearing'],
  ['Cold-storage build, 41 ac', 'Wilmer, TX', 'in review · applicant unresolved'],
  ['Rezoning, 88 ac PAD', 'Queen Creek, AZ', 'hearing set 8/26'],
];

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [keepSignedIn, setKeepSignedIn] = useState(false);
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
    <main className="grid min-h-screen bg-background lg:grid-cols-[minmax(380px,520px)_1fr]">
      <section className="flex min-h-screen flex-col border-foreground px-5 py-6 sm:px-8 lg:border-r-2 lg:px-10 lg:py-8">
        <div>
          <BuildSignalsLogo />
          <p className="mt-2 text-[9px] uppercase text-muted-foreground">Infrastructure opportunities. Early.</p>
        </div>

        <div className="mt-10 w-full max-w-md sm:mt-12">
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

            <label className="flex cursor-pointer items-center gap-2 text-[11px]">
              <button
                type="button"
                role="checkbox"
                aria-checked={keepSignedIn}
                onClick={() => setKeepSignedIn((value) => !value)}
                className="flex h-4 w-4 items-center justify-center border-2 border-foreground"
              >
                {keepSignedIn && <CheckSquare className="h-3 w-3" />}
              </button>
              Keep me signed in on this device
            </label>

            {error && <p className="border-l-2 border-destructive pl-3 text-xs text-destructive" role="alert">{error}</p>}

            <button type="submit" disabled={submitting} className="flex h-11 w-full items-center justify-between bg-foreground px-4 text-xs font-semibold text-background disabled:opacity-50">
              {submitting ? 'Signing in...' : 'Sign in'}
              <ArrowRight className="h-4 w-4" />
            </button>

            <div className="flex items-center gap-3 text-[9px] text-muted-foreground"><span className="h-px flex-1 bg-border" />OR<span className="h-px flex-1 bg-border" /></div>
            <button type="button" className="h-11 w-full border-2 border-foreground bg-card px-4 text-left text-xs font-semibold">Continue with SSO (SAML)</button>

            <p className="text-center text-xs text-muted-foreground">
              No account?{' '}
              <Link to="/register" className="font-semibold text-foreground underline-offset-4 hover:underline">
                Create account
              </Link>
            </p>
          </form>
        </div>

        <p className="mt-auto pt-8 text-[10px] text-muted-foreground">
          Status · Security · Terms
        </p>
      </section>

      <section className="hidden min-w-0 flex-col lg:flex">
        <div className="border-b-2 border-foreground px-8 py-7">
          <p className="section-label">Coverage — live</p>
          <div className="mt-4 grid grid-cols-4">
            {[
              ['1,412', 'jurisdictions ingested'],
              ['97%', 'sources ≤24h fresh'],
              ['64', 'pre-approval signals today'],
              ['9', 'chain entries this week'],
            ].map(([value, label], index) => (
              <div key={label} className={index === 0 ? 'border-l-2 border-destructive pl-3' : 'px-3'}>
                <p className="text-2xl font-semibold">{value}</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-1 flex-col px-8 py-7">
          <p className="section-label">Signals detected before final approval</p>
          <div className="mt-3 border-t-2 border-foreground">
            {proofSignals.map(([name, market, evidence]) => (
              <div key={name} className="grid grid-cols-[1fr_auto] gap-6 border-b border-border py-3 text-xs">
                <p><span className="font-semibold">{name}</span> · {market}</p>
                <p className="text-muted-foreground">{evidence}</p>
              </div>
            ))}
            <div className="grid grid-cols-[1fr_auto] gap-6 border-b border-border py-3 text-xs text-muted-foreground">
              <p>Full records visible after sign-in</p><p>—</p>
            </div>
          </div>
          <p className="mt-auto border-t-2 border-foreground pt-4 text-[10px] text-muted-foreground">SOC 2 Type II · SSO/SAML · organization-scoped data · audit log on every read</p>
        </div>
      </section>
    </main>
  );
}
