import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layout } from "@/components/Layout";
import { motion } from "framer-motion";
import { ApiError } from "@/api/client";
import { WEBHOOK_EVENT_TYPES, organizationsApi, type ApiKeyCreateResponse, type ApiKeyScope, type WebhookDeliveryStatus, type WebhookEventType } from "@/api/organizations";
import { ErrorState, LoadingState } from "@/components/DataStates";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { BarChart3, Bell, CheckCircle2, Copy, Database, FileText, KeyRound, Plug, RefreshCw, Scale, Send, Settings as SettingsIcon, Trash2, TriangleAlert, Users } from "lucide-react";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };
const API_KEY_SCOPES: ApiKeyScope[] = ["read", "write", "admin"];

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function defaultExpirationDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 90);
  return date.toISOString().slice(0, 10);
}

const settingsSections = [
  {
    icon: <SettingsIcon className="h-4 w-4" />,
    title: 'Workspace Settings',
    description: 'Configure workspace name, branding, and default preferences.',
    items: ['Workspace name', 'Logo', 'Default currency', 'Timezone'],
  },
  {
    icon: <Scale className="h-4 w-4" />,
    title: 'Scoring Weights',
    description: 'Customize how deal scores are calculated across dimensions.',
    items: ['Market attractiveness weight', 'Financial upside weight', 'Operational complexity weight', 'Permitting risk weight', 'Execution speed weight'],
  },
  {
    icon: <FileText className="h-4 w-4" />,
    title: 'Memo Templates',
    description: 'Manage investment memo templates and formatting preferences.',
    items: ['Default template', 'Custom sections', 'Header/footer', 'Branding'],
  },
  {
    icon: <Bell className="h-4 w-4" />,
    title: 'Notification Preferences',
    description: 'Control how and when you receive alerts about deal activity.',
    items: ['Email notifications', 'In-app alerts', 'Signal notifications', 'Weekly digest'],
  },
  {
    icon: <Database className="h-4 w-4" />,
    title: 'Data Sources',
    description: 'Connect and manage external data feeds for market intelligence.',
    items: ['CoStar integration', 'Public records', 'Census data', 'Permit feeds'],
  },
  {
    icon: <Users className="h-4 w-4" />,
    title: 'Team Members',
    description: 'Manage team access, roles, and permissions.',
    items: ['Sarah Chen — Managing Director', 'Marcus Reid — VP Acquisitions', 'Elena Voss — Senior Analyst', 'James Park — Analyst'],
  },
  {
    icon: <Plug className="h-4 w-4" />,
    title: 'API Connections',
    description: 'Manage API keys and integrations with external platforms.',
    items: ['Enrichment API', 'Document processing', 'CRM sync', 'Email integration'],
  },
];

