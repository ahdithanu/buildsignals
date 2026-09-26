import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { AuthPageShell } from '@/components/auth/AuthPageShell';
import { useToast } from '@/hooks/use-toast';
import { passwordResetApi } from '@/api/password_reset';
import { ApiError } from '@/api/client';

const INVALID_LINK_MESSAGE =
  'This reset link is invalid or expired. Request a new one.';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();
  const { toast } = useToast();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [invalidLink, setInvalidLink] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!token) {
    return (
      <AuthPageShell eyebrow="Account recovery" title="Reset password">
            <div className="text-sm text-destructive" role="alert">
              No reset token was provided. Please use the link from your email
              or{' '}
              <Link
                to="/forgot-password"
                className="text-primary underline-offset-4 hover:underline"
              >
                request a new one
              </Link>
              .
            </div>
      </AuthPageShell>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await passwordResetApi.reset(token!, password);
      toast({ title: 'Password reset successfully' });
      navigate('/login');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 400) {
          setInvalidLink(true);
        } else if (err.status === 422) {
          setError(err.message || 'Password does not meet requirements.');
        } else if (err.status === 429) {
          setError('Too many requests, try again in a bit.');
        } else {
          setError(err.message || 'Something went wrong.');
        }
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (invalidLink) {
    return (
      <AuthPageShell eyebrow="Account recovery" title="Reset link unusable">
            <div className="text-sm text-destructive mb-4" role="alert">
              {INVALID_LINK_MESSAGE}
            </div>
            <p className="text-sm">
              <Link
                to="/forgot-password"
                className="text-primary underline-offset-4 hover:underline"
              >
                Request a new reset link
              </Link>
            </p>
      </AuthPageShell>
    );
  }

  return (
    <AuthPageShell
      eyebrow="Account recovery"
      title="Choose a new password"
      description="Use a strong password you have not used elsewhere."
    >
          <form onSubmit={handleSubmit} className="space-y-5">
            <label className="block">
              <span className="section-label">New password</span>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={12}
                placeholder="At least 12 characters"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>
            <label className="block">
              <span className="section-label">Confirm password</span>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Repeat password"
                className="mt-1.5 h-11 w-full border-2 border-foreground bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-[#1a63c7]"
              />
            </label>
            {error && (
              <div className="text-sm text-destructive" role="alert">
                {error}
              </div>
            )}
            <button type="submit" className="flex h-11 w-full items-center justify-between bg-foreground px-4 text-xs font-semibold text-background disabled:opacity-50" disabled={submitting}>
              {submitting ? 'Resetting...' : 'Reset password'}
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
    </AuthPageShell>
  );
}
