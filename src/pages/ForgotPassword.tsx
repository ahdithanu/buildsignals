import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Forgot your password?</CardTitle>
          <CardDescription>
            Enter your email and we'll send you a reset link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {message ? (
            <div className="space-y-4">
              <div
                className="text-sm text-foreground rounded-md border border-border bg-muted p-3"
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
              <p className="text-sm text-muted-foreground text-center">
                <Link
                  to="/login"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  Back to sign in
                </Link>
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@firm.com"
                />
              </div>
              <Button
                type="submit"
                className="w-full"
                disabled={submitting}
              >
                {submitting ? 'Sending…' : 'Send reset link'}
              </Button>
              <p className="text-sm text-muted-foreground text-center">
                <Link
                  to="/login"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  Back to sign in
                </Link>
              </p>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
