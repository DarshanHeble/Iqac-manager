#!/usr/bin/env bash
#
# run.sh — run and inspect the IQAC Manager stack.
#
#   ./run.sh [command]      up (default) · status · logs · db · sh · down · destroy · rebuild
#
#   VERBOSE=1 ./run.sh      stream docker's raw output instead of summarising
#
# Requires ./setup.sh to have been run once.

set -euo pipefail
cd "$(dirname "$0")"

# shellcheck source=docker/lib/shell.sh
source docker/lib/shell.sh

# --- .env access -------------------------------------------------------------

need_env() {
  [ -f .env ] || die "No .env found ${G_DOT} run ./setup.sh first."
}

# Read one key from .env. Quoted values are unwrapped so a .env with quotes does
# not leak them into a URL or a psql argument.
env_or() {
  [ -f .env ] || return 0
  local v
  v=$(grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true)
  v=${v#\"}; v=${v%\"}
  printf '%s' "$v"
}

# --- health waiting ----------------------------------------------------------

# Poll container health rather than sleeping a fixed interval: a cold `npm ci`
# can take minutes, so a fixed sleep either wastes time or gives up early.
# Renders a live countdown instead of nothing happening for two minutes.
wait_healthy() {
  local service=$1 timeout=${2:-240}
  local waited=0 cid state health

  if [ "$HAS_TTY" = 1 ]; then
    printf '%s%s%s waiting for %s' "$INDENT" "$C_CYAN" "$G_INFO" "$service" >&2
  fi

  while [ "$waited" -lt "$timeout" ]; do
    cid=$(dc ps -q "$service" 2>/dev/null || true)
    if [ -n "$cid" ]; then
      health=$(docker inspect -f \
        '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$cid" 2>/dev/null || echo unknown)
      case "$health" in
        healthy|running)
          [ "$HAS_TTY" = 1 ] && _clear_line
          return 0
          ;;
        unhealthy|exited|dead)
          [ "$HAS_TTY" = 1 ] && _clear_line
          fail "$service is $health"
          explain_failure "$service"
          return 1
          ;;
      esac
    fi
    if [ "$HAS_TTY" = 1 ]; then
      _clear_line
      printf '%s%s%s waiting for %-9s %s%ss%s' \
        "$INDENT" "$C_CYAN" "$G_INFO" "$service" "$C_DIM" "$waited" "$C_RESET" >&2
    fi
    sleep 2
    waited=$((waited + 2))
  done

  [ "$HAS_TTY" = 1 ] && _clear_line
  fail "$service did not become healthy within $(_fmt_duration $((timeout * 1000)))"
  explain_failure "$service"
  return 1
}

# --- up ----------------------------------------------------------------------

