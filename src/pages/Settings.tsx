import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layout } from "@/components/Layout";
import { motion } from "framer-motion";
import { ApiError } from "@/api/client";
import { organizationsApi, type ApiKeyCreateResponse, type ApiKeyScope } from "@/api/organizations";
import { ErrorState, LoadingState } from "@/components/DataStates";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { Bell, Copy, Database, FileText, KeyRound, Plug, Scale, Settings as SettingsIcon, Trash2, Users } from "lucide-react";

const fadeIn = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };
const API_KEY_SCOPES: ApiKeyScope[] = ["read", "write", "admin"];

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
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
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);

  const apiKeys = useQuery({
    queryKey: ["organization-api-keys", orgId],
    queryFn: () => organizationsApi.listApiKeys(orgId),
    enabled: Boolean(orgId && isAdmin),
  });

  const invalidateKeys = () =>
    queryClient.invalidateQueries({ queryKey: ["organization-api-keys", orgId] });

  const createKey = useMutation({
    mutationFn: () => organizationsApi.createApiKey(orgId, {
      name: newKeyName.trim(),
      scopes: newKeyScopes,
    }),
    onSuccess: (key) => {
      setCreatedKey(key);
      setNewKeyName("Warehouse export");
      setNewKeyScopes(["read"]);
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

  const toggleScope = (scope: ApiKeyScope) => {
    setNewKeyScopes((current) => {
      if (current.includes(scope)) {
        const next = current.filter((item) => item !== scope);
        return next.length ? next : current;
      }
      return [...current, scope].sort() as ApiKeyScope[];
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
              className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]"
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
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Scopes: {key.scopes.join(", ")} · Created {formatDate(key.created_at)} · Last used {formatDate(key.last_used_at)}
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
