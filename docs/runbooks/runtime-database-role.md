# Runtime Database Role

## Boundary

Application runtime must not use the administrative migration credential. A
matching tenant policy and enabled/FORCE flags are not enough: check
`pg_catalog.row_security_active` and actual foreign-row denial in the effective
runtime connection. Managed-provider administrative privileges can invalidate
assumptions based only on `rolsuper` and `rolbypassrls`.

The November 11 SF preflight found this gate failing on the old credential.
The user separately authorized scoped database-role remediation and staged
API/worker configuration changes. No schema migration or paid upgrade is included.

## Privileges

The restricted runtime login has no superuser, bypass-RLS, create-database,
create-role, replication, inheritance, administrative membership or table
ownership. It receives CONNECT, public-schema USAGE, CRUD on application model
tables, sequence USAGE/SELECT and read-only migration-version inspection.
No public-schema CREATE privilege is accepted. Extension/migration metadata
does not receive runtime write grants. Public function privileges and application
authorization remain separate concerns; this is not a claim that SQL injection
or all possible database privilege paths are impossible.

Future migrations stay on the separate administrative credential. Review grants
for new tables/sequences after each migration; there is no runtime DDL fallback.
Authentication deliberately uses global identity tables and bootstrap audit
policy behavior. Do not claim every table is universally default-deny, or grant
administrative membership to make a failing application path work.

## Managed Credential And Workers

Use the encrypted Standard SSM parameter referenced by the reviewed provisioner
constant. Preserve the existing Secrets Manager administrative value for explicit
migration operations; never overwrite it or put credentials in Git, shell
arguments, receipts or logs. Existing AWS-managed encryption is used; no custom
KMS key, parameter-tier or paid-service upgrade is required.

API instance and ECS execution roles receive read permission for exactly this
parameter. Once API cutover is accepted, remove its instance role's access to
the old administrative database secret, retaining unrelated application secrets.
The ECS execution role still serves separate migration tasks; it is not a task
role handed to ingestion application code. Verify task-role assignments rather
than assuming this separation.

Both recurring provisioners clone the migration base only for existing execution
settings. A shared deep-copy helper replaces exactly one managed DATABASE_URL
reference with the reviewed runtime parameter before mutations. Missing/duplicate
references or plaintext DATABASE_URL environment entries fail closed. Other
secrets/settings and the original migration definition stay unchanged.

## Staged Acceptance

1. Provision the login and grants without changing schemas or tenant rows.
2. Check effective RLS, own-scope positive controls, foreign-row denial and
   empty/unset-scope denial using the candidate credential, read-only.
3. Change the API credential only, preserving the old image/settings. Verify
   deployment completion, database health, actual authenticated reads and demo.
4. Clone existing worker revisions changing only DATABASE_URL. Add IAM RunTask
   grants before updating scheduler targets; preserve existing grants, images,
   commands, times, retry policies, networks and states. Never recreate sources.
5. Verify registered references and actual worker execution separately. A changed
   schedule is not proof that a subsequent daily invocation succeeded. Running
   processes keep their old credential until they exit; do not silently kill them.
6. Remove obsolete API administrative-secret read access after cutover acceptance.
   Preserve the migration credential and explicit rollback receipts.

For feature rollback, keep the restricted runtime credential while restoring the
previous image or disabling the feature flag. Do not silently restore known
administrative bypass privileges. Permission failures require investigation, not
RLS weakening. The SF bounded-backfill and map receipts are in
`docs/sf-derived-locations.md`; source schedules remain independent.

## Current Receipt

Restricted-role provisioning task `df035cda62864476af7743e38fd41df7` exited0:
71 application model tables granted, zero schema changes/row writes, no admin
membership/ownership, effective-RLS default-deny geocode check passed.
Restricted read-only SF task `1f8a8a42e97246a5b736533fab16c050` exited0:
6,711 source rows readable, foreign geocodes0, baseline native/derived0.
All23 existing schedule targets were revised credential-only; all remain enabled.
API credential-only operation `f7baa815ec414fa6a3a9c958e3d31d9e` is still pending
at this checkpoint. Final API acceptance, administrative-secret policy removal
and actual post-change scheduled-worker receipts must be recorded before calling
the complete runtime remediation accepted.

Local provisioner regression suite19passed; combined provisioner/core/backfill
suite78passed. No live model calls, schema migrations, source activations or
paid-service upgrades were performed.