cmd_up() {
  need_env
  dc_resolve
  dc_daemon

  banner "up"

  section "Build"
  step "Building images" dc build \
    || die "Image build failed ${G_DOT} re-run with VERBOSE=1 ./run.sh"

  section "Start"
  # The database comes up on its own first. Doing it in this order is what makes
  # a credential mismatch detectable *before* the backend dies on it: the
  # backend's failure mode is a 500 on every request, which reads like an
  # application bug rather than a config one.
  step "Starting database" dc up -d db --quiet-pull \
    || die "The database container failed to start."

  wait_healthy db 90 || die "database did not come up."

  # Postgres stores the password the volume was created with and silently
  # ignores later changes to .env, so the two can diverge with no error until the
  # backend tries to authenticate.
  #
  # The check has to run from a *different* container than db, using the app's own
  # connection helper. Two near-misses are worth recording:
  #   - `docker compose exec db printenv POSTGRES_PASSWORD` is useless: Compose
  #     populates that variable *from* .env, so it always matches by construction.
  #   - `psql -h 127.0.0.1` inside the db container is also useless: the stock
  #     pg_hba.conf sets `host ... 127.0.0.1/32 trust`, so it authenticates
  #     anyone regardless of the password.
  # Only a TCP connection from another container hits the `scram-sha-256` rule,
  # which is the same path the backend itself takes.
  if ! dc run --rm --no-deps -T backend \
        python -c "import sys; sys.path.insert(0,'backend'); from db import get_db_connection; get_db_connection().close()" \
        >/dev/null 2>&1; then
    fail "POSTGRES_PASSWORD in .env is not the password this volume uses"
    dim  "Postgres keeps the password the volume was created with. Editing .env"
    dim  "afterwards changes nothing on the database side, and the backend then"
    dim  "fails to authenticate on every database-backed request."
    printf '\n' >&2
    dim  "${G_ARR} ./run.sh destroy        delete the volume and all data, start fresh"
    dim  "${G_ARR} ./run.sh down && ./run.sh  if you prefer restoring the old password"
    printf '\n' >&2
    exit 1
  fi
  ok "db       PostgreSQL ready, credentials verified"

  step "Starting application" dc up -d backend frontend --quiet-pull \
    || die "Containers failed to start."

  section "Health"
  wait_healthy backend 180 || { explain_failure backend; die "backend did not come up."; }
  ok "backend  gunicorn up, database reachable, schema present"

  wait_healthy frontend 60 \
    && ok "frontend nginx serving the Angular bundle" \
    || warn "frontend not healthy yet ${G_DOT} it may still be starting, check ./run.sh logs"

  section "Endpoints"
  local fe be
  fe=$(env_or FRONTEND_PORT); fe=${fe:-8080}
  be=$(env_or BACKEND_PORT);  be=${be:-5000}
  bullet "app     http://localhost:$fe"
  bullet "api     http://localhost:$fe/api/  $G_DOT proxied to the backend"
  bullet "legacy  http://localhost:$be/  $G_DOT Flask's own UI, localhost only"
  if grep -q '^CLOUDINARY_API_SECRET=replace_me' .env 2>/dev/null; then
    printf '\n' >&2
    warn "Cloudinary is unconfigured $G_DOT login and reports work, uploads will fail"
  fi

  summary "Running ${G_DOT} http://localhost:$fe" ok
  dim "  ./run.sh logs    follow logs"
  dim "  ./run.sh down    stop, keep the database"
  printf '\n' >&2
}

# --- status ------------------------------------------------------------------

cmd_status() {
  need_env
  dc_resolve

  local running
  running=$(dc ps -q --status running 2>/dev/null | wc -l)

  if [ "$running" -eq 0 ]; then
    summary "Stack is stopped" warn
    dim "  ./run.sh          start it"
    printf '\n' >&2
    return 0
  fi

  banner "status"
  section "Containers"

  # Column widths chosen to fit a normal 80-column terminal. Header goes to
  # stderr with the rest of the chrome; see the note on ok()/warn() in shell.sh.
  printf '%s  %s%s %s %s%s\n' \
    "$INDENT" "$C_DIM" "SERVICE" "STATUS" "PORTS" "$C_RESET" >&2

  while read -r svc state health ports; do
    [ -z "$svc" ] && continue
    local colour glyph label
    case "$health" in
      healthy)   colour=$C_GREEN;  glyph=$G_OK;   label="healthy"   ;;
      starting)  colour=$C_YELLOW; glyph=$G_INFO; label="starting"  ;;
      unhealthy) colour=$C_RED;    glyph=$G_FAIL; label="unhealthy" ;;
      *)         colour=$C_YELLOW; glyph=$G_WARN; label="$health"   ;;
    esac
    printf '%s  %s%-9s%s %s%s %-9s%s %s%s%s\n' \
      "$INDENT" "$C_BOLD" "$svc" "$C_RESET" \
      "$colour" "$glyph" "$label" "$C_RESET" \
      "$C_DIM" "$ports" "$C_RESET" >&2
  done < <(dc ps --format '{{.Service}} {{.State}} {{.Health}} {{.Ports}}' 2>/dev/null)

  section "Data"
  if dc ps --services --status running 2>/dev/null | grep -qx db; then
    local rows
    rows=$(dc exec -T db psql -U "$(env_or POSTGRES_USER)" -d "$(env_or POSTGRES_DB)" \
             -tAc "SELECT count(*) FROM users" 2>/dev/null || echo '?')
    bullet "database  postgres:16-alpine $G_DOT $rows users, volume retained across restarts"
  fi

  local fe; fe=$(env_or FRONTEND_PORT); fe=${fe:-8080}
  printf '\n' >&2
  bullet "http://localhost:$fe"
  printf '\n' >&2
}

