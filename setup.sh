#!/usr/bin/env bash
#
# setup.sh — one-time install for the Docker stack.
#
#   ./setup.sh            generate .env if missing, build both images
#   ./setup.sh --reset    regenerate secrets and drop the database volume
#   VERBOSE=1 ./setup.sh  stream docker's raw output instead of summarising
#
# Idempotent: an existing .env is never overwritten, so hand-edited secrets
# survive a re-run. Run ./run.sh afterwards.

set -euo pipefail
cd "$(dirname "$0")"

# shellcheck source=docker/lib/shell.sh
source docker/lib/shell.sh

RESET=0
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    -h|--help)
      sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown option: $arg   (try --help)" ;;
  esac
done

banner "setup"

# --- preflight ---------------------------------------------------------------

section "Preflight"

dc_resolve
dc_daemon

ok "$(dc_version_line)"
ok "Daemon reachable"

if [ -t 0 ] && [ -t 1 ]; then
  bullet "interactive terminal $G_DOT live output on failures"
else
  bullet "non-interactive $G_DOT plain output, no colours"
fi

# --- environment -------------------------------------------------------------

section "Environment"

# Generate .env from .env.example. Idempotent by design — callers check first.
write_env() {
  [ -f .env.example ] || die ".env.example is missing from the repository."

  # Prefer openssl, fall back to python, then /dev/urandom — so this works on a
  # bare CI image as well as a developer machine.
  random_secret() {
    if command -v openssl >/dev/null 2>&1; then
      openssl rand -hex 32
    elif command -v python3 >/dev/null 2>&1; then
      python3 -c 'import secrets; print(secrets.token_hex(32))'
    else
      head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
    fi
  }

  local secret_key db_password
  secret_key=$(random_secret)
  db_password=$(random_secret)

  # Only the two placeholder lines are rewritten; anything edited in
  # .env.example survives.
  awk -v sk="$secret_key" -v pw="$db_password" '
    /^SECRET_KEY=/        { print "SECRET_KEY=" sk; next }
    /^POSTGRES_PASSWORD=/ { print "POSTGRES_PASSWORD=" pw; next }
    { print }
  ' .env.example > .env

  # DATABASE_URL embeds the DB password and the backend port is published on the
  # host, so the file must not be world-readable.
  chmod 600 .env
  ok ".env created $G_DOT generated SECRET_KEY and POSTGRES_PASSWORD"
}

if [ -f .env ]; then
  ok ".env present"
  if [ "$RESET" = 1 ]; then
    # Rotating POSTGRES_PASSWORD is only coherent if the volume that stored the
    # old one goes away with it. Postgres keeps the password it was initialised
    # with and ignores later changes, so regenerating .env alone would leave a
    # volume the new credentials can never open — which ./run.sh would then
    # (correctly) refuse to start against. Destroy the volume here so that
    # --reset always ends in a state that actually works.
    has_volume=0
    if dc_has_volume db-data; then
      has_volume=1
    fi

    warn "--reset regenerates secrets"
    dim "SECRET_KEY and POSTGRES_PASSWORD will be replaced $G_DOT existing"
    dim "sessions are invalidated and Cloudinary settings must be re-entered."
    if [ "$has_volume" = 1 ]; then
      dim ""
      warn "A database volume exists, and its data will be destroyed $G_DOT"
      dim "every worklog entry, user account and setting in PostgreSQL is lost."
    fi
    confirm "Replace .env${has_volume:+, and delete the database volume}?" "reset" \
      || die "aborted $G_DOT nothing was changed"

    # Tear down first. docker-compose.yml declares `env_file: .env`, so every
    # compose command fails outright once that file is gone — dropping the volume
    # has to happen while .env still exists.
    if [ "$has_volume" = 1 ]; then
      step "Removing containers and database volume" dc down -v --remove-orphans \
        || die "could not remove the database volume $G_DOT nothing was changed"
      ok "database volume removed $G_DOT it will be recreated empty on ./run.sh"
    fi

    # Stash rather than delete, so a failure mid-way is recoverable. Secrets
    # stay on disk at mode 600, never printed.
    cp .env ".env.bak.$(date +%s)"
    ok "previous .env saved alongside as .env.bak.*"
    rm -f .env
  else
    dim "left untouched $G_DOT re-running will not change your secrets"
  fi
