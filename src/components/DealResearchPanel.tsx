import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FlaskConical, Loader2, RefreshCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { dealResearchApi, type DealResearchResponse } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader,
  AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel,
} from '@/components/ui/alert-dialog';

const errorMessages: Record<number, string> = {
  401: 'Your session expired. Sign in again before starting research.',
  403: 'Research is not permitted for this account.',
  404: 'This saved deal is no longer available.',
  409: 'The research request conflicted with another request or workspace change. Review before trying again.',
  422: 'This saved deal cannot be researched in its current state.',
  429: 'The research run limit has been reached. No automatic retry will occur.',
  503: 'Research is temporarily unavailable. No automatic retry will occur.',
};

export function DealResearchPanel({ dealId }: { dealId: string | undefined }) {
  const { organizationId, user, role, isAuthenticated, isDemo, isLoading } = useAuth();
  if (!dealId || !organizationId || !user || !isAuthenticated || isLoading || isDemo
    || (role !== 'admin' && role !== 'editor')) return null;
  return <DealResearchContent key={JSON.stringify([organizationId, user.id, dealId, role])}
    dealId={dealId} organizationId={organizationId} userId={user.id} role={role} />;
}

function DealResearchContent({ dealId, organizationId, userId, role }: {
  dealId: string; organizationId: string; userId: string; role: string;
}) {
  const capabilities = useQuery({
    queryKey: ['deal-research-capabilities', organizationId, userId, dealId, role],
    queryFn: () => dealResearchApi.capabilities(dealId),
    retry: false, gcTime: 0, refetchOnMount: 'always', refetchOnWindowFocus: false,
  });
  const [consentOpen, setConsentOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DealResearchResponse | null>(null);
  const active = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  const data = capabilities.data;
  const available = !capabilities.isError && data?.enabled === true
    && Number.isSafeInteger(data.daily_run_limit) && data.daily_run_limit >= 0
    && Number.isSafeInteger(data.remaining_runs) && data.remaining_runs >= 0;
  const disabled = pending || capabilities.isFetching || !available || data.remaining_runs === 0;

  const startResearch = async () => {
    if (!consentOpen || disabled || inFlight.current) return;
    inFlight.current = true;
    setConsentOpen(false); setPending(true); setError(null); setResult(null);
    try {
      const response = await dealResearchApi.run(dealId, crypto.randomUUID());
      if (active.current) setResult(response);
    } catch (err) {
      if (active.current) {
        const status = typeof err === 'object' && err !== null && 'status' in err ? Number(err.status) : 0;
        setError(errorMessages[status] ?? 'Research did not complete. A run may have been used. Review before trying again.');
      }
    } finally {
      if (active.current) {
        await capabilities.refetch();
        if (active.current) { inFlight.current = false; setPending(false); }
      }
    }
  };

  // Capability refresh failures must not discard an already received paid result.
  if (!available && !result && !error && !pending) return null;
  return <section aria-label="Deal research" className="border-y py-5 min-w-0">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-sm font-semibold">Deal research</h3>
      <AlertDialog open={consentOpen} onOpenChange={setConsentOpen}>
        <AlertDialogTrigger asChild>
          <Button type="button" variant="outline" size="sm" disabled={disabled}>
            {pending ? <Loader2 aria-hidden="true" className="animate-spin" /> : <FlaskConical aria-hidden="true" />}
            {pending ? 'Research running' : 'Run research'}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent className="max-w-[calc(100%-2rem)] sm:max-w-lg rounded-lg">
          <form aria-label="Confirm research run" onSubmit={event => { event.preventDefault(); void startResearch(); }}>
            <AlertDialogHeader>
              <AlertDialogTitle>Run paid research?</AlertDialogTitle>
              <AlertDialogDescription>
                Send saved deal facts to configured model providers and use one run. Provider charges may apply.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="mt-5 gap-2 sm:gap-0">
              <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
              <Button type="submit" disabled={disabled}>Confirm and run</Button>
            </AlertDialogFooter>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    {available ? <p className="mt-2 text-xs text-muted-foreground">{data.remaining_runs} of {data.daily_run_limit} daily runs remaining</p>
      : capabilities.isError ? <div className="mt-2 flex flex-wrap items-center gap-2">
        <p role="alert" className="text-xs text-muted-foreground">Run quota unavailable.</p>
        <Button type="button" variant="outline" size="sm" disabled={pending || capabilities.isFetching}
          onClick={() => { void capabilities.refetch(); }}>
          <RefreshCw aria-hidden="true" />Refresh quota
        </Button>
      </div> : <p className="mt-2 text-xs text-muted-foreground">Research is currently disabled.</p>}
    {pending && <p role="status" className="mt-3 text-sm">Research in progress...</p>}
    {error && <p role="alert" className="mt-3 text-sm">{error}</p>}
    {result && <ResearchFindings response={result} />}
  </section>;
}

function ResearchFindings({ response }: { response: DealResearchResponse }) {
  const { result } = response;
  const finalStage = result.stages[result.stages.length - 1];
  const known = (value: number | null) => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  return <div className="mt-4 space-y-4 text-sm [overflow-wrap:anywhere]">
    <div className="space-y-1 text-xs text-muted-foreground">
      <p>Model-generated / research only</p>
      <p>Saved workspace facts / not verified</p>
    </div>
    {finalStage && <>
      <div>
        <h4 className="font-semibold">Quote-backed facts</h4>
        {finalStage.findings.facts.length === 0 ? <p className="mt-2 text-muted-foreground">No quoted facts returned.</p>
          : <ul className="mt-2 space-y-3">
            {finalStage.findings.facts.map((fact, index) => <li key={index} className="border-l-2 pl-3">
              <blockquote className="whitespace-pre-wrap">{fact.quote}</blockquote>
              <p className="mt-1 text-xs text-muted-foreground">Source: {fact.source_id}</p>
            </li>)}
          </ul>}
      </div>
      {(['unknowns', 'questions'] as const).map(kind => <div key={kind}>
        <h4 className="font-semibold">{kind === 'unknowns' ? 'Unknowns' : 'Questions'}</h4>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
          {finalStage.findings[kind].map((item, index) => <li key={index}>{item}</li>)}
        </ul>
        {finalStage.findings[kind].length === 0 && <p className="mt-2 text-muted-foreground">None returned.</p>}
      </div>)}
    </>}
    {result.limitations.length > 0 && <div>
      <h4 className="font-semibold">Limitations</h4>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {result.limitations.map((item, index) => <li key={index}>{item}</li>)}
      </ul>
    </div>}
    <details className="border-t pt-3 text-xs text-muted-foreground">
      <summary className="cursor-pointer font-medium">Run details</summary>
      <p className="mt-2">Run: {response.run_id}</p>
      {result.usage.map((usage, index) => <div key={index} className="mt-3 space-y-1">
        <p>Requested model: {usage.requested_model}</p>
        <p>Served model: {usage.served_model ?? 'Not reported'} / Provider: {usage.provider ?? 'Not reported'}</p>
        <p>{known(usage.cost) ? `Reported cost: ${usage.cost}` : 'Cost not reported'}</p>
        {known(usage.total_tokens) && <p>Reported tokens: {usage.total_tokens}</p>}
        {known(usage.latency_ms) && <p>Reported latency: {usage.latency_ms} ms</p>}
      </div>)}
    </details>
  </div>;
}
