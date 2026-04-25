import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layout } from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingState, ErrorState } from "@/components/DataStates";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import {
  organizationsApi,
  type MemberResponse,
} from "@/api/organizations";
import type { MemberRole } from "@/types/auth";
import { ApiError } from "@/api/client";
import { Users, UserPlus, Trash2 } from "lucide-react";
import { motion } from "framer-motion";

const ROLE_OPTIONS: { value: MemberRole; label: string; hint: string }[] = [
  { value: "admin", label: "Admin", hint: "Full access incl. billing + members" },
  { value: "editor", label: "Editor", hint: "Create and edit deals, memos" },
  { value: "viewer", label: "Viewer", hint: "Read-only" },
];

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function roleBadgeClass(role: MemberRole): string {
  switch (role) {
    case "admin":
      return "bg-primary/10 text-primary";
    case "editor":
      return "bg-accent/10 text-accent-foreground";
    default:
      return "bg-muted text-muted-foreground";
  }
}

export default function Team() {
  const { organizationId, role: myRole, user } = useAuth();
  const orgId = organizationId ?? "";
  const isAdmin = myRole === "admin";
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<MemberRole>("editor");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["org-members", orgId],
    queryFn: () => organizationsApi.listMembers(orgId),
    enabled: !!orgId,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["org-members", orgId] });

  const inviteMutation = useMutation({
    mutationFn: () =>
      organizationsApi.invite(orgId, {
        email: inviteEmail.trim(),
        role: inviteRole,
      }),
    onSuccess: (member) => {
      toast({
        title: "Member added",
        description: `${member.email} joined as ${member.role}.`,
      });
      setInviteEmail("");
      setInviteRole("editor");
      invalidate();
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError ? err.message : "Failed to invite member";
      toast({
        title: "Invite failed",
        description: msg,
        variant: "destructive",
      });
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: MemberRole }) =>
      organizationsApi.updateRole(orgId, userId, { role }),
    onSuccess: () => {
      toast({ title: "Role updated" });
      invalidate();
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError ? err.message : "Failed to update role";
      toast({
        title: "Update failed",
        description: msg,
        variant: "destructive",
      });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => organizationsApi.remove(orgId, userId),
    onSuccess: () => {
      toast({ title: "Member removed" });
      invalidate();
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError ? err.message : "Failed to remove member";
      toast({
        title: "Remove failed",
        description: msg,
        variant: "destructive",
      });
    },
  });

  const handleInvite = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    inviteMutation.mutate();
  };

  const handleRemove = (member: MemberResponse) => {
    // Minimal confirm — no need for a whole dialog component for MVP.
    if (
      !window.confirm(
        `Remove ${member.email} from the organization? This cannot be undone.`,
      )
    ) {
      return;
    }
    removeMutation.mutate(member.user_id);
  };

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-5 md:space-y-6 max-w-[1100px] mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-lg md:text-xl font-semibold font-display">
              Team
            </h2>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isAdmin
              ? "Invite teammates and manage their roles."
              : "Everyone on your workspace. Only admins can add or remove members."}
          </p>
        </motion.div>

        {isAdmin && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <UserPlus className="h-4 w-4" />
                Add a teammate
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={handleInvite}
                className="grid grid-cols-1 md:grid-cols-[1fr_200px_auto] gap-3"
              >
                <div className="space-y-1.5">
                  <Label htmlFor="invite_email">Email</Label>
                  <Input
                    id="invite_email"
                    type="email"
                    required
                    placeholder="teammate@company.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="invite_role">Role</Label>
                  <Select
                    value={inviteRole}
                    onValueChange={(v) => setInviteRole(v as MemberRole)}
                  >
                    <SelectTrigger id="invite_role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end">
                  <Button
                    type="submit"
                    disabled={inviteMutation.isPending || !inviteEmail.trim()}
                  >
                    {inviteMutation.isPending ? "Adding…" : "Add member"}
                  </Button>
                </div>
              </form>
              <p className="text-xs text-muted-foreground mt-3">
                The teammate must already have a DealSignal account with this
                email. Ask them to register first if they haven't yet.
              </p>
            </CardContent>
          </Card>
        )}

        {isLoading ? (
          <LoadingState message="Loading team…" />
        ) : error ? (
          <ErrorState
            message="Failed to load team members."
            onRetry={() => refetch()}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {(data?.length ?? 0) === 1
                  ? "1 member"
                  : `${data?.length ?? 0} members`}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="text-left p-3 font-medium">Name</th>
                      <th className="text-left p-3 font-medium">Email</th>
                      <th className="text-left p-3 font-medium">Role</th>
                      <th className="text-left p-3 font-medium">Joined</th>
                      {isAdmin && (
                        <th className="text-right p-3 font-medium">Actions</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {data?.map((m) => {
                      const isSelf = m.user_id === user?.id;
                      return (
                        <tr
                          key={m.id}
                          className="border-t align-middle hover:bg-muted/20"
                        >
                          <td className="p-3">
                            <div className="font-medium">
                              {m.full_name}
                              {isSelf && (
                                <span className="ml-2 text-xs text-muted-foreground">
                                  (you)
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-3 text-muted-foreground">
                            {m.email}
                          </td>
                          <td className="p-3">
                            {isAdmin && !isSelf ? (
                              <Select
                                value={m.role}
                                onValueChange={(v) =>
                                  roleMutation.mutate({
                                    userId: m.user_id,
                                    role: v as MemberRole,
                                  })
                                }
                                disabled={roleMutation.isPending}
                              >
                                <SelectTrigger className="h-8 w-[120px]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {ROLE_OPTIONS.map((o) => (
                                    <SelectItem key={o.value} value={o.value}>
                                      {o.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <span
                                className={`px-2 py-0.5 rounded text-xs capitalize ${roleBadgeClass(m.role)}`}
                              >
                                {m.role}
                              </span>
                            )}
                          </td>
                          <td className="p-3 text-muted-foreground whitespace-nowrap">
                            {formatDate(m.joined_at)}
                          </td>
                          {isAdmin && (
                            <td className="p-3 text-right">
                              {!isSelf && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRemove(m)}
                                  disabled={removeMutation.isPending}
                                  aria-label={`Remove ${m.email}`}
                                >
                                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                                </Button>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
