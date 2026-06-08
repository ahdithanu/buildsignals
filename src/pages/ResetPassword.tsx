import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
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
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl">Reset password</CardTitle>
          </CardHeader>
          <CardContent>
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
          </CardContent>
        </Card>
      </div>
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
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl">Reset link unusable</CardTitle>
          </CardHeader>
          <CardContent>
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
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Choose a new password</CardTitle>
          <CardDescription>
            Pick something strong you haven't used elsewhere.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm password</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div className="text-sm text-destructive" role="alert">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? 'Resetting…' : 'Reset password'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
