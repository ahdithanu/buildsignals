import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useState } from "react";

import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Pins the contract for the top-level error boundary:
 *   - render errors below the boundary surface the InternalError UI
 *   - the "Try again" button resets the boundary and lets children re-render
 */

function Boom(): JSX.Element {
  throw new Error("kaboom");
}

describe("<ErrorBoundary>", () => {
  // React logs caught render errors to console.error. Silence it so test
  // output stays readable, but restore so unrelated noise still surfaces.
  let errSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    errSpy.mockRestore();
  });

  it("renders the InternalError UI when a child throws", () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(
      screen.getByText(/An unexpected error occurred\. Engineering has been notified\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toBeInTheDocument();
  });

  it("resets and re-renders children when 'Try again' is clicked and the issue is gone", () => {
    // A toggleable child: throws on first render, then succeeds after the
    // controlled flag flips. The flag is flipped by the test BEFORE the user
    // clicks "Try again", so the second render does not re-throw.
    let shouldThrow = true;
    function MaybeBoom(): JSX.Element {
      const [n] = useState(0);
      if (shouldThrow) throw new Error("first render boom");
      return <div>RECOVERED {n}</div>;
    }

    render(
      <MemoryRouter>
        <ErrorBoundary>
          <MaybeBoom />
        </ErrorBoundary>
      </MemoryRouter>,
    );

    // Boundary tripped.
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    // Simulate the underlying cause being fixed.
    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText(/RECOVERED/)).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });
});
