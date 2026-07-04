# RBAC Audit — API Routes

Production reference for how role guards are (and aren't) applied across `app/routes/`. Read this before adding a new endpoint.

## Roles

`MemberRole` enum values:

- **admin** — full control, including org membership management.
- **editor** — create/update/delete on tenant data (deals, contacts, memos, etc.).
- **viewer** — **does not exist in the codebase.** Any authenticated org member effectively has read access; there is no lower-privilege read-only tier. "Viewer" columns below are shown for completeness but always mirror `editor` on reads.

## Two layers of enforcement

DealSignal enforces auth at two layers, and both matter when reading the matrix below:

1. **Global auth posture** (`AuthContextMiddleware` + `ALLOW_ANONYMOUS`).
   In production (`ALLOW_ANONYMOUS=False`, refused-to-boot-otherwise), every non-public path returns 401 without a valid Bearer token. This alone protects endpoints that lack an explicit auth `Depends`.
2. **Route-level guards** (`Depends(require_role(...))` on the decorator, or `Depends(get_current_user)`).
   These make the requirement explicit and inspectable via `route.dependencies`. Preferred over relying on the global posture, because a config drift (e.g. accidentally shipping with `ALLOW_ANONYMOUS=True`) becomes a data-exposure incident on any endpoint without a route-level guard.

## Guard convention

Intended pattern for mutations:

```python
@router.post(..., dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))])
```

Reads generally have no `require_role(...)` — org isolation is enforced by `active_query()` / `scope_query()` reading `org_id` off `AuthContext`. A handful of endpoints (audit, org membership, org export) enforce roles by calling `_require_admin(...)` inside the handler body instead. That still works, but it's harder to audit and easier to regress — prefer `Depends`.

## Role matrix

Legend: A = admin, E = editor, V = viewer (n/a — treat as E for reads). `Y` = allowed, `—` = denied, `Auth` = any authenticated org member, `Public` = no auth.

### Auth / session (`auth.py`, `twofa.py`, `password_reset.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| POST | /auth/register | Public | Public | Public | IP rate-limited |
| POST | /auth/login | Public | Public | Public | IP + per-account lockout, optional TOTP |
| POST | /auth/refresh | Public | Public | Public | httpOnly cookie, `token_version` check |
| POST | /auth/logout | Public | Public | Public | Idempotent cookie clear |
| POST | /auth/logout-all | Auth | Auth | Auth | Bumps caller's `token_version` |
| GET | /auth/me | Auth | Auth | Auth | Self-lookup |
| POST | /auth/switch-org | Auth | Auth | Auth | Manual membership check; rotates refresh cookie |
| POST | /auth/2fa/setup | Auth | Auth | Auth | Self-enroll |
| POST | /auth/2fa/verify | Auth | Auth | Auth | Self |
| POST | /auth/2fa/disable | Auth | Auth | Auth | Re-verifies password + TOTP in handler |
| POST | /auth/password/forgot | Public | Public | Public | Constant 204, IP + email rate limits |
| POST | /auth/password/reset | Public | Public | Public | Single-use hashed token; bumps `token_version` |

### Organizations & members (`organizations.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /organizations/me | Auth | Auth | Auth | Own memberships |
| GET | /organizations/{org_id}/members | Auth | Auth | Auth | Manual `_ensure_membership()` |
| POST | /organizations/{org_id}/members | Y | — | — | `Depends(require_role_of(admin))` |
| PATCH | /organizations/{org_id}/members/{user_id} | Y | — | — | `Depends(require_role_of(admin))` |
| DELETE | /organizations/{org_id}/members/{user_id} | Y | — | — | `Depends(require_role_of(admin))` |

### Deals (`deals.py`, `deal_summary.py`, `pipeline.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /deals | Auth | Auth | Auth | `active_query` scope |
| POST | /deals | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id} | Auth | Auth | Auth | |
| PATCH | /deals/{deal_id} | Y | Y | — | Decorator guard |
| DELETE | /deals/{deal_id} | Y | Y | — | Soft-delete; consider admin-only |
| POST | /deals/import | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/summary | Auth | Auth | Auth | No route-level auth `Depends`; relies on global posture |
| POST | /deals/{deal_id}/move-stage | Y | Y | — | Decorator guard |

### Deal intelligence (`deal_intelligence.py`, `assumptions.py`, `memos.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| POST | /deals/{deal_id}/enrich | Y | Y | — | Decorator guard |
| POST | /deals/{deal_id}/score | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/assumptions | Auth | Auth | Auth | |
| PUT | /deals/{deal_id}/assumptions | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/outputs | Auth | Auth | Auth | |
| POST | /deals/{deal_id}/recalculate | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/memo | Auth | Auth | Auth | |
| POST | /deals/{deal_id}/generate-memo | Y | Y | — | Decorator guard |
| PUT | /deals/{deal_id}/memo | Y | Y | — | Decorator guard |
| DELETE | /deals/{deal_id}/memo | Y | Y | — | Editor can delete — confirm intended vs. admin-only |

