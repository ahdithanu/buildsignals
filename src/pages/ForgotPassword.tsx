import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { AuthPageShell } from '@/components/auth/AuthPageShell';
import { passwordResetApi } from '@/api/password_reset';
import { ApiError } from '@/api/client';

const GENERIC_SUCCESS =
  "If an account with that email exists, we've sent a reset link. Check your inbox.";
const RATE_LIMIT_MESSAGE = 'Too many requests, try again in a bit.';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [showFootnote, setShowFootnote] = useState(false);

  useEffect(() => {
    if (!message || isRateLimited) return;
    const t = setTimeout(() => setShowFootnote(true), 8000);
    return () => clearTimeout(t);
  }, [message, isRateLimited]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setShowFootnote(false);
    try {
      await passwordResetApi.forgot(email);
      setIsRateLimited(false);
      setMessage(GENERIC_SUCCESS);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setIsRateLimited(true);
        setMessage(RATE_LIMIT_MESSAGE);
      } else {
        // Don't reveal whether the email was valid — same success message.
        setIsRateLimited(false);
        setMessage(GENERIC_SUCCESS);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function tryDifferentEmail() {
    setEmail('');
    setMessage(null);
    setIsRateLimited(false);
    setShowFootnote(false);
  }

  return (
    <AuthPageShell
      eyebrow="Account recovery"
      title="Reset your password"
      description="Enter your work email and we'll send a reset link if the account exists."
      footer={<Link to="/login" className="font-semibold text-foreground hover:underline">Back to sign in</Link>}
    >
          {message ? (
            <div className="space-y-4">
              <div
                className="border-l-2 border-foreground bg-secondary p-3 text-sm text-foreground"
                role="status"
              >
                {message}
              </div>
              {showFootnote && (
                <p className="text-xs text-muted-foreground">
                  Didn't get it? Check spam or{' '}
                  <button
                    type="button"
                    onClick={tryDifferentEmail}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Try a different email
                  </button>
                </p>
              )}
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
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
              <button
                type="submit"
                className="flex h-11 w-full items-center justify-between bg-foreground px-4 text-xs font-semibold text-background disabled:opacity-50"
                disabled={submitting}
              >
                {submitting ? 'Sending...' : 'Send reset link'}
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}
    </AuthPageShell>
  );
}
