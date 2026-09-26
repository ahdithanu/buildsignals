import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { AuthPageShell } from '@/components/auth/AuthPageShell';
import { useAuth } from '@/contexts/AuthContext';

export default function Register() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 12) {
      setError('Password must be at least 12 characters.');
      return;
    }
    setSubmitting(true);
    try {
      await register({
        email,
        password,
        full_name: fullName,
        organization_name: orgName.trim() || undefined,
      });
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthPageShell
      eyebrow="Enterprise access"
      title="Create your BuildSignals account"
      description="Create an organization-scoped workspace for your team."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-foreground hover:underline">Sign in</Link></>}
    >
          <form onSubmit={handleSubmit} className="space-y-5">
            <label className="block">
              <span className="section-label">Full name</span>
              <input
                id="fullName"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Smith"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>
            <label className="block">
              <span className="section-label">Work email</span>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@firm.com"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>
            <label className="block">
              <span className="section-label">Password</span>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 12 characters"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>
            <label className="block">
              <span className="section-label">Organization name (optional)</span>
              <input
                id="orgName"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Acme Capital"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
              <p className="text-xs text-muted-foreground">
                A named workspace makes you its administrator.
              </p>
            </label>
            {error && (
              <div className="border-l-2 border-destructive pl-3 text-xs text-destructive" role="alert">
                {error}
              </div>
            )}
            <button type="submit" className="flex h-11 w-full items-center justify-between bg-foreground px-4 text-xs font-semibold text-background disabled:opacity-50" disabled={submitting}>
              {submitting ? 'Creating account...' : 'Create account'}
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
    </AuthPageShell>
  );
}
