import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface InternalErrorProps {
  onReset?: () => void;
  /** Only shown in dev to make debugging easier. Never rendered in prod. */
  error?: Error | null;
}

/**
 * Friendly 500 page rendered when the top-level <ErrorBoundary> catches a
 * render error. Intentionally minimal — no Sidebar / Layout — so it cannot
 * itself crash if Layout (or anything it imports) is the source of the bug.
 */
export default function InternalError({ onReset, error }: InternalErrorProps) {
  const isDev = import.meta.env.DEV;
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md card-shadow">
        <CardHeader className="space-y-3 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" aria-hidden="true" />
          </div>
          <CardTitle className="text-lg font-semibold">Something went wrong</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred. Engineering has been notified.
          </p>
          {isDev && error?.message && (
            <pre className="text-left text-xs bg-secondary rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap break-all">
              {error.message}
            </pre>
          )}
          <div className="flex flex-col sm:flex-row gap-2 justify-center pt-2">
            {onReset && (
              <Button onClick={onReset} variant="default">
                Try again
              </Button>
            )}
            <Button asChild variant="outline">
              <Link to="/">Back to dashboard</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
