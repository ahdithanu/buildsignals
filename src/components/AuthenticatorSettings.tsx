import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { KeyRound, Loader2, RotateCw, ShieldCheck, ShieldOff, X } from "lucide-react";
import { ApiError } from "@/api/client";
import { twofaApi, type AuthenticatorStatus } from "@/api/twofa";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";

type Mode = "idle" | "enroll" | "disable";
type Operation = "status" | "setup" | "verify" | "disable";

function AuthenticatorSession() {
  const [status, setStatus] = useState<AuthenticatorStatus | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [busy, setBusy] = useState<Operation | null>("status");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const generation = useRef(0);
  const inFlight = useRef(false);
  const codeInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);

  const clearCredentials = useCallback(() => {
    setSecret("");
    setCode("");
    setPassword("");
  }, []);

  const loadStatus = useCallback(async () => {
    const operation = ++generation.current;
    inFlight.current = true;
    clearCredentials();
    setMode("idle");
    setBusy("status");
    setError(null);
    setNotice(null);
    try {
      const result = await twofaApi.status();
      if (operation === generation.current) setStatus(result);
    } catch {
      if (operation === generation.current) {
        setStatus(null);
        setError("Unable to load authenticator status.");
      }
    } finally {
      if (operation === generation.current) {
        inFlight.current = false;
        setBusy(null);
      }
    }
  }, [clearCredentials]);

  useEffect(() => {
    void loadStatus();
    return () => {
      // Retire in-flight responses; the keyed session's sensitive state is discarded.
      generation.current += 1;
    };
  }, [loadStatus]);

  useEffect(() => {
    if (mode === "enroll") codeInput.current?.focus();
    if (mode === "disable") passwordInput.current?.focus();
  }, [mode]);

  function cancel() {
    generation.current += 1;
    inFlight.current = false;
    clearCredentials();
    setStatus(null);
    setMode("idle");
    setBusy(null);
    setError(null);
    setNotice(null);
    void loadStatus();
  }

  async function startEnrollment() {
    if (inFlight.current || !status?.enrollment_ready || status.enabled || error) return;
    const operation = ++generation.current;
    inFlight.current = true;
    clearCredentials();
    setBusy("setup");
    setNotice(null);
    try {
      // Recheck before rotating a pending key; another tab may have enabled MFA.
      const current = await twofaApi.status();
      if (operation !== generation.current) return;
      setStatus(current);
      if (current.enabled || !current.enrollment_ready) return;
      const nextSecret = await twofaApi.setup();
      if (operation !== generation.current) return;
      setSecret(nextSecret);
      setMode("enroll");
    } catch {
      if (operation === generation.current) {
        clearCredentials();
        setStatus(null);
        setError("Enrollment outcome unknown. Check status before starting again.");
      }
    } finally {
      if (operation === generation.current) {
        inFlight.current = false;
        setBusy(null);
      }
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !/^[0-9]{6}$/.test(code)) return;
    if (mode === "disable" && !password) return;
    if (mode !== "disable" && (mode !== "enroll" || !secret)) return;
    const action = mode === "disable" ? "disable" : "verify";
    const operation = ++generation.current;
    inFlight.current = true;
    setBusy(action);
    setError(null);
    setNotice(null);
    try {
      // Dispatch then clear inputs immediately, including after failed requests.
      const pending = action === "disable" ? twofaApi.disable(password, code) : twofaApi.verify(code);
      setPassword("");
      setCode("");
      await pending;
      if (operation !== generation.current) return;
      clearCredentials();
      setMode("idle");
      setStatus((current) => current ? { ...current, enabled: action === "verify" } : null);
      setNotice(action === "verify" ? "Authenticator enabled." : "Authenticator disabled.");
    } catch (failure) {
      if (operation !== generation.current) return;
      if (action === "verify" && failure instanceof ApiError && failure.status === 400) {
        setError("Code not accepted. Enter a new six-digit code or cancel enrollment.");
      } else {
        clearCredentials();
        setMode("idle");
        setStatus(null);
        setError("Change outcome unknown. Check status before trying again.");
      }
    } finally {
      if (operation === generation.current) {
        setPassword("");
        setCode("");
        inFlight.current = false;
        setBusy(null);
      }
    }
  }

  return (
    <section aria-labelledby="authenticator-heading" className="sentry-block min-w-0 space-y-4 border-b py-6" data-private="true">
      <h2 id="authenticator-heading" className="flex items-center gap-2 text-base font-semibold">
        <ShieldCheck aria-hidden="true" className="h-4 w-4 shrink-0" />
        Authenticator
      </h2>
      <p role="status" className="flex items-center gap-2 text-sm" aria-live="polite">
        {busy === "status" && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
        {busy === "status" ? "Checking status..." : status?.enabled ? "Enabled" : !status ? "Status unavailable" : mode === "enroll" ? "Confirmation required" : "Not enabled"}
      </p>
      {status && !status.enrollment_ready && (
        <p className="text-sm text-muted-foreground">Authenticator management unavailable. Contact your administrator.</p>
      )}
      {error && <p role="alert" className="text-sm text-destructive [overflow-wrap:anywhere]">{error}</p>}
      {notice && <p role="status" className="text-sm">{notice}</p>}

      {mode === "idle" && !busy && (error || !status || !status.enrollment_ready) ? (
        <Button variant="outline" className="min-h-11" onClick={() => void loadStatus()}>
          <RotateCw aria-hidden="true" /> Check status
        </Button>
      ) : mode === "idle" && status?.enrollment_ready && (
        status.enabled ? (
          <Button variant="outline" className="min-h-11" disabled={!!busy} onClick={() => { setNotice(null); setMode("disable"); }}>
            <ShieldOff aria-hidden="true" /> Disable authenticator
          </Button>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Starting enrollment replaces any unconfirmed key.</p>
            <Button className="min-h-11" disabled={!!busy} onClick={() => void startEnrollment()}>
              <KeyRound aria-hidden="true" /> {busy === "setup" ? "Starting..." : "Set up authenticator"}
            </Button>
          </div>
        )
      )}

      {mode === "enroll" && secret && busy !== "verify" && (
        <div className="min-w-0 space-y-3">
          <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
            <div><dt className="text-muted-foreground">Issuer</dt><dd>BuildSignals</dd></div>
            <div><dt className="text-muted-foreground">Type</dt><dd>Time-based (TOTP)</dd></div>
            <div><dt className="text-muted-foreground">Digits</dt><dd>6</dd></div>
            <div><dt className="text-muted-foreground">Period</dt><dd>30 seconds</dd></div>
          </dl>
          <div className="space-y-1.5">
            <Label htmlFor="authenticator-key">Manual setup key</Label>
            <Input id="authenticator-key" value={secret} readOnly autoComplete="off" spellCheck={false}
              className="sentry-mask min-h-11 font-mono" data-private="true" data-lpignore="true" data-1p-ignore="true" />
          </div>
        </div>
      )}

      {mode !== "idle" && (
        <form onSubmit={submit} autoComplete="off" className="space-y-4">
          {mode === "disable" && (
            <div className="space-y-1.5">
              <Label htmlFor="authenticator-password">Current password</Label>
              <Input ref={passwordInput} id="authenticator-password" type="password" autoComplete="off" required
                className="sentry-mask min-h-11" data-private="true" value={password} disabled={!!busy}
                onChange={(event) => setPassword(event.target.value)} />
            </div>
          )}
          <div className="max-w-xs space-y-1.5">
            <Label htmlFor="authenticator-code">Authenticator code</Label>
            <Input ref={codeInput} id="authenticator-code" type="text" inputMode="numeric" autoComplete="off"
              className="sentry-mask min-h-11" data-private="true" pattern="[0-9]{6}" maxLength={6} required
              value={code} disabled={!!busy} onChange={(event) => setCode(event.target.value)} />
          </div>
          <div className="flex flex-wrap gap-3">
            <Button type="submit" className="min-h-11" variant={mode === "disable" ? "destructive" : "default"}
              disabled={!!busy || !/^[0-9]{6}$/.test(code) || (mode === "disable" && !password)}>
              {mode === "disable" ? <ShieldOff aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
              {busy ? "Submitting..." : mode === "disable" ? "Confirm disable" : "Confirm authenticator"}
            </Button>
            <Button type="button" variant="outline" className="min-h-11" disabled={!!busy} onClick={cancel}>
              <X aria-hidden="true" /> Cancel
            </Button>
          </div>
        </form>
      )}
      {busy === "setup" && (
        <Button variant="outline" className="min-h-11" onClick={cancel}><X aria-hidden="true" /> Cancel</Button>
      )}
    </section>
  );
}

export function AuthenticatorSettings() {
  const { user, organizationId, role, isLoading, isAuthenticated } = useAuth();
  if (isLoading || !isAuthenticated || !user) return null;
  return <AuthenticatorSession key={`${user.id}:${organizationId ?? ""}:${role ?? ""}`} />;
}
