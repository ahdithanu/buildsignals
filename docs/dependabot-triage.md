# Dependabot triage process

Dependabot opens weekly PRs for pip, npm, and GitHub Actions (see
`.github/dependabot.yml`). Goal: keep the backlog at zero open PRs older
than 2 weeks.

---

## Weekly triage (15 min)

1. Open GitHub → Pull requests → filter `label:deps`.
2. For each PR:
   - **Patch bumps (grouped):** merge if CI green. Frontend PRs need
     `frontend.yml` + `e2e.yml` if `package-lock.json` changed.
   - **Minor/major bumps:** read changelog; run locally if touching auth,
     SQLAlchemy, FastAPI, or React.
   - **Conflicts:** rebase on `main` and re-run CI.
3. Close stale PRs superseded by a newer bump to the same package.

---

## Merge order

1. Backend (pip) — usually independent.
2. GitHub Actions — low risk.
3. Frontend (npm) — may need lockfile conflict resolution.

Never merge multiple major frontend bumps in one deploy without testing E2E.

---

## When to defer

| Signal | Action |
|--------|--------|
| CI red on unrelated flake | Re-run; don't merge until green |
| Major version with breaking API | Create ticket; pin version temporarily |
| Security advisory (pip-audit fails) | Priority merge or explicit `--ignore-vuln` with comment in CI |

---

## Automation

- `pip-audit --strict` in CI blocks known CVEs.
- Dependabot security alerts appear separately — treat as Sev-2 if exploitable
  in production code path.

Track status in [enterprise_readiness.md](enterprise_readiness.md) (B8).
