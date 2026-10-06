#!/usr/bin/env bash
# =============================================================================
# docker/lib/shell.sh — shared terminal layer for setup.sh and run.sh.
#
# Sourced, never executed. Owns colour handling, step timing, spinners and
# log capture so the two entry scripts contain only their own logic.
#
# The reason this exists: `docker compose build` streams hundreds of lines of
# buildkit progress (`#31 8.482`, `=> => exporting layers`) straight to stderr.
# Forwarding that to a human is noise. Every long command here is captured to a
# temp file, reduced to one line of output, and dumped in full only when it
# fails. Set VERBOSE=1 to see the raw stream while it runs.
# =============================================================================

# --- capability detection ----------------------------------------------------

# Colour only when a human is watching. Piping to a file or a log collector
# should produce plain text, not escape codes.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m';  C_DIM=$'\033[2m'
  C_RED=$'\033[31m';   C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m';  C_CYAN=$'\033[36m'; C_GREY=$'\033[90m'
  HAS_TTY=1
else
  C_RESET=''; C_BOLD=''; C_DIM=''
  C_RED='';   C_GREEN=''; C_YELLOW=''
  C_BLUE='';  C_CYAN=''; C_GREY=''
  HAS_TTY=0
fi

# Unicode when the terminal can encode it; ASCII otherwise, so the output does
# not turn into mojibake under a legacy locale or a minimal container.
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *UTF-8*|*utf8*|*UTF8*) GLYPH_OK=1 ;;
  *)                      GLYPH_OK=0 ;;
esac
if [ "$GLYPH_OK" = 1 ] && [ "$HAS_TTY" = 1 ]; then
  G_OK=$'✔'; G_FAIL=$'✖'; G_WARN=$'⚠'; G_INFO=$'ℹ'
  G_DOT=$'·';  G_RULE=$'─'; G_BULLET=$'•'; G_ARR=$'→'
else
  G_OK='ok'; G_FAIL='FAIL'; G_WARN='!'; G_INFO='-'
  G_DOT='-';  G_RULE='-';  G_BULLET='*'; G_ARR='->'
fi

INDENT='    '

# --- timing ------------------------------------------------------------------

# Epoch time in MILLISECONDS.
#
# EPOCHREALTIME is a bash 5+ builtin holding MICROSECONDS since the epoch, so
# the fractional part must be divided by 1000. Getting this wrong scales every
# displayed duration by 1000 — a 3s build reported as "50m". Falling back to
# `date +%s` (seconds) avoids a fork on older bash but costs resolution.
_now_ms() {
  local t=${EPOCHREALTIME:-}
  if [ -n "$t" ]; then
    printf '%s%03d' "${t%.*}" "$(( 10#${t#*.} / 1000 ))"
  else
    printf '%s000' "$(date +%s)"
  fi
}

# Human-readable duration. 940ms -> "940ms", 2.6s -> "2.6s", 95s -> "1m 35s".
_fmt_duration() {
  local ms=$1
  if   [ "$ms" -lt 1000 ];  then printf '%sms' "$ms"
  elif [ "$ms" -lt 60000 ]; then printf '%d.%ds' $((ms / 1000)) $(((ms % 1000) / 100))
  else printf '%dm %ds' $((ms / 60000)) $(((ms % 60000) / 1000))
  fi
}

# Wall-clock start, set once per entry script.
SHELL_T0=$(_now_ms)

# --- static output -----------------------------------------------------------