elif [ "$RESET" = 1 ]; then
  dim "no .env to replace $G_DOT generating a fresh one"

  # Generated before the volume check, not after. dc_has_volume resolves the
  # Compose project through `docker compose config`, and compose.yml declares
  # `env_file: .env` — so with no .env that command fails, the project name comes
  # back empty and the check silently reports "no volume". Generating first is
  # what lets the check work, and .env has to be created on this path regardless.
  write_env

  # Postgres keeps the password it was initialised with, so a surviving volume
  # cannot be opened by the password just written to .env. --reset promises a
  # working state, so offer the same teardown rather than leaving a stack that
  # fails on the next ./run.sh.
  if dc_has_volume db-data; then
    warn "a database volume from a previous run exists"
    dim "Its stored password will not match the .env just generated, so the stack"
    dim "would not start. Deleting it loses every entry, user account and setting"
    dim "in PostgreSQL."
    confirm "Delete the database volume?" "reset" \
      || die "aborted $G_DOT .env was created but the volume was left in place"

    step "Removing containers and database volume" dc down -v --remove-orphans \
      || die "could not remove the database volume $G_DOT nothing was changed"
    ok "database volume removed $G_DOT it will be recreated empty on ./run.sh"
  fi
fi

if [ ! -f .env ]; then
  write_env
fi

chmod 600 .env 2>/dev/null || true
dim "mode $(stat -c '%a' .env 2>/dev/null || echo '?')"

# --- configuration warnings --------------------------------------------------
#
# These are reported but do not block: the stack is expected to boot with
# placeholders so a first run cannot fail on a missing optional key.

warn_found=0

if grep -q '^SECRET_KEY=replace_me' .env 2>/dev/null; then
  warn "SECRET_KEY is still the placeholder $G_DOT every session cookie is forgeable"
  dim  "fix: set SECRET_KEY=$( (command -v openssl >/dev/null && openssl rand -hex 32) || echo '<64 hex chars>')"
  warn_found=1
elif [ "$(awk -F= '/^SECRET_KEY=/{print length($2)}' .env)" -lt 32 ]; then
  warn "SECRET_KEY is shorter than 32 characters"
  warn_found=1
fi

if grep -q '^CLOUDINARY_API_SECRET=replace_me' .env 2>/dev/null; then
  warn "CLOUDINARY_* are placeholders $G_DOT the app will start but uploads will fail"
  dim  "app.py calls cloudinary.config() unguarded at import, so these three must"
  dim  "be set for anything that uploads a file to work"
  warn_found=1
fi

[ "$warn_found" = 0 ] && ok "no placeholder values detected in .env"

# A stale volume with a different POSTGRES_PASSWORD is a confusing failure: the
# backend 500s on every database-backed request while Postgres reports itself
# healthy.
#
# Deliberately not checked here. setup.sh runs before the stack is started, so
# there is no live database to compare against, and comparing
# `dc exec db printenv POSTGRES_PASSWORD` would be worthless anyway — Compose
# injects that variable from .env, so it matches by construction. ./run.sh
# performs a real authentication attempt from a separate container, which is the
# only check that can actually detect a mismatch.

# --- build -------------------------------------------------------------------

section "Build"

# Through step(), so buildkit's per-layer progress is captured and reduced to one
# line. On failure the last 30 lines are printed with the reason.
step "Building images" dc build \
  || die "Image build failed ${G_DOT} re-run with VERBOSE=1 ./setup.sh for the full stream."

# Image sizes are the only useful thing to report after a silent build.
if [ "$HAS_TTY" = 1 ]; then
  while read -r svc size; do
    [ -n "$svc" ] && bullet "$(printf '%-9s %s' "$svc" "$size")"
  done < <(dc images --format '{{.Service}} {{.Size}}' 2>/dev/null)
fi

# --- next --------------------------------------------------------------------

summary "Ready ${G_DOT} start the stack with ./run.sh" ok
dim "  http://localhost:8080"
dim "  ./run.sh --help for logs, psql, shell, down and destroy"
printf '\n' >&2