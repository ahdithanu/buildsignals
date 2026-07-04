import { Component, ReactNode, ErrorInfo } from "react";
import InternalError from "@/pages/InternalError";
import { captureError } from "@/sentry";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Top-level error boundary. React error boundaries must be class components —
 * the hooks API has no equivalent for `componentDidCatch` /
 * `getDerivedStateFromError`. Render errors anywhere below this boundary
 * surface a friendly <InternalError> page instead of a white screen.
 *
 * NOTE: This does NOT catch errors in event handlers, async code, or during
 * SSR — that's a React limitation. Wire Sentry for those.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Report to Sentry with the React component stack for context. Sentry's
    // global handlers already catch uncaught exceptions and unhandled
    // promise rejections; the componentStack is only available here, so we
    // capture explicitly rather than letting the error bubble.
    captureError(error, { componentStack: info.componentStack });

    // Also log to the browser console — devs debugging locally shouldn't
    // need a Sentry account to see the stack.
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] Caught render error:", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return <InternalError onReset={this.handleReset} error={this.state.error} />;
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