# A titled band. The rule is sized to the terminal so the heading ends at the
# right margin instead of at a fixed 60 columns.
section() {
  local title=$1 total=${COLUMNS:-0}
  [ "$total" -lt 44 ] && total=72
  local avail=$(( total - ${#INDENT} - 1 ))
  local pad=$(( avail - ${#title} - 2 ))
  [ "$pad" -lt 2 ] && pad=2
  # Built with bash substitution rather than `tr ' ' "$G_RULE"`: tr operates on
  # bytes when the locale is not UTF-8, so a multibyte rule collapses into
  # invalid sequences and prints as a row of replacement characters.
  local spaces rule
  printf -v spaces '%*s' "$pad" ''
  rule=${spaces// /$G_RULE}
  printf '\n%s%s%s %s%s%s\n' "$INDENT" "$C_BOLD" "$title" \
    "$C_DIM" "$rule" "$C_RESET" >&2
}

# Every human-readable line goes to stderr, deliberately. Status and progress are
# chrome, not data: keeping them off stdout means `./run.sh logs > app.log` yields
# only container output, and — more importantly — stdout is block-buffered when
# piped while stderr is not, so mixing the two reorders them unpredictably the
# moment output is redirected to a file or a pipe.
ok()    { printf '%s%s%s %s\n'    "$INDENT" "$C_GREEN"  "$G_OK"   "$*" >&2; }
warn()  { printf '%s%s%s %s%s\n'  "$INDENT" "$C_YELLOW" "$G_WARN" "$*" "$C_RESET" >&2; }
info()  { printf '%s%s%s %s%s\n'  "$INDENT" "$C_CYAN"   "$G_INFO" "$*" "$C_RESET" >&2; }
fail()  { printf '%s%s%s %s%s\n'  "$INDENT" "$C_RED"    "$G_FAIL" "$*" "$C_RESET" >&2; }
plain() { printf '%s%s%s\n'        "$INDENT" "$*" "$C_RESET" >&2; }
dim()   { printf '%s%s%s%s\n'      "$INDENT" "$C_DIM"    "$*" "$C_RESET" >&2; }
bullet(){ printf '%s  %s%s %s%s\n'   "$INDENT" "$C_GREY"   "$G_BULLET" "$*" "$C_RESET" >&2; }

# Success line with an optional right-aligned elapsed time.
#   ok_timed "backend image built" "$ms"
ok_timed() {
  local msg=$1 ms=${2:-}
  local line="$msg"
  if [ -n "$ms" ]; then
    line="$msg  $(printf '%s%s%s' "$C_DIM" "$(_fmt_duration "$ms")" "$C_RESET")"
  fi
  printf '%s%s%s %s\n' "$INDENT" "$C_GREEN" "$G_OK" "$line" >&2
}

# Header shown once at the top of a script, carrying the elapsed time so far.
banner() {
  printf '\n%s%s%s %s%s%s  %s%s%s\n' \
    "$INDENT" "$C_BOLD" "$C_CYAN" "$G_BULLET" "$1" "$C_RESET" \
    "$C_GREY" "$(_fmt_duration $(( $(_now_ms) - SHELL_T0 )))" "$C_RESET" >&2
}

# Terminal summary line. $1 = message, $2 = "ok" | "warn" | "fail".
summary() {
  local msg=$1 kind=${2:-ok}
  local glyph colour
  case $kind in
    ok)   glyph=$G_OK;   colour=$C_GREEN  ;;
    warn) glyph=$G_WARN; colour=$C_YELLOW ;;
    *)    glyph=$G_FAIL; colour=$C_RED    ;;
  esac
  printf '\n%s%s%s %s%s%s  %s%s%s\n\n' \
    "$INDENT" "$colour" "$glyph" "$C_BOLD" "$msg" "$C_RESET" \
    "$C_DIM" "$(_fmt_duration $(( $(_now_ms) - SHELL_T0 )))" "$C_RESET" >&2
}

# --- spinner -----------------------------------------------------------------

# Only animates on a TTY. Spinner frames go to stderr so that stdout stays
# parseable when a script's output is consumed by another tool.
SPINNER_PID=""

_spinner_frame() {
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  [ "$GLYPH_OK" = 1 ] || frames='/-\|'
  printf '%s' "${frames:0:1}"
}

_spinner_loop() {
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  [ "$GLYPH_OK" = 1 ] || frames='/-\|'
  local i=0
  while :; do
    # \033[K erases to end of line as well as returning to column 0, so a
    # shrinking label cannot leave fragments behind.
    printf '\r\033[K%s%s%s %s%s' "$INDENT" "$C_CYAN" "${frames:i:1}" "$1" "$C_RESET" >&2
    i=$(( (i + 1) % ${#frames} ))
    sleep 0.1
  done
}

# Erase the spinner line. Written as a function so the exact escape sequence
# lives in one place.
_clear_line() { printf '\r\033[K' >&2; }

# Print a captured log body indented, in the error colour.
print_log_body() {
  local log=$1 lines=${2:-30}
  [ -f "$log" ] || return 0
  local total; total=$(wc -l < "$log")
  printf '\n%s%s  %s last %s of output%s\n' \
    "$INDENT" "$C_DIM" "$G_RULE" "$lines" "$C_RESET" >&2
  if [ "$total" -gt "$lines" ]; then
    tail -n "$lines" "$log"
  else
    cat "$log"
  fi | while IFS= read -r l; do
    printf '%s  %s%s%s\n' "$INDENT" "$C_RED" "$l" "$C_RESET"
  done >&2
  printf '\n' >&2
}

# Turn a container's logs into a diagnosis when it fails to become healthy.
#
# `docker compose up` reports "dependency failed to start" without ever showing
# why, and the reason lives in the *dependency's* logs. Without this the user
# gets a generic failure and has to know to go looking. Matches the handful of
# failure modes that are actually possible here.
#
#   explain_failure <service>
explain_failure() {
  local service=$1
  local log; log=$(mktemp "${TMPDIR:-/tmp}/iqac-diag.XXXXXX")
  dc logs --tail 60 "$service" > "$log" 2>&1

  if grep -q 'password authentication failed' "$log"; then
    printf '\n%s%s%s %sThe database password does not match%s\n' \
      "$INDENT" "$C_RED" "$G_FAIL" "$C_BOLD" "$C_RESET" >&2
    printf '%s  %sPostgres keeps the password the volume was created with.%s\n' \
      "$INDENT" "$C_DIM" "$C_RESET" >&2
    printf '%s  %sChanging POSTGRES_PASSWORD in .env after the first run breaks\n' \
      "$INDENT" "$C_DIM" >&2
    printf '%s  %sauth, and nothing on the database side changes.%s\n' \
      "$INDENT" "$C_DIM" "$C_RESET" >&2
    printf '\n%s  %s./run.sh destroy%s   %sdelete the volume and all data, then start fresh\n' \
      "$INDENT" "$C_BOLD" "$C_RESET" "$C_DIM" >&2
    printf '%s  %s./run.sh down && ./run.sh%s   %sif you would rather restore the old password\n\n' \
      "$INDENT" "$C_BOLD" "$C_RESET" "$C_DIM" >&2
  elif grep -qiE 'could not initialize database|could not connect' "$log"; then
    printf '\n%s%s%s %sThe backend cannot reach the database%s\n' \
      "$INDENT" "$C_RED" "$G_FAIL" "$C_BOLD" "$C_RESET" >&2
  elif grep -q 'Cloudinary' "$log"; then
    printf '\n%s%s%s %sCloudinary is not configured%s\n' \
      "$INDENT" "$C_RED" "$G_FAIL" "$C_BOLD" "$C_RESET" >&2
    printf '%s  %sapp.py calls cloudinary.config() at import and will not boot\n' \
      "$INDENT" "$C_DIM" >&2
    printf '%s  %swithout CLOUDINARY_CLOUD_NAME, _API_KEY and _API_SECRET.%s\n\n' \
      "$INDENT" "$C_DIM" "$C_RESET" >&2
  fi

  print_log_body "$log" 20
  rm -f "$log"
}

# --- captured commands -------------------------------------------------------

# Path of the log from the last failed step, so it can be re-read.
LAST_LOG=""

# Dump the tail of a captured log — the diagnostic that actually matters when a
# step fails, since the whole point of capturing was to keep it out of the way
# until it was needed.
_dump_log() { print_log_body "$1" "${2:-30}"; }

# Run a command quietly, showing a spinner and a one-line result.
#
#   step "Building images" docker compose build
#
# Set VERBOSE=1 to stream the command live instead of capturing it.
# Returns the command's exit status; on failure the tail of its output is shown
# and left in $LAST_LOG.
step() {
  local label=$1; shift
  if [ "${1:-}" = "--" ]; then shift; fi

  local log start rc
  log=$(mktemp "${TMPDIR:-/tmp}/iqac-step.XXXXXX")
  start=$(_now_ms)

  if [ "${VERBOSE:-0}" = "1" ]; then
    dim "$label $G_ARR"
    "$@" 2>&1 | while IFS= read -r l; do printf '%s  %s\n' "$INDENT" "$l"; done
    rc=${PIPESTATUS[0]}
    _clear_line
    if [ "$rc" -eq 0 ]; then
      ok_timed "$label" "$(( $(_now_ms) - start ))"
    else
      fail "$label"
    fi
    rm -f "$log"
    return "$rc"
  fi

  if [ "$HAS_TTY" = 1 ]; then
    _spinner_loop "$label" &
    SPINNER_PID=$!
  fi

  "$@" > "$log" 2>&1
  rc=$?

  if [ -n "$SPINNER_PID" ] && [ "$SPINNER_PID" -gt 1 ] 2>/dev/null; then
    kill "$SPINNER_PID" 2>/dev/null || true
    wait "$SPINNER_PID" 2>/dev/null || true
    _clear_line
    SPINNER_PID=""
  fi

  if [ "$rc" -eq 0 ]; then
    ok_timed "$label" "$(( $(_now_ms) - start ))"
    rm -f "$log"
    return 0
  fi

  fail "$label"
  _dump_log "$log" 30
  LAST_LOG="$log"
  return "$rc"
}

# Capture a command's stdout for later inspection (no output at all).
#   capture VAR some-command
capture() {
  local __var=$1; shift
  "$@" 2>/dev/null && :
}

# Abort with a clean message. The only place a script may exit non-zero with
# output of its own.
die() {
  if [ -n "$SPINNER_PID" ]; then
    kill "$SPINNER_PID" 2>/dev/null || true
    _clear_line
  fi
  printf '%s%s%s %s%s\n\n' "$INDENT" "$C_RED" "$G_FAIL" "$C_BOLD$*" "$C_RESET" >&2
  exit 1
}

# --- confirmation ------------------------------------------------------------

# Destructive actions must be typed out in full, not answered y/n. This runs
# `./run.sh destroy` and `./setup.sh --reset`; a stray Enter should not be
# enough to drop a database.
confirm() {
  local prompt=$1 expected=$2
  [ "$HAS_TTY" = 1 ] || die "refusing to run '$expected' without a terminal"
  local answer
  printf '\n%s%s%s %s%s%s\n' \
    "$INDENT" "$C_YELLOW" "$G_WARN" "$C_BOLD" "$prompt" "$C_RESET" >&2
  printf '%s  %s%s' "$INDENT" "$G_ARR" "$expected $G_DOT " >&2
  read -r answer || answer=""
  printf '\n' >&2
  [ "$answer" = "$expected" ]
}

# --- docker helpers ----------------------------------------------------------

# The Compose command, resolved once. v2 plugin only: `docker-compose` (v1, Python)
# is EOL and behaves differently enough to be worth refusing rather than
# half-supporting.
DC_READY=0
dc_resolve() {
  command -v docker >/dev/null 2>&1 \
    || die "Docker is not installed.
       Install it from https://docs.docker.com/get-docker/ and re-run."
  docker compose version >/dev/null 2>&1 \
    || die "The Docker Compose v2 plugin is missing.
       'docker-compose' v1 is not supported. Install the plugin:
         https://docs.docker.com/compose/install/"
  DC_READY=1
}

# The daemon can be installed and still not be running, or the user may lack
# socket permission. `docker info` catches all three with one call.
dc_daemon() {
  docker info >/dev/null 2>&1 \
    || die "Cannot reach the Docker daemon.
       It may not be running, or your user may lack socket permission.
         sudo systemctl start docker
         sudo usermod -aG docker $USER   # then log out and back in"
}

dc() { docker compose "$@"; }

# The Compose project name, as Compose itself resolves it. Honours COMPOSE_PROJECT_NAME
# and otherwise derives the directory-based default, so it never drifts from the
# project Compose actually uses.
dc_project() {
  docker compose config --format json 2>/dev/null | sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1
}

# Whether a Compose-managed named volume exists, e.g. dc_has_volume db-data.
#
# Compose has no `volume` subcommand, so `dc volume ls` would fail outright.
# Instead filter `docker volume ls` on the two labels Compose stamps onto every
# volume it creates. Both are required: `com.docker.compose.volume` alone is just
# the volume *key* from the compose file, so any other project that happens to
# declare a volume called db-data would also match, and a stray match makes
# --reset warn about (and destroy) data that is not ours.
dc_has_volume() {
  local project
  project=$(dc_project)
  [ -n "$project" ] || return 1
  [ -n "$(docker volume ls -q \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.volume=$1" 2>/dev/null)" ]
}

# Human label for the Docker version, e.g. "Docker 29.7.2 · Compose v5.5.1"
dc_version_line() {
  local d c
  d=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ,)
  c=$(docker compose version --short 2>/dev/null)
  printf 'Docker %s %s Compose v%s' "$d" "$G_DOT" "$c"
}