# --- logs --------------------------------------------------------------------

cmd_logs() {
  need_env
  dc_resolve

  local service="" follow=0 lines=100
  while [ $# -gt 0 ]; do
    case "$1" in
      -f|--follow) follow=1; shift ;;
      -n) lines=$2; shift 2 ;;
      backend|frontend|db) service=$1; shift ;;
      -h|--help) dim "  ./run.sh logs [-f] [-n LINES] [backend|frontend|db]"; return 0 ;;
      *) die "unknown logs option: $1" ;;
    esac
  done

  if [ "$follow" = 1 ] && [ "$HAS_TTY" != 1 ]; then
    follow=0
    dim "not a terminal ${G_DOT} showing the last $lines lines instead of following"
  fi

  printf '\n' >&2
  if [ "$follow" = 1 ]; then
    dim "  following ${service:-all services} ${G_DOT} Ctrl-C to stop"
    printf '\n' >&2
  fi

  # docker compose prefixes each line with the service and colourises it, which
  # is already the right shape; --no-log-prefix would strip the one piece of
  # information that matters when reading three services at once.
  if [ "$follow" = 1 ]; then
    dc logs -f --tail "$lines" $service
  else
    dc logs --tail "$lines" $service
    printf '\n' >&2
  fi
}

# --- db ----------------------------------------------------------------------

cmd_db() {
  need_env
  dc_resolve
  dc_daemon
  dc ps --services --status running 2>/dev/null | grep -qx db \
    || die "The database is not running ${G_DOT} ./run.sh first."
  # psql must run inside the container: port 5432 is deliberately not published.
  # Extra arguments are forwarded, so `./run.sh db -c "SELECT 1"` works and does
  # not silently open an interactive shell that cannot read from a pipe.
  dc exec db psql -U "$(env_or POSTGRES_USER)" -d "$(env_or POSTGRES_DB)" "$@"
}

# --- sh ----------------------------------------------------------------------

cmd_sh() {
  need_env
  dc_resolve
  local service=${1:-backend}
  shift || true
  case "$service" in
    backend|frontend|db) ;;
    *) die "unknown service: $service   (backend | frontend | db)" ;;
  esac
  dc ps --services --status running 2>/dev/null | grep -qx "$service" \
    || die "$service is not running ${G_DOT} ./run.sh first."
  # sh, not bash: the frontend image is nginx:alpine, which has no bash at all,
  # and the same call has to work for all three services. Remaining arguments are
  # forwarded so `./run.sh sh backend -c "..."` runs instead of opening a shell.
  dc exec "$service" sh "$@"
}

# --- rebuild -----------------------------------------------------------------

cmd_rebuild() {
  need_env
  dc_resolve
  dc_daemon
  banner "rebuild"
  section "Build"
  # --no-cache is the point of this subcommand: a plain build would reuse the
  # very layers you are trying to invalidate.
  step "Rebuilding without cache" dc build --no-cache \
    || die "Rebuild failed ${G_DOT} re-run with VERBOSE=1 ./run.sh"
  if dc ps -q --status running >/dev/null 2>&1; then
    section "Restart"
    dc up -d --remove-orphans --quiet-pull || die "Restart failed."
    section "Health"
    wait_healthy backend 180 && ok "backend healthy"
    wait_healthy frontend 60 && ok "frontend healthy"
  fi
  summary "Rebuilt" ok
}

# --- down --------------------------------------------------------------------

cmd_down() {
  need_env
  dc_resolve
  banner "down"
  step "Stopping containers" dc down --remove-orphans || die "Failed to stop."
  ok "database volume kept ${G_DOT} ./run.sh destroy removes it too"
  summary "Stopped" ok
}

