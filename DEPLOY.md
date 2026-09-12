# VA-DAT deployment and local development

The website is a Next.js/React application in `web/`, based on
[C4G/template at 1589fc95](https://github.com/C4G/template/tree/1589fc95324a0b4b1af97cfa72c7fe7045341de3).
The existing Python pipeline remains an internal HTTP service. This changes the
deployment from the old single-image resource to a **Git-backed Docker Compose
resource**. Do not point the old single-image Coolify resource at the web image
without first configuring the complete stack.

## Services and persistence

| Service | Purpose | Exposure |
| --- | --- | --- |
| `web` | React, Better Auth, administrator configuration, audit proxy | Coolify domain → port 3000 |
| `api` | Python auditing and NDJSON progress | Internal port 8000 only |
| `db` | PostgreSQL 17 | Internal port 5432 only |
| `backup` | Verified PostgreSQL dump before migrations | Exits on completion |
| `migrations` | Prisma migration CLI from the web image | Exits on completion |

Startup is `db healthy → backup successful → migrations successful → web`.
Web also waits for API health. An exited backup/migration container is normal
when its exit code is zero. A required failure blocks web startup.

Compose creates a network with service-name DNS. Do not mark it `internal: true`:
Python requires outbound access to websites and LLM providers. No production
service has a published host port. Do not assign domains to `api` or `db`.

Named volumes `db-data` and `backups` are scoped to the Compose project. Keep
the project/resource identity stable across deploys. PostgreSQL data survives
container recreation; Python audit artifacts are temporary and not persisted.

## Local full-stack development

Requirements: Docker with Compose v2. Host development additionally needs
Node 24, pnpm 10.29.2, and uv.

1. Copy `example.env` to `.env` and fill `DATABASE_PASSWORD` and `AUTH_SECRET`.
   Generate each independently with `openssl rand -hex 32`. Use a URL-safe
   database password because Compose embeds it in `DATABASE_URL`.
2. Build and start:

   ```sh
   docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d
   ```

3. Open `http://localhost:3000/audit`. Set both `WEB_PORT` and
   `BETTER_AUTH_URL` when using a different port.
4. Inspect status with `docker compose ps -a` and logs with
   `docker compose logs --tail 100 web api backup migrations`.
5. Stop with `docker compose down`. This preserves data. **Do not add `-v` or
   `--volumes` unless intentionally destroying that stack's database/backups.**

No provider API keys are passed into either application container, even if the
host `.env` has them. Do not add provider-key environment interpolation or an
`env_file` containing LLM credentials. Users enter request-scoped keys; a blank
key runs programmatic checks only in this deployment.

For hot reload, start the database with:

```sh
docker compose -f docker-compose.yml -f docker-compose.local-db.yml up -d db
```

Copy `web/example.env` to `web/.env`, using that local database's password.
Then run `pnpm install --frozen-lockfile`, `pnpm run init`, and `pnpm dev` from
`web/`. In another terminal run `uv run python entry_points/api_server.py`.
The standalone Python API retains environment-key fallback for CLI/local
compatibility: remove provider keys from its environment and root `.env` if
you want no-key requests to be guaranteed dry runs. Never aim development
migration commands at a deployed database.

## First administrator and model configuration

Register an account at `/signup`, or sign in through configured Google OAuth.
Registrations receive the template's non-admin `STAFF` role; there is no
STAFF-specific audit workflow. No demonstration users are seeded.

An operator with access to the stack promotes the intended existing account:

```sh
docker compose exec web node scripts/promote-admin.mjs person@example.org
```

The command fails if the account does not exist. Sign out and back in after
promotion. `/admin/models` permits enabling supported models and choosing an
enabled default. The public dropdown and proxy use the saved configuration.
At least one model must remain enabled. Redeployments do not reset choices.

The catalog is code-maintained in `web/src/lib/model-catalog.ts`; it preserves
the previous dropdown, not a promise that each provider currently offers every
listed model. Adding models requires checking Python provider compatibility
and updating the catalog. No API keys are stored in PostgreSQL.

## Coolify setup — operator action required

1. Configure a Git-backed Docker Compose application for this repository,
   using root `docker-compose.yml`. Do not use the local-build override.
   The repository must remain available for `scripts/backup.sh`, mounted as a
   Compose config. No application build runs on the shared Coolify host.
2. Assign only `web` a domain, targeting port 3000. For example, Coolify's
   domain field may be `https://va-dat.c4g.dev:3000`; the public origin remains
   `https://va-dat.c4g.dev`, without the internal port.
3. Set `DATABASE_PASSWORD`, `AUTH_SECRET` (at least 32 random characters), and
   `BETTER_AUTH_URL` to the public origin. Leave `PYTHON_API_URL` as the Compose
   internal address. Set Google client credentials if Google sign-in is used;
   its callback is `<origin>/api/auth/callback/google`. Passkeys require HTTPS
   outside localhost and use the public hostname as their relying-party ID.
4. Keep `BACKUP_MODE=required`, `BACKUP_KEEP=10`, and the named volumes.
   `best-effort` and `off` are explicit operator escape hatches, not production
   defaults. Invalid modes or retention values fail startup.
5. Ensure both GHCR packages are accessible to Coolify. `IMAGE_TAG` selects
   matching web/API tags; pin a tested commit SHA for controlled deployment.
6. Disable independent git auto-deployment if using the publication workflow.
   Configure repository variable `COOLIFY_APP_UUID` for the **Compose** resource
   and secret `COOLIFY_TOKEN`. The workflow tests first, publishes both images,
   and only then triggers Coolify. It skips deployment if either value is absent.
7. Confirm each deployment reruns backup and migrations. With manual Compose,
   explicitly recreate completed jobs and dependent web when applying updates:

   ```sh
   docker compose pull
   docker compose up -d --force-recreate backup migrations api web
   ```

Never change PostgreSQL's initialized password just by changing its environment
variable: rotate the database role password and application connection settings
together. Optional template email/push functionality additionally needs its
Resend/VAPID settings; these are not required for public audits or email/password
login.

These network/domain conventions follow the
[Coolify Compose documentation](https://coolify.io/docs/knowledge-base/docker/compose).

## Streaming and proxy timeouts

Audit responses use `application/x-ndjson`, with progress lines and exactly one
final `type: result` line. Next.js forwards the response stream without collecting
it. Its Node upstream socket has a **600-second inactivity timeout**, reset by
traffic; there is no 600-second total audit deadline. Stopping the browser stream
closes the upstream connection, but synchronous Python work already running may
continue until the next write or provider call completes.

Justin must inspect the deployed proxy configuration, including any proxy/CDN
in front of Coolify:

- **Traefik:** do not attach a buffering middleware to audit traffic. Ensure
  the public entrypoint's `transport.respondingTimeouts.writeTimeout` is `0`
  (no total response deadline). Its `idleTimeout` concerns idle keep-alive
  connections, not the upstream response-body inactivity timer; the latter is
  enforced in Next.js. Do not change shared proxy settings without reviewing
  their effect on other applications.
- **Nginx, if present:** use `proxy_buffering off` and
  `proxy_read_timeout 600s` for audit API traffic. Do not cache these requests.
- Do not rely on `X-Accel-Buffering: no` alone; confirm the active proxy's actual
  configuration. See [Traefik timeout definitions](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/)
  and [Next.js self-hosting guidance](https://nextjs.org/docs/app/guides/self-hosting).

Use `curl -N` and the browser Network panel on staging to confirm progress arrives
before completion. A no-key HTML audit is a free smoke check; validate a delayed
mock response through the proxy for a meaningful buffering check. Live provider
tests require explicit authorization and the tester's own key.

## Backups, verification, and rollback

Backups are `pg_dump -Fc`, validated with `pg_restore --list`, then atomically
renamed and retained to `BACKUP_KEEP`. Partial dumps are removed. Dumps share the
database host: they protect against bad migrations, **not server/disk loss**.
Arrange off-host backups and a restore drill separately. Application image
rollback does not undo database migrations; verify schema compatibility before
pinning an older image or restoring a dump.

Automated checks:

```sh
uv run python -m unittest discover -s tests -v
uv run python entry_points/run_pipeline.py --html test_files/dat_visionaid_home.html --dry-run --output-dir ci-output
cd web
pnpm exec tsc --noEmit
pnpm lint
pnpm test
pnpm format
```

CI builds both containers, starts a fresh stack, exercises real authentication
and administrator promotion, tests a free audit, checks persistence on restart,
and verifies that backup/migration failures prevent web startup. The scripts
`scripts/smoke-test.mjs` and `scripts/test-startup.mjs` require
`SMOKE_ALLOW_MUTATION=1` and are **only for disposable test environments**.
The smoke test creates an account and temporarily changes model configuration.
With `SMOKE_RECREATE_STACK=1` (as in CI), it recreates the entire
`vadat-integration` stack without removing its volumes and verifies persistence;
this mode requires the same Compose environment variables used to start it.
The startup test removes only the uniquely named disposable stacks it creates.

Live Coolify configuration, OAuth provider callbacks, production TLS/passkeys,
off-host backups, and real provider access must be verified by the operator;
local container tests do not establish those deployment facts.
