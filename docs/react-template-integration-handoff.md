# React/template integration handoff

## Implemented

- Branch: `feat/react-template-integration`, based on merged VA-DAT main
  `a8066d73`; the unmerged asynchronous crawling PR was not included.
- C4G/template `1589fc95` imported into `web/`. Its pnpm lockfile is unchanged.
  The Python dependency lockfile and pipeline behavior are unchanged.
- Public React project page at `/` and separate tool at `/audit`, with HTML paste/upload, single/nested URL
  modes, request-scoped provider keys, progress streaming,
  expandable details, page trees, and CSV downloads.
- Template authentication and an ADMIN-only `/admin/models` page/API, backed by
  PostgreSQL. Registration cannot choose privileged roles. An operator can
  promote an existing account using the documented command.
- Public model options come from saved configuration. Audit proxy requests are
  checked server-side; disabled/unknown models cannot bypass the dropdown.
- Internal Python `/health`; static repository-file serving removed. The old
  root HTML/CSS remain historical references, not an active frontend.
- Production Compose for Next.js, Python, and PostgreSQL 17, plus verified
  backup and migration jobs. Development overlays expose localhost ports only.
- CI and publication workflows for both application images, using matching
  commit tags and triggering Coolify only after tests and both publications.

The public UI now follows the original VA-DAT design, not the template theme.
The frontend-design skill was used for fidelity: original DM fonts (self-hosted
with their licenses), scoped original content CSS/footer, input tabs,
upload area, collapsed HTML paste field, provider/model row, progress bar,
summary cards, findings table, LLM accordions, and CSV/feedback buttons.
One shared original-style P5 navbar appears on every route, with sign-in/sign-up buttons, account access
and administrator links. `/` renders the project sections and `/audit` renders
only the audit tool; no hidden project/audit panels or hash-driven tab state
remain. Next.js links handle navigation, including home section anchors.
Team and Lighthouse link to `/#team` and `/#lighthouse`. The duplicate `/team`
pages and empty course placeholders were removed; old URLs redirect to the
corresponding home sections. Original project content remains in place.
Account/admin pages retain template authentication and components but are
light-only, including portalled dialogs and the users grid. Saved dark/system
preferences cannot override light mode, and the theme toggle was removed. Backend and
Compose behavior are unchanged by this visual restoration. Extra search and
summary controls from the first migration were removed to match the original.
Keyboard controls, live announcements, safe text rendering and result focus
remain. On narrow screens the tabs wrap instead of reproducing the original
horizontal overflow. The project Lighthouse content reports historical scores,
not measurements of this React build.

## Verification performed locally

| Check | Result |
| --- | --- |
| Web tests | 94 passing, including 50 inherited template tests |
| TypeScript, ESLint, Prettier | Passing |
| Python API regression | 3 passing tests |
| Locked Python dependencies/export | Lock check passes; generated requirements unchanged |
| Pipeline fixture dry run | 14 programmatic findings, 10 generated prompts, no LLM calls |
| Production Dockerfiles | Both application images build successfully |
| Fresh Compose initialization | Database, verified backup, migrations, API and web start successfully |
| Real authentication | Signup, forged-role rejection, non-admin rejection, promotion, and admin login pass |
| Model restrictions | Public list, saved settings, invalid/disabled model rejection and same-origin checks pass |
| Persistence | Settings survive web restart and full-stack recreation, including PostgreSQL; original settings restored |
| Startup failure safeguards | Deliberately failed backup and migration each prevent web startup |
| Isolation | Python/PostgreSQL have no host port bindings; Python image excludes `web/` and `.env` |
| Streaming | Early progress, fragmented Unicode/NDJSON, JSON fallback, missing results, connection errors and cancellation tested |
| Chromium desktop/mobile | Original audit content geometry matches below the shared navbar; home/audit navigation and Team/Lighthouse anchors, mobile, upload/remove, key visibility, mocked URL results, safe output and CSV download pass; auth stays light with dark OS/saved preferences; old course URLs redirect; no page errors |

The container/authentication checks above were completed before the visual
restoration. After restoration and shared-navigation changes, the 94 tests, type checking, lint, formatting,
production Next.js build and mocked browser checks were rerun. No live Coolify
check has been performed.

### Repeat the visual comparison

Start the local frontend (`cd web && pnpm dev --port 3318`), then run
`UI_URL=http://localhost:3318 node scripts/check-original-ui.mjs` from the repo
root with Playwright/Chromium available. If Playwright is installed separately,
set `PLAYWRIGHT_MODULE` to its absolute `index.mjs` path. The script serves only
the original reference HTML/CSS on an ephemeral localhost port, mocks all APIs,
checks desktop audit geometry (excluding the intentionally changed navbar), separate routes and mobile interactions, and writes comparison
screenshots to a printed temporary directory. No database or paid keys needed.

Browser checks used an isolated Playwright download and a temporary extracted
audio library because the host lacked Chromium's audio dependency. No system
package or application dependency was changed for those checks.

No paid provider calls, live deployment, GitHub push, or commit was performed.
The original untracked supervisor discussion document was preserved.
The local `vadat-integration` test containers were stopped after verification;
their named database/backup volumes are retained for inspection. Failure-test
stacks and their disposable volumes were removed by the test harness.

The secret-free Docker build succeeds but the inherited Better Auth module
emits missing-origin/default-secret diagnostics while Next.js collects route
metadata. Real runtime credentials are required by Compose and were exercised
in the authentication smoke tests. Google also warns when its optional client
credentials are unset; email/password authentication remains available.

## Justin's remaining deployment checks

Follow [DEPLOY.md](../DEPLOY.md). In particular:

1. Configure a Git-backed Compose resource instead of the old single-image
   resource, with the repository's backup script available as a Compose config.
2. Set secrets/public origin, assign a domain only to `web:3000`, and verify
   both GHCR images are accessible. Point the deployment UUID at this resource.
3. Verify backup and migration jobs rerun on every deployment and volumes retain
   their identities. Pin matching image tags for controlled promotion.
4. Inspect actual proxy buffering and timeout settings. Validate delayed
   streaming through staging, not just directly against a local container.
5. Verify production TLS, Google callbacks if enabled, and passkeys for the real
   hostname. Promote the intended administrator; there are no seeded demo users.
6. Arrange off-host backups and a restore drill. Same-host dumps do not protect
   against server loss; application rollback does not undo database migrations.

The catalog preserves existing model IDs; availability of every model at its
provider was not tested. Synchronous Python processing may briefly continue
after the browser stops waiting. These are documented boundaries, not claims
of live-provider or live-Coolify verification.