# --- destroy -----------------------------------------------------------------

# Removes every trace of the stack: containers, network, volume, built images,
# and the build cache that would otherwise keep consuming disk. Each category is
# reported so the user can see what actually went.
cmd_destroy() {
  need_env
  dc_resolve
  dc_daemon

  banner "destroy"

  warn "This deletes the PostgreSQL volume and every worklog entry in it."
  dim  "Uploaded files under backend/static/{attachments,signed_reports} are kept."
  confirm "Type 'destroy' to remove all containers, images and data" "destroy" \
    || die "Aborted ${G_DOT} nothing was changed."

  section "Remove"
  local removed=0

  step "containers and network" dc down -v --remove-orphans --rmi local \
    || die "Could not remove containers."

  # Built images are pulled by tag, not by a compose-managed reference in every
  # Docker version, so remove them explicitly.
  if dc images -q 2>/dev/null | head -1 | grep -q .; then
    step "built images" dc images -q | xargs -r docker rmi -f \
      || warn "Some images could not be removed."
    removed=1
  fi

  # Only the build cache this project's images produced, and only when the user
  # opted in with --all. `docker builder prune -a` is cluster-wide.
  if [ "${1:-}" = "--all" ]; then
    confirm "This also clears Docker's shared build cache for every project" "prune-all" \
      || die "Aborted."
    step "build cache" docker builder prune -af || warn "Build cache prune reported an error."
    removed=1
  fi

  section "Result"
  if [ "$removed" = 1 ]; then
    ok "removed containers, network, volume and images"
  else
    ok "removed containers, network and volume"
  fi
  bullet "volumes    $(dc volumes 2>/dev/null || echo 'none')"
  bullet "your .env is untouched $G_DOT run ./setup.sh to start over"
  bullet "source files untouched"

  summary "Destroyed" ok
  printf '  %srebuild from scratch%s  ./setup.sh && ./run.sh\n\n' "$C_BOLD" "$C_RESET"
}

# --- dispatch ----------------------------------------------------------------

case "${1:-up}" in
  up|"")      shift || true; cmd_up "$@" ;;
  status|ps)  shift || true; cmd_status "$@" ;;
  logs)       shift || true; cmd_logs "$@" ;;
  db|psql)    shift || true; cmd_db "$@" ;;
  sh|shell)   shift || true; cmd_sh "$@" ;;
  rebuild)    shift || true; cmd_rebuild "$@" ;;
  down)       shift || true; cmd_down "$@" ;;
  destroy)    shift || true; cmd_destroy "$@" ;;
  -h|--help|help)
    printf '\n%s%sIQAC Manager%s  %s  %s\n\n' \
      "$INDENT" "$C_BOLD$C_CYAN" "$C_RESET" "$G_DOT" "container commands"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "run" "$C_RESET"          "build, start, wait for health, show endpoints"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "status" "$C_RESET"      "service table, health, row counts"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "logs" "$C_RESET"        "follow logs  ${C_DIM}(-f, -n LINES, [service])${C_RESET}"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "db" "$C_RESET"          "psql shell  ${C_DIM}(extra args pass through, e.g. -c \"SELECT 1\")${C_RESET}"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "sh [service]" "$C_RESET" "shell in backend (default), frontend or db"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "rebuild" "$C_RESET"     "rebuild ${C_DIM}--no-cache${C_RESET}, restart if running"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "down" "$C_RESET"       "stop, keep the database"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "destroy" "$C_RESET"    "remove containers, network, volume, images"
    printf '  %s%-12s%s %s\n' "" "" ""                 "${C_DIM}keeps .env, source and uploaded files${C_RESET}"
    printf '  %s%-12s%s %s\n' "$C_BOLD" "destroy --all" "$C_RESET" "the above, plus Docker's shared build cache"
    printf '\n  %sVERBOSE=1%s streams docker output instead of summarising\n\n' \
      "$C_DIM" "$C_RESET"
    ;;
  *) die "unknown command: $1
       try ./run.sh --help" ;;
esac