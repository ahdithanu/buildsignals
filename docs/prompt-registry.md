# Prompt registry

The workspace-admin page at `/admin/prompts` manages versioned prompt text. The
corresponding strict-admin API is `/v1/prompts`. It offers template creation,
immutable revisions, exact-variable preview, activation, rollback to a prior
revision, and audit history.

## Model and boundaries

- `prompt_template` is tenant-scoped by `organization_id` and has a stable key,
  workflow label, and active version number.
- `prompt_version` contains body text, declared variables, a SHA-256 content
  checksum, author, and timestamps. Versions are append-only through the API;
  SQLite and PostgreSQL triggers prevent direct edits to content/identity
  columns. Activation changes only the active pointer and activation timestamp.
- Existing `audit_logs` record create, version-create, activation, and rollback
  actions. Audit entries store version/checksum, not prompt body or preview data.
- PostgreSQL row-level security and composite tenant foreign keys protect both
  tables. The API also filters every read by organization and requires a current
  admin membership, including in anonymous demo mode.

Placeholders use `{{variable_name}}`, with lowercase identifiers declared
exactly once. Preview requires a value for each variable and performs one
literal substitution pass. It does not evaluate code, call a model, or save the
values. Do not put secrets or personal data in prompt bodies or preview values.

**Activation is registry metadata only.** The installed memo and score workflows
are deterministic code paths and do not read these templates. Copilot and
multi-agent evaluation flows currently accept captured outputs; they do not
execute the selected prompt. An eval `prompt_version` label is supplied by the
caller and is not cryptographic proof that a particular prompt body produced an
output. Therefore publication is not described as an automated quality gate.

## Adding a real consumer

An AI workflow should load the active version by `(organization_id, key)`, pin
its version ID and checksum for the entire run, validate its inputs against
declared variables, and persist that identity with the output. It should fail
closed if no active version exists. Add a measured live eval harness that runs
the pinned version against evidence cases before allowing automatic promotion.
Until then, activation is an administrative selection, not a runtime rollout.

## Scaling

Queries are by tenant/key or tenant/template/version and use unique/composite
indexes. Template counts are bounded to 200 per workspace and 200 versions per
template in this first admin UI; this avoids unbounded history payloads. At
larger scale, paginate listings and audit history and move preview evaluation
to a dedicated sandbox, while retaining immutable version IDs and tenant keys.
The number of opportunities does not affect registry query cost.
