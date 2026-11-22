import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * Pins the password reset UI contract:
 *   - ForgotPassword submits the email to passwordResetApi.forgot and shows
 *     a non-enumerating acknowledgement only after a successful request.
 *   - ForgotPassword failures show a generic retryable alert, not false success.
 *   - ResetPassword without a ?token= renders an error and never calls the API.
 *   - ResetPassword with mismatched passwords does not submit.
 *   - ResetPassword with matching passwords calls reset() and navigates to /login.
 *   - ResetPassword shows the invalid-link message on 400.
 */

vi.mock("@/api/password_reset", () => ({
  passwordResetApi: {
    forgot: vi.fn(),
    reset: vi.fn(),
  },
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>(
      "react-router-dom",
    );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { passwordResetApi } from "@/api/password_reset";
import { ApiError } from "@/api/client";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

const forgotMock = passwordResetApi.forgot as unknown as ReturnType<
  typeof vi.fn
>;
const resetMock = passwordResetApi.reset as unknown as ReturnType<typeof vi.fn>;

const renderForgot = () =>
  render(
    <MemoryRouter initialEntries={["/forgot-password"]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPassword />} />
      </Routes>
    </MemoryRouter>,
  );

const renderReset = (initialEntry: string) =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPassword />} />
      </Routes>
    </MemoryRouter>,
  );

describe("<ForgotPassword>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    forgotMock.mockReset();
  });

  it("acknowledges a successful request without promising email delivery", async () => {
    forgotMock.mockResolvedValueOnce(undefined);
    renderForgot();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(forgotMock).toHaveBeenCalledWith("alice@example.com");
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If an account with that email exists, a password reset has been requested. Check your inbox.",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/we've sent a reset link/i)).not.toBeInTheDocument();
  });

  it.each([
    ["503", new ApiError("SMTP stack: account ghost@example.com exists", 503)],
    ["500", new ApiError("Traceback: no account for ghost@example.com", 500)],
    ["network", new TypeError("Network transport failed with private backend details")],
  ])("shows a safe retryable alert, never success, after a %s failure", async (_label, error) => {
    forgotMock.mockRejectedValueOnce(error);
    renderForgot();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "ghost@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password reset is temporarily unavailable. Please try again.",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText(/if an account with that email exists/i)).not.toBeInTheDocument();
    expect(screen.queryByText(error.message)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveValue("ghost@example.com");
    expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled();
  });

  it.each([503, 429])("retries a %s failure with the preserved email and acknowledges only success", async status => {
    let resolveRetry!: () => void;
    forgotMock.mockRejectedValueOnce(new ApiError("private backend failure", status))
      .mockImplementationOnce(() => new Promise<void>(resolve => { resolveRetry = resolve; }));
    renderForgot();
    const email = screen.getByLabelText(/email/i);
    fireEvent.change(email, { target: { value: "alice@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await screen.findByRole("alert");
    expect(screen.getByLabelText(/email/i)).toBe(email);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(screen.getByLabelText(/email/i)).toHaveValue("alice@example.com");
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(forgotMock).toHaveBeenNthCalledWith(1, "alice@example.com");
    expect(forgotMock).toHaveBeenNthCalledWith(2, "alice@example.com");
    resolveRetry();
    expect(await screen.findByRole("status")).toHaveTextContent("a password reset has been requested");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("preserves the 429 rate-limit message without reflecting backend details", async () => {
    forgotMock.mockRejectedValueOnce(new ApiError("Account-specific throttle for alice@example.com", 429));
    renderForgot();
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "alice@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests, try again in a bit.");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText(/Account-specific throttle/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveValue("alice@example.com");
  });
});

describe("<ResetPassword>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders an error and does not call the API when token is missing", () => {
    renderReset("/reset-password");
    expect(
      screen.getByText(/no reset token was provided/i),
    ).toBeInTheDocument();
    expect(resetMock).not.toHaveBeenCalled();
  });

  it("does not submit when the two passwords don't match", async () => {
    renderReset("/reset-password?token=abc123");

    fireEvent.change(screen.getByLabelText(/^new password$/i), {
      target: { value: "CorrectHorseBattery42" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "Different42!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    expect(
      await screen.findByText(/passwords do not match/i),
    ).toBeInTheDocument();
    expect(resetMock).not.toHaveBeenCalled();
  });

  it("calls reset and navigates to /login on success", async () => {
    resetMock.mockResolvedValueOnce(undefined);
    renderReset("/reset-password?token=abc123");

    fireEvent.change(screen.getByLabelText(/^new password$/i), {
      target: { value: "CorrectHorseBattery42" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "CorrectHorseBattery42" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(resetMock).toHaveBeenCalledWith(
        "abc123",
        "CorrectHorseBattery42",
      );
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/login");
    });
  });

  it("shows the invalid-link message on 400", async () => {
    resetMock.mockRejectedValueOnce(
      new ApiError("Invalid or expired reset token", 400),
    );
    renderReset("/reset-password?token=stale");

    fireEvent.change(screen.getByLabelText(/^new password$/i), {
      target: { value: "CorrectHorseBattery42" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "CorrectHorseBattery42" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    expect(
      await screen.findByText(/this reset link is invalid or expired/i),
    ).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