export default function Settings() {
  const { organizationId, role } = useAuth();
  const orgId = organizationId ?? "";
  const isAdmin = role === "admin";
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [newKeyName, setNewKeyName] = useState("Warehouse export");
  const [newKeyScopes, setNewKeyScopes] = useState<ApiKeyScope[]>(["read"]);
  const [newKeyExpiresAt, setNewKeyExpiresAt] = useState(defaultExpirationDate);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [selectedUsageKeyId, setSelectedUsageKeyId] = useState<string | null>(null);
  const [webhookName, setWebhookName] = useState("Customer integration");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookSecretReference, setWebhookSecretReference] = useState("");
  const [webhookEventTypes, setWebhookEventTypes] = useState<WebhookEventType[]>(["deal.created"]);
  const [webhookTestEventType, setWebhookTestEventType] = useState<WebhookEventType>("deal.created");
  const [selectedWebhookSubscriptionId, setSelectedWebhookSubscriptionId] = useState<string | null>(null);
  const [webhookDeliveryStatusFilter, setWebhookDeliveryStatusFilter] = useState<WebhookDeliveryStatus | "all">("all");
  const [webhookDeliveryEventTypeFilter, setWebhookDeliveryEventTypeFilter] = useState<WebhookEventType | "all">("all");
  const [webhookDeliveryEventIdFilter, setWebhookDeliveryEventIdFilter] = useState("");

  const apiKeys = useQuery({
    queryKey: ["organization-api-keys", orgId],
    queryFn: () => organizationsApi.listApiKeys(orgId),
    enabled: Boolean(orgId && isAdmin),
  });

  const usageSummary = useQuery({
    queryKey: ["organization-api-key-usage", orgId, selectedUsageKeyId],
    queryFn: () => organizationsApi.getApiKeyUsage(orgId, selectedUsageKeyId ?? ""),
    enabled: Boolean(orgId && isAdmin && selectedUsageKeyId),
  });

  const webhookSummary = useQuery({
    queryKey: ["organization-webhook-summary", orgId],
    queryFn: () => organizationsApi.getWebhookDeliverySummary(orgId),
    enabled: Boolean(orgId && isAdmin),
  });

  const webhookDeadLetters = useQuery({
    queryKey: ["organization-webhook-dead-letters", orgId],
    queryFn: () => organizationsApi.listWebhookDeadLetters(orgId),
    enabled: Boolean(orgId && isAdmin),
  });

  const webhookSubscriptions = useQuery({
    queryKey: ["organization-webhook-subscriptions", orgId],
    queryFn: () => organizationsApi.listWebhookSubscriptions(orgId),
    enabled: Boolean(orgId && isAdmin),
  });

  const webhookDeliveries = useQuery({
    queryKey: [
      "organization-webhook-deliveries",
      orgId,
      selectedWebhookSubscriptionId,
      webhookDeliveryStatusFilter,
      webhookDeliveryEventTypeFilter,
      webhookDeliveryEventIdFilter,
    ],
    queryFn: () => organizationsApi.listWebhookDeliveries(orgId, {
      subscriptionId: selectedWebhookSubscriptionId ?? undefined,
      status: webhookDeliveryStatusFilter === "all" ? undefined : webhookDeliveryStatusFilter,
      eventType: webhookDeliveryEventTypeFilter === "all" ? undefined : webhookDeliveryEventTypeFilter,
      eventId: webhookDeliveryEventIdFilter,
      limit: 10,
    }),
    enabled: Boolean(orgId && isAdmin && selectedWebhookSubscriptionId),
  });

  const invalidateKeys = () =>
    queryClient.invalidateQueries({ queryKey: ["organization-api-keys", orgId] });

  const invalidateWebhooks = () => {
    queryClient.invalidateQueries({ queryKey: ["organization-webhook-summary", orgId] });
    queryClient.invalidateQueries({ queryKey: ["organization-webhook-dead-letters", orgId] });
    queryClient.invalidateQueries({ queryKey: ["organization-webhook-subscriptions", orgId] });
    queryClient.invalidateQueries({ queryKey: ["organization-webhook-deliveries", orgId] });
  };

  const createKey = useMutation({
    mutationFn: () => organizationsApi.createApiKey(orgId, {
      name: newKeyName.trim(),
      scopes: newKeyScopes,
      expires_at: newKeyExpiresAt ? new Date(`${newKeyExpiresAt}T23:59:59.000Z`).toISOString() : null,
    }),
    onSuccess: (key) => {
      setCreatedKey(key);
      setNewKeyName("Warehouse export");
      setNewKeyScopes(["read"]);
      setNewKeyExpiresAt(defaultExpirationDate());
      invalidateKeys();
      toast({ title: "API key created", description: "Copy the secret now. It will not be shown again." });
    },
    onError: (err) => {
      toast({
        title: "Could not create API key",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const revokeKey = useMutation({
    mutationFn: (keyId: string) => organizationsApi.revokeApiKey(orgId, keyId),
    onSuccess: () => {
      invalidateKeys();
      toast({ title: "API key revoked" });
    },
    onError: (err) => {
      toast({
        title: "Could not revoke API key",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const rebuildRollups = useMutation({
    mutationFn: (keyId: string) => organizationsApi.rebuildApiKeyUsageRollups(orgId, keyId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["organization-api-key-usage", orgId, result.api_key_id] });
      invalidateKeys();
      toast({
        title: "Usage rollups rebuilt",
        description: `${result.rebuilt_events.toLocaleString()} raw events were reconciled.`,
      });
    },
    onError: (err) => {
      toast({
        title: "Could not rebuild usage rollups",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const replayWebhookDelivery = useMutation({
    mutationFn: (deliveryId: string) => organizationsApi.replayWebhookDelivery(orgId, deliveryId),
    onSuccess: () => {
      invalidateWebhooks();
      toast({
        title: "Webhook replay queued",
        description: "A new pending delivery was created for retry processing.",
      });
    },
    onError: (err) => {
      toast({
        title: "Could not replay webhook",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const acknowledgeWebhookDeadLetter = useMutation({
    mutationFn: ({ deliveryId, note }: { deliveryId: string; note?: string }) =>
      organizationsApi.acknowledgeWebhookDeadLetter(orgId, deliveryId, note),
    onSuccess: () => {
      invalidateWebhooks();
      toast({
        title: "Dead letter acknowledged",
        description: "The acknowledgement was recorded in the audit log.",
      });
    },
    onError: (err) => {
      toast({
        title: "Could not acknowledge dead letter",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const createWebhookSubscription = useMutation({
    mutationFn: () => organizationsApi.createWebhookSubscription(orgId, {
      name: webhookName.trim(),
      target_url: webhookUrl.trim(),
      event_types: webhookEventTypes,
      secret_reference: webhookSecretReference.trim() || null,
    }),
    onSuccess: () => {
      setWebhookName("Customer integration");
      setWebhookUrl("");
      setWebhookSecretReference("");
      setWebhookEventTypes(["deal.created"]);
      invalidateWebhooks();
      toast({ title: "Webhook endpoint created" });
    },
    onError: (err) => {
      toast({
        title: "Could not create webhook endpoint",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const toggleWebhookStatus = useMutation({
    mutationFn: ({ subscriptionId, status }: { subscriptionId: string; status: "active" | "disabled" }) =>
      organizationsApi.updateWebhookSubscription(orgId, subscriptionId, { status }),
    onSuccess: () => {
      invalidateWebhooks();
      toast({ title: "Webhook endpoint updated" });
    },
    onError: (err) => {
      toast({
        title: "Could not update webhook endpoint",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const createWebhookTestEvent = useMutation({
    mutationFn: ({ eventType, subscriptionId }: { eventType: WebhookEventType; subscriptionId?: string }) =>
      organizationsApi.createWebhookTestEvent(orgId, {
        event_type: eventType,
        event_id: `admin-test-${Date.now()}`,
        subscription_id: subscriptionId ?? null,
        payload: {
          test: true,
          source: "settings_console",
          message: "Build Signals webhook test event",
        },
      }),
    onSuccess: (deliveries, variables) => {
      invalidateWebhooks();
      toast({
        title: "Webhook test event queued",
        description: `${deliveries.length.toLocaleString()} matching active endpoint${deliveries.length === 1 ? "" : "s"} will receive ${variables.eventType}.`,
      });
    },
    onError: (err) => {
      toast({
        title: "Could not queue webhook test",
        description: err instanceof ApiError ? err.message : "Try again.",
        variant: "destructive",
      });
    },
  });

  const toggleScope = (scope: ApiKeyScope) => {
    setNewKeyScopes((current) => {
      if (current.includes(scope)) {
        const next = current.filter((item) => item !== scope);
        return next.length ? next : current;
      }
      return [...current, scope].sort() as ApiKeyScope[];
    });
  };

  const toggleWebhookEventType = (eventType: WebhookEventType) => {
    setWebhookEventTypes((current) => {
      if (current.includes(eventType)) {
        const next = current.filter((item) => item !== eventType);
        return next.length ? next : current;
      }
      return [...current, eventType].sort() as WebhookEventType[];
    });
  };

  const copySecret = async () => {
    if (!createdKey?.secret) return;
    await navigator.clipboard.writeText(createdKey.secret);
    toast({ title: "Secret copied" });
  };

  return (
    <Layout>
      <div className="p-6 max-w-[900px] mx-auto">
        <motion.div {...fadeIn} className="mb-6">
          <h2 className="text-xl font-semibold font-display text-foreground">Settings</h2>
          <p className="text-sm text-muted-foreground mt-0.5">Configure your BuildSignals workspace</p>
        </motion.div>

        {isAdmin && (
          <motion.div {...fadeIn} className="mb-6 rounded-xl border bg-card p-5 card-shadow">
            <div className="mb-6 rounded-xl border bg-secondary/30 p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Plug className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-semibold text-foreground">Webhook endpoints</h3>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Configure signed customer integration endpoints for deal, signal, assessment, and eval events.
                  </p>
                </div>
                <span className="rounded-full bg-background px-3 py-1 text-xs text-muted-foreground">
                  HMAC signed
                </span>
              </div>

              <form
                className="mt-4 grid gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (webhookName.trim() && webhookUrl.trim()) createWebhookSubscription.mutate();
                }}
              >
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label htmlFor="webhook-name" className="text-xs font-medium text-muted-foreground">
                      Endpoint name
                    </label>
                    <input
                      id="webhook-name"
                      value={webhookName}
                      onChange={(event) => setWebhookName(event.target.value)}
                      className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                      minLength={3}
                      maxLength={120}
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="webhook-url" className="text-xs font-medium text-muted-foreground">
                      Target URL
                    </label>
                    <input
                      id="webhook-url"
                      type="url"
                      value={webhookUrl}
                      onChange={(event) => setWebhookUrl(event.target.value)}
                      placeholder="https://customer.example.com/webhooks/build-signals"
                      className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label htmlFor="webhook-secret-reference" className="text-xs font-medium text-muted-foreground">
                    Secret reference
                  </label>
                  <input
                    id="webhook-secret-reference"
                    value={webhookSecretReference}
                    onChange={(event) => setWebhookSecretReference(event.target.value)}
                    placeholder="vercel:BUILD_SIGNALS_WEBHOOK_SECRET"
                    className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                    maxLength={255}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Store the signing secret outside the UI and reference it here; do not paste raw secret values.
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Events</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {WEBHOOK_EVENT_TYPES.map((eventType) => (
                      <button
                        key={eventType}
                        type="button"
                        onClick={() => toggleWebhookEventType(eventType)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                          webhookEventTypes.includes(eventType)
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border bg-background text-muted-foreground"
                        }`}
                      >
                        {eventType}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <button
                    type="submit"
                    disabled={createWebhookSubscription.isPending || !webhookName.trim() || !webhookUrl.trim()}
                    className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                  >
                    {createWebhookSubscription.isPending ? "Creating..." : "Create webhook endpoint"}
                  </button>
                </div>
              </form>

              <div className="mt-5 rounded-lg border bg-background p-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                  <div>
                    <label htmlFor="webhook-test-event" className="text-xs font-medium text-muted-foreground">
                      Test event type
                    </label>
                    <select
                      id="webhook-test-event"
                      value={webhookTestEventType}
                      onChange={(event) => setWebhookTestEventType(event.target.value as WebhookEventType)}
                      className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm md:w-72"
                    >
                      {WEBHOOK_EVENT_TYPES.map((eventType) => (
                        <option key={eventType} value={eventType}>{eventType}</option>
                      ))}
                    </select>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Queues a signed test payload for every active endpoint subscribed to this event.
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={createWebhookTestEvent.isPending || !webhookSubscriptions.data?.some((subscription) => subscription.status === "active")}
                    onClick={() => createWebhookTestEvent.mutate({ eventType: webhookTestEventType })}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                  >
                    <Send className="h-3.5 w-3.5" />
                    {createWebhookTestEvent.isPending ? "Queuing..." : "Send test event"}
                  </button>
                </div>
              </div>

              <div className="mt-5">
                {webhookSubscriptions.isLoading && <p className="text-xs text-muted-foreground">Loading webhook endpoints...</p>}
                {webhookSubscriptions.error && <p className="text-xs text-destructive">Could not load webhook endpoints.</p>}
                {webhookSubscriptions.data && (
                  <div className="space-y-2">
                    {webhookSubscriptions.data.length === 0 && (
                      <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                        No webhook endpoints yet. Add one to stream Build Signals events into a customer workflow.
                      </p>
                    )}
                    {webhookSubscriptions.data.map((subscription) => (
                      <div key={subscription.id} className="rounded-lg border bg-background p-3">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-medium text-foreground">{subscription.name}</p>
                              <span className={`rounded-full px-2 py-0.5 text-xs ${
                                subscription.status === "active"
                                  ? "bg-emerald-500/10 text-emerald-700"
                                  : "bg-muted text-muted-foreground"
                              }`}>
                                {subscription.status}
                              </span>
                            </div>
                            <p className="mt-1 break-all text-xs text-muted-foreground">{subscription.target_url}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              Events: {subscription.event_types.join(", ")} · Updated {formatDate(subscription.updated_at)}
                            </p>
                            {subscription.secret_reference && (
                              <p className="mt-1 text-xs text-muted-foreground">
                                Secret reference: {subscription.secret_reference}
                              </p>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedWebhookSubscriptionId(subscription.id);
                                setWebhookDeliveryStatusFilter("all");
                                setWebhookDeliveryEventTypeFilter("all");
                                setWebhookDeliveryEventIdFilter("");
                              }}
                              className="inline-flex items-center justify-center rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                            >
                              View deliveries
                            </button>
                            <button
                              type="button"
                              disabled={createWebhookTestEvent.isPending || subscription.status !== "active"}
                              onClick={() => createWebhookTestEvent.mutate({
                                eventType: subscription.event_types[0],
                                subscriptionId: subscription.id,
                              })}
                              className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                            >
                              <Send className="h-3.5 w-3.5" />
                              Send test
                            </button>
                            <button
                              type="button"
                              disabled={toggleWebhookStatus.isPending}
                              onClick={() => {
                                const nextStatus = subscription.status === "active" ? "disabled" : "active";
                                if (window.confirm(`${nextStatus === "disabled" ? "Disable" : "Enable"} ${subscription.name}?`)) {
                                  toggleWebhookStatus.mutate({ subscriptionId: subscription.id, status: nextStatus });
                                }
                              }}
                              className="inline-flex items-center justify-center rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                            >
                              {subscription.status === "active" ? "Disable" : "Enable"}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {selectedWebhookSubscriptionId && (
                <div className="mt-5 rounded-lg border bg-background p-3">
                  <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Recent endpoint deliveries
                      </p>
                      <p className="mt-1 text-sm font-medium text-foreground">
                        {webhookSubscriptions.data?.find((subscription) => subscription.id === selectedWebhookSubscriptionId)?.name ?? "Selected endpoint"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => webhookDeliveries.refetch()}
                      className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Refresh deliveries
                    </button>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <div>
                      <label htmlFor="webhook-delivery-status-filter" className="text-xs font-medium text-muted-foreground">
                        Status
                      </label>
                      <select
                        id="webhook-delivery-status-filter"
                        value={webhookDeliveryStatusFilter}
                        onChange={(event) => setWebhookDeliveryStatusFilter(event.target.value as WebhookDeliveryStatus | "all")}
                        className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                      >
                        <option value="all">All statuses</option>
                        <option value="pending">Pending</option>
                        <option value="delivered">Delivered</option>
                        <option value="failed">Failed</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="webhook-delivery-event-type-filter" className="text-xs font-medium text-muted-foreground">
                        Event type
                      </label>
                      <select
                        id="webhook-delivery-event-type-filter"
                        value={webhookDeliveryEventTypeFilter}
                        onChange={(event) => setWebhookDeliveryEventTypeFilter(event.target.value as WebhookEventType | "all")}
                        className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                      >
                        <option value="all">All event types</option>
                        {WEBHOOK_EVENT_TYPES.map((eventType) => (
                          <option key={eventType} value={eventType}>{eventType}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor="webhook-delivery-event-id-filter" className="text-xs font-medium text-muted-foreground">
                        Event ID contains
                      </label>
                      <input
                        id="webhook-delivery-event-id-filter"
                        value={webhookDeliveryEventIdFilter}
                        onChange={(event) => setWebhookDeliveryEventIdFilter(event.target.value)}
                        placeholder="admin-test, deal id, event id"
                        className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                      />
                    </div>
                  </div>
                  {webhookDeliveries.isLoading && (
                    <p className="mt-3 text-xs text-muted-foreground">Loading recent deliveries...</p>
                  )}
                  {webhookDeliveries.error && (
                    <p className="mt-3 text-xs text-destructive">Could not load recent deliveries.</p>
                  )}
                  {webhookDeliveries.data && (
                    <div className="mt-3 space-y-2">
                      {webhookDeliveries.data.length === 0 && (
                        <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
                          No deliveries match these filters. Send a test event or broaden the status, event type, or event ID search.
                        </p>
                      )}
                      {webhookDeliveries.data.map((delivery) => (
                        <div key={delivery.id} className="rounded-lg border p-3">
                          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                            <div>
                              <p className="text-sm font-medium text-foreground">{delivery.event_type}</p>
                              <p className="mt-1 text-xs text-muted-foreground">
                                Event {delivery.event_id} · Created {formatDate(delivery.created_at)}
                              </p>
                            </div>
                            <span className={`rounded-full px-2 py-0.5 text-xs ${
                              delivery.status === "delivered"
                                ? "bg-emerald-500/10 text-emerald-700"
                                : delivery.status === "failed"
                                  ? "bg-destructive/10 text-destructive"
                                  : "bg-amber-500/10 text-amber-700"
                            }`}>
                              {delivery.status}
                            </span>
                          </div>
                          <p className="mt-2 text-xs text-muted-foreground">
                            Attempts: {delivery.attempt_count.toLocaleString()} · Last attempt: {formatDate(delivery.last_attempted_at)}
                            {delivery.response_status_code ? ` · Response ${delivery.response_status_code}` : ""}
                          </p>
                          {delivery.error_message && (
                            <p className="mt-2 text-xs text-destructive">{delivery.error_message}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="mb-6 rounded-xl border bg-secondary/30 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <Plug className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-semibold text-foreground">Webhook delivery health</h3>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Monitor customer integration delivery, retries, and failed events that need operator review.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    webhookSummary.refetch();
                    webhookDeadLetters.refetch();
                  }}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border bg-background px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Refresh
                </button>
              </div>

              {(webhookSummary.isLoading || webhookDeadLetters.isLoading) && (
                <p className="mt-4 text-xs text-muted-foreground">Loading webhook delivery status...</p>
              )}
              {(webhookSummary.error || webhookDeadLetters.error) && (
                <p className="mt-4 text-xs text-destructive">Could not load webhook delivery status.</p>
              )}
              {webhookSummary.data && (
                <div className="mt-4 grid gap-3 md:grid-cols-4">
                  <div className="rounded-lg border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Delivery posture</p>
                    <div className="mt-2 flex items-center gap-2">
                      {webhookSummary.data.dead_lettered > 0 ? (
                        <TriangleAlert className="h-4 w-4 text-amber-600" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      )}
                      <p className="text-sm font-semibold text-foreground">
                        {webhookSummary.data.dead_lettered > 0 ? "Review needed" : "Healthy"}
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {webhookSummary.data.subscriptions_active.toLocaleString()} active subscriptions
                    </p>
                  </div>
                  <div className="rounded-lg border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Dead letters</p>
                    <p className="mt-1 text-2xl font-semibold text-foreground">
                      {webhookSummary.data.dead_lettered.toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {webhookSummary.data.failed.toLocaleString()} failed total
                    </p>
                  </div>
                  <div className="rounded-lg border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Failure rate</p>
                    <p className="mt-1 text-2xl font-semibold text-foreground">
                      {formatPercent(webhookSummary.data.failure_rate)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {webhookSummary.data.delivered.toLocaleString()} delivered
                    </p>
                  </div>
                  <div className="rounded-lg border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Latest attempt</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {formatDate(webhookSummary.data.latest_attempted_at)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {webhookSummary.data.pending.toLocaleString()} pending retries
                    </p>
                  </div>
                </div>
              )}
              {webhookSummary.data?.last_error_message && (
                <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  Last delivery error: {webhookSummary.data.last_error_message}
                </p>
              )}
              {webhookDeadLetters.data && webhookDeadLetters.data.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Latest dead-lettered deliveries
                  </p>
                  {webhookDeadLetters.data.map((delivery) => (
                    <div key={delivery.id} className="rounded-lg border bg-background p-3">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div>
                          <p className="text-sm font-medium text-foreground">{delivery.event_type}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {delivery.attempt_count.toLocaleString()} attempts · {formatDate(delivery.updated_at)}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={replayWebhookDelivery.isPending}
                            onClick={() => {
                              if (window.confirm("Replay this failed webhook delivery? A new pending delivery will be created.")) {
                                replayWebhookDelivery.mutate(delivery.id);
                              }
                            }}
                            className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            Replay
                          </button>
                          <button
                            type="button"
                            disabled={acknowledgeWebhookDeadLetter.isPending}
                            onClick={() => {
                              const note = window.prompt("Acknowledge this dead letter with an optional operator note.");
                              if (note !== null) {
                                acknowledgeWebhookDeadLetter.mutate({ deliveryId: delivery.id, note });
                              }
                            }}
                            className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Acknowledge
                          </button>
                        </div>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Event {delivery.event_id} · Subscription {delivery.subscription_id.slice(0, 8)}
                      </p>
                      {delivery.error_message && (
                        <p className="mt-2 text-xs text-destructive">{delivery.error_message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold text-foreground">Organization API keys</h3>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Issue tenant-scoped machine credentials for customer exports and partner integrations.
                </p>
              </div>
              <span className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
                /v1/public
              </span>
            </div>

            {createdKey && (
              <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">One-time secret</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Store this securely. Build Signals only stores the hashed key and cannot show it again.
                </p>
                <div className="mt-3 flex flex-col gap-2 md:flex-row">
                  <code className="flex-1 overflow-x-auto rounded-md bg-background px-3 py-2 text-xs">
                    {createdKey.secret}
                  </code>
                  <button
                    type="button"
                    onClick={() => void copySecret()}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Copy
                  </button>
                </div>
              </div>
            )}

            <form
              className="mt-4 grid gap-3 md:grid-cols-[1fr_180px_auto]"
              onSubmit={(event) => {
                event.preventDefault();
                if (newKeyName.trim()) createKey.mutate();
              }}
            >
              <div>
                <label htmlFor="api-key-name" className="text-xs font-medium text-muted-foreground">Key name</label>
                <input
                  id="api-key-name"
                  value={newKeyName}
                  onChange={(event) => setNewKeyName(event.target.value)}
                  className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                  minLength={3}
                  maxLength={120}
                  required
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  {API_KEY_SCOPES.map((scope) => (
                    <button
                      key={scope}
                      type="button"
                      onClick={() => toggleScope(scope)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        newKeyScopes.includes(scope)
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border bg-secondary text-muted-foreground"
                      }`}
                    >
                      {scope}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="api-key-expires" className="text-xs font-medium text-muted-foreground">Expires</label>
                <input
                  id="api-key-expires"
                  type="date"
                  value={newKeyExpiresAt}
                  onChange={(event) => setNewKeyExpiresAt(event.target.value)}
                  className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm"
                  required
                />
              </div>
              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={createKey.isPending || !newKeyName.trim()}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  {createKey.isPending ? "Creating..." : "Create key"}
                </button>
              </div>
            </form>

            <div className="mt-5">
              {apiKeys.isLoading && <LoadingState message="Loading API keys..." />}
              {apiKeys.error && <ErrorState message="Could not load API keys." onRetry={() => apiKeys.refetch()} />}
              {apiKeys.data && (
                <div className="space-y-2">
                  {apiKeys.data.length === 0 && (
                    <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                      No API keys yet. Create a read-only key to power exports or partner demos.
                    </p>
                  )}
                  {apiKeys.data.map((key) => (
                    <div key={key.id} className="flex flex-col gap-3 rounded-lg border p-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{key.name}</p>
                          <code className="rounded bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{key.key_prefix}</code>
                          {key.revoked_at && <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">Revoked</span>}
                          {!key.revoked_at && key.rotation_due && <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700">Rotate soon</span>}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Scopes: {key.scopes.join(", ")} · Created {formatDate(key.created_at)} · Expires {formatDate(key.expires_at)} · Last used {formatDate(key.last_used_at)}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Usage: {key.usage_total_calls.toLocaleString()} calls · Last call {formatDate(key.usage_last_called_at)}
                          {key.rate_limit_limit && key.rate_limit_window_seconds
                            ? ` · Limit ${key.rate_limit_limit.toLocaleString()}/${key.rate_limit_window_seconds}s`
                            : ""}
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled={Boolean(key.revoked_at) || revokeKey.isPending}
                        onClick={() => {
                          if (window.confirm(`Revoke ${key.name}? Existing integrations using this key will stop working.`)) {
                            revokeKey.mutate(key.id);
                          }
                        }}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Revoke
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedUsageKeyId((current) => (current === key.id ? null : key.id))}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
                      >
                        <BarChart3 className="h-3.5 w-3.5" />
                        {selectedUsageKeyId === key.id ? "Hide usage" : "View usage"}
                      </button>
                      {selectedUsageKeyId === key.id && (
                        <div className="md:col-span-2 rounded-lg border bg-secondary/40 p-3">
                          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                              Daily usage rollups
                            </p>
                            <button
                              type="button"
                              onClick={() => rebuildRollups.mutate(key.id)}
                              disabled={rebuildRollups.isPending}
                              className="inline-flex items-center justify-center gap-2 rounded-lg border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                            >
                              <RefreshCw className="h-3.5 w-3.5" />
                              {rebuildRollups.isPending ? "Rebuilding..." : "Rebuild rollups"}
                            </button>
                          </div>
                          {usageSummary.isLoading && <p className="mt-3 text-xs text-muted-foreground">Loading usage...</p>}
                          {usageSummary.error && (
                            <p className="mt-3 text-xs text-destructive">Could not load usage detail.</p>
                          )}
                          {usageSummary.data && (
                            <div className="mt-3 grid gap-3 md:grid-cols-3">
                              {usageSummary.data.daily.slice(0, 3).map((bucket) => (
                                <div key={bucket.usage_date} className="rounded-lg border bg-background p-3">
                                  <p className="text-xs text-muted-foreground">{bucket.usage_date}</p>
                                  <p className="mt-1 text-lg font-semibold text-foreground">
                                    {bucket.total_calls.toLocaleString()} calls
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {bucket.total_items.toLocaleString()} items · {bucket.average_latency_ms}ms avg
                                  </p>
                                </div>
                              ))}
                              {usageSummary.data.daily.length === 0 && (
                                <p className="text-xs text-muted-foreground">No daily rollups have been recorded yet.</p>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}

        <div className="space-y-4">
          {settingsSections.map((section, i) => (
            <motion.div key={i} {...fadeIn} transition={{ delay: i * 0.05 }}>
              <div className="rounded-xl border bg-card p-5 card-shadow hover:card-shadow-hover transition-shadow">
                <div className="flex items-start gap-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                    {section.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-foreground">{section.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{section.description}</p>
                    <div className="flex flex-wrap gap-2 mt-3">
                      {section.items.map((item, j) => (
                        <span key={j} className="text-xs bg-secondary px-2.5 py-1 rounded-md text-muted-foreground">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-lg bg-secondary">
                    Configure
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
