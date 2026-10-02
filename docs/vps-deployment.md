# Signatlas VPS deployment

This deployment coexists with the host's Nginx. Unlike `deploy.sh`, it does not
bind containers to public ports 80/443. Use `compose.vps.yml` exclusively for this
installation; do not run the original Compose stack alongside it.

## Layout

- Checkout: `/home/ubuntu/signatlas`
- Configuration: `/home/ubuntu/signatlas/.env.production` (mode 0600, never committed)
- Session files: `/home/ubuntu/signatlas-data/sessions`
- PostgreSQL 16: private Compose network, persistent `signatlas_postgres_data` volume
- Web/API: loopback ports 18880/18787, exposed through host Nginx and HTTPS
- Release state and backups: `.deploy/`

The initial environment uses Clerk development credentials and Creem test mode.
Production login/payment credentials and a real browser payment-flow acceptance
test are required before commercial launch. Configure the Creem webhook endpoint
as `https://api.signatlas.app/webhooks/creem` in the matching Creem environment.

## First install

Install Docker with Compose, Nginx, Certbot with its Nginx plugin, Git, curl and
Python 3. Clone `https://github.com/watchingthewheelsgo/vedic.git` to the checkout.
Create `.env.production` from the production example and set:

```dotenv
SITE_DOMAIN=signatlas.app
API_DOMAIN=api.signatlas.app
VITE_API_BASE_URL=https://api.signatlas.app/v1
ALLOWED_ORIGINS=https://signatlas.app
CREEM_SUCCESS_URL=https://signatlas.app/account?billing=success
DATABASE_URL=postgresql://signatlas:REPLACE_WITH_RANDOM_PASSWORD@db:5432/signatlas?sslmode=disable
POSTGRES_PASSWORD=REPLACE_WITH_SAME_RANDOM_PASSWORD
DATABASE_SCHEMA_MODE=migrations
SESSION_DATA_DIR=/home/ubuntu/signatlas-data/sessions
BACKUP_DIR=/home/ubuntu/signatlas/.deploy/backups
VEDICSIGN_UID=1000
VEDICSIGN_GID=1000
```

The SSL override is only for this unexposed, same-host Docker database. Keep TLS
enabled when using an external database provider.

Set the actual Clerk and agent credentials, `APP_ENV=production`,
`VEDIC_AUTH_MODE=clerk`, `RELOAD=false`, and `CREEM_TEST_MODE=true` for staging.
Create the session directory owned by the configured UID/GID. Install
`deploy/nginx-signatlas.conf` as a **new** Nginx site, test with `nginx -t`, then
reload Nginx. Obtain a certificate for the root, API and www domains using
Certbot's Nginx plugin once DNS resolves to this host. Configure www to redirect
to the root domain after issuance. Do not overwrite existing sites or TLS config.

## Update from GitHub and deploy

```sh
ssh ubuntu@43.163.197.166 'cd /home/ubuntu/signatlas && bash scripts/production/update-vps.sh'
```

The script refuses dirty checkouts, fetches and fast-forwards `origin/main`,
validates config, builds images sequentially, backs up PostgreSQL and session
artifacts, applies forward migrations and checks container/local HTTP health,
public HTTPS and CORS. It uses noninteractive sudo for Docker if necessary.
It retains the previous application image and attempts automatic application
rollback on startup/health failure. Git's source revision remains at the new
commit on a failed release; `.deploy/vps-current` tracks the running image.

Manual application rollback (does not downgrade database schema):

```sh
bash scripts/production/update-vps.sh --rollback
```

For a schema-breaking migration, assess compatibility before deployment. Restoring
a database dump is a separate maintenance operation; never blindly restore over
new user data. Backups are local to this VPS; copy them off-host for disaster
recovery. Report jobs may be interrupted by container replacement, so use a quiet
maintenance window for updates.

## Verification and logs

```sh
curl -f https://signatlas.app/
curl -f https://api.signatlas.app/health
curl -i -X OPTIONS https://api.signatlas.app/v1/me \
  -H 'Origin: https://signatlas.app' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-vedic-anonymous-id'
sudo env VEDICSIGN_IMAGE_TAG="$(cat .deploy/vps-current)" \
  docker compose --env-file .env.production -f compose.vps.yml logs --tail 100
```

Also verify signed-in access, report calculation, report completion, PDF export,
and a Creem test checkout/webhook. Passing health checks alone does not prove
these external integrations. Certificate renewal uses the host Certbot timer.