### Contacts, activities, documents, distributions

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /deals/{deal_id}/contacts | Auth | Auth | Auth | |
| POST | /deals/{deal_id}/contacts | Y | Y | — | Decorator guard |
| PATCH | /contacts/{contact_id} | Y | Y | — | Decorator guard |
| DELETE | /contacts/{contact_id} | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/activities | Auth | Auth | Auth | |
| POST | /deals/{deal_id}/activities | Y | Y | — | Decorator guard |
| GET | /outreach/follow-ups | Auth | Auth | Auth | Org scope via `active_query` only |
| GET | /deals/{deal_id}/documents | Auth | Auth | Auth | |
| POST | /deals/{deal_id}/documents | Y | Y | — | Decorator guard |
| DELETE | /documents/{document_id} | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/distributions | Auth | Auth | Auth | No route-level auth `Depends`; relies on global posture |
| POST | /deals/{deal_id}/send | Y | Y | — | Decorator guard |

### Buy box, signals (`buy_box.py`, `signals.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /buy-box | Auth | Auth | Auth | |
| POST | /buy-box | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/match-buy-boxes | Auth | Auth | Auth | |
| GET | /signals | Auth | Auth | Auth | |
| POST | /signals | Y | Y | — | Decorator guard |
| GET | /deals/{deal_id}/signals | Auth | Auth | Auth | |

### Audit & data portability (`audit.py`, `data_portability.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /audit | Y | — | — | `Depends(require_role_strict(admin))` |
| GET | /audit/export | Y | — | — | `Depends(require_role_strict(admin))`; still writes an audit row + commits on a GET — see gap 2 |
| GET | /organizations/{org_id}/export | Y | — | — | `Depends(require_role_of(admin, must_match_active_org=True))` |

### Dashboard (`dashboard.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /dashboard/kpis | Auth | Auth | Auth | No route-level auth `Depends`; protected in prod only by global posture |
| GET | /dashboard/top-opportunities | Auth | Auth | Auth | Same as above |
| GET | /dashboard/pipeline-snapshot | Auth | Auth | Auth | Same as above |
| GET | /dashboard/recent-signals | Auth | Auth | Auth | Same as above |
| GET | /dashboard/ai-insights | Auth | Auth | Auth | Same as above |

### Health (`health.py`)

| Method | Path | A | E | V | Notes |
|---|---|---|---|---|---|
| GET | /health | Public | Public | Public | Intentional |

## Gaps

Ranked by severity. Items marked ✅ were addressed in the same PR that added this doc.

1. ✅ **Explicit route-level auth guards on tenant reads that only rely on the global posture.** `dashboard.py` (all 5 endpoints), `deal_summary.py` `GET /summary`, and `distributions.py` `GET /distributions` now declare `Depends(require_role(admin, editor))` — matches the mutation convention and survives a middleware refactor.
2. **`GET /audit/export` mutates on a GET.** Writes an audit-log row and commits inside a GET handler. Change to POST or move the side effect. Cache-safety and idempotency assumptions elsewhere in the stack (browsers, CDNs, retries) don't apply to state-changing GETs. Deferred — coordinate with the frontend before the API change.
3. ✅ **In-handler role checks converted to `Depends(...)` guards.** All role enforcement now lives on the route signature and is inspectable via `route.dependencies`:
   - `GET /audit`, `GET /audit/export` — `Depends(require_role_strict(admin))`.
   - `POST /organizations/{org_id}/members`, `PATCH /organizations/{org_id}/members/{user_id}`, `DELETE /organizations/{org_id}/members/{user_id}` — `Depends(require_role_of(admin))`. Path-scoped: checks membership + role of the *path* org id.
   - `GET /organizations/{org_id}/export` — `Depends(require_role_of(admin, must_match_active_org=True))`. Same factory, stricter mode: the path org must also equal the caller's active org (matches the GDPR posture — admins can't cross-export using a token signed for a different org).
   - `require_role_of` factory lives in `app/utils/auth_deps.py`. Use it for any admin-scoped endpoint where the org id comes from the URL, not the JWT.
4. **Editor can perform destructive deletes.** Confirm intent for:
   - `DELETE /deals/{deal_id}` (soft-delete)
   - `DELETE /deals/{deal_id}/memo`
   - `DELETE /documents/{document_id}`
   - `DELETE /contacts/{contact_id}`
   If policy is "destructive ops = admin only," tighten these to `require_role(MemberRole.admin)`.
5. **No `viewer` role exists.** Every authenticated org member can read every tenant-scoped endpoint. If read-only members are ever needed (auditors, guest investors), add `MemberRole.viewer` to the enum + migration and add it as an allowed role on all `GET` endpoints via `require_role`.

## Checklist for a new endpoint

1. **Auth**: Add `Depends(get_current_user)` unless the route is genuinely public. Don't rely on the global posture — make the requirement explicit.
2. **Org scoping**: All queries go through `active_query(db.query(Model), Model)` or `scope_query(...)`. Never raw `db.query(Model).filter(Model.id == x)` without an `org_id` filter.
3. **Role guard on mutations**: Use `dependencies=[Depends(require_role(MemberRole.admin, MemberRole.editor))]` on the decorator. Do not put role checks in the handler body.
4. **Admin-only ops**: Use `Depends(require_role(MemberRole.admin))` at the decorator. If you find yourself calling `_require_admin(...)` inside a handler, use the dependency instead.
5. **Destructive ops (DELETE, exports, member changes)**: default to admin-only unless there's an explicit product reason to allow editors.
6. **GETs don't mutate.** No `db.commit()` inside a GET handler.
7. **Public endpoints** must be rate-limited via `limiter.check` and should return constant responses when they touch account state (avoid enumeration).
