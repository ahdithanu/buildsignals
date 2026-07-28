import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * Pins the password reset UI contract:
 *   - ForgotPassword submits the email to passwordResetApi.forgot and shows
 *     the generic success message.
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
  });

  it("submits the email and shows the generic success message", async () => {
    forgotMock.mockResolvedValueOnce(undefined);
    renderForgot();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(forgotMock).toHaveBeenCalledWith("alice@example.com");
    });
    expect(
      await screen.findByText(
        /if an account with that email exists/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows the same success message even when the API errors (no enumeration)", async () => {
    forgotMock.mockRejectedValueOnce(new ApiError("nope", 500));
    renderForgot();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "ghost@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(
      await screen.findByText(/if an account with that email exists/i),
    ).toBeInTheDocument();
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
