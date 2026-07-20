#!/usr/bin/env bash
set -Eeuo pipefail

readonly EXIT_USAGE=2
readonly EXIT_LOCKED=10
readonly EXIT_UNSAFE_REPOSITORY=20
readonly EXIT_VALIDATION_FAILED=30
readonly EXIT_DEPLOYMENT_FAILED=40
readonly EXIT_ROLLBACK_FAILED=50

config_file=""
dry_run="false"

usage() {
  cat <<'EOF'
Usage: update-vps.sh --config PATH [--dry-run]

Safely fast-forwards an ArchiDEAL checkout and updates its Docker Compose
stack. The configuration file must be owned by the invoking user and must not
be readable or writable by group or other users.

Options:
  --config PATH  Operator-owned configuration file (required).
  --dry-run      Check prerequisites, repository state, remote branch and
                 Compose configuration without changing the checkout or stack.
  -h, --help     Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --config)
      config_file="${2:-}"
      shift 2
      ;;
    --dry-run)
      dry_run="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit "$EXIT_USAGE"
      ;;
  esac
done

if [[ -z "$config_file" || ! -f "$config_file" ]]; then
  printf '%s\n' 'A readable --config file is required.' >&2
  usage >&2
  exit "$EXIT_USAGE"
fi

secure_file() {
  local path="$1"
  local description="$2"
  local owner mode

  owner="$(stat -c '%u' -- "$path" 2>/dev/null)" || {
    printf 'Cannot inspect %s ownership: %s\n' "$description" "$path" >&2
    return 1
  }
  mode="$(stat -c '%a' -- "$path" 2>/dev/null)" || {
    printf 'Cannot inspect %s permissions: %s\n' "$description" "$path" >&2
    return 1
  }
  if [[ "$owner" != "$(id -u)" || ! "$mode" =~ ^[0-7]?[0-7]00$ ]]; then
    printf '%s must be owned by uid %s and inaccessible to group/other (mode 0600).\n' \
      "$description" "$(id -u)" >&2
    return 1
  fi
}

secure_file "$config_file" 'The update configuration' || exit "$EXIT_USAGE"

# The file is executable shell configuration and must remain operator-owned.
# It must contain deployment metadata and paths only, never application secrets.
# shellcheck disable=SC1090
source "$config_file"

: "${ARCHIDEAL_REPO_DIR:=}"
: "${ARCHIDEAL_REMOTE:=origin}"
: "${ARCHIDEAL_BRANCH:=main}"
: "${ARCHIDEAL_ENV_FILE:=}"
: "${ARCHIDEAL_COMPOSE_PROJECT:=archideal}"
: "${ARCHIDEAL_HEALTH_URL:=http://127.0.0.1:8080}"
: "${ARCHIDEAL_HEALTH_TIMEOUT:=5m}"
: "${ARCHIDEAL_BUILD_PULL:=0}"
: "${ARCHIDEAL_FORCE_REDEPLOY:=0}"
: "${ARCHIDEAL_PYTHON:=python3}"
: "${ARCHIDEAL_LOG_FILE:=}"
: "${ARCHIDEAL_LOCK_FILE:=}"
: "${ARCHIDEAL_UPDATE_PATH:=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"

PATH="$ARCHIDEAL_UPDATE_PATH"
export PATH
umask 077

if [[ -z "$ARCHIDEAL_REPO_DIR" || ! -d "$ARCHIDEAL_REPO_DIR/.git" ]]; then
  printf '%s\n' 'ARCHIDEAL_REPO_DIR must reference an ArchiDEAL Git checkout.' >&2
  exit "$EXIT_USAGE"
fi

repo_dir="$(cd -- "$ARCHIDEAL_REPO_DIR" && pwd -P)"
if [[ -z "$ARCHIDEAL_ENV_FILE" ]]; then
  ARCHIDEAL_ENV_FILE="$repo_dir/.env"
elif [[ "$ARCHIDEAL_ENV_FILE" != /* ]]; then
  ARCHIDEAL_ENV_FILE="$repo_dir/$ARCHIDEAL_ENV_FILE"
fi
if [[ -z "$ARCHIDEAL_LOG_FILE" ]]; then
  ARCHIDEAL_LOG_FILE="$repo_dir/.git/archideal-vps-update.log"
elif [[ "$ARCHIDEAL_LOG_FILE" != /* ]]; then
  ARCHIDEAL_LOG_FILE="$repo_dir/$ARCHIDEAL_LOG_FILE"
fi
if [[ -z "$ARCHIDEAL_LOCK_FILE" ]]; then
  ARCHIDEAL_LOCK_FILE="$repo_dir/.git/archideal-vps-update.lock"
elif [[ "$ARCHIDEAL_LOCK_FILE" != /* ]]; then
  ARCHIDEAL_LOCK_FILE="$repo_dir/$ARCHIDEAL_LOCK_FILE"
fi

mkdir -p -- "$(dirname -- "$ARCHIDEAL_LOG_FILE")" \
  "$(dirname -- "$ARCHIDEAL_LOCK_FILE")"
touch -- "$ARCHIDEAL_LOG_FILE"
chmod 600 -- "$ARCHIDEAL_LOG_FILE"
exec > >(tee -a "$ARCHIDEAL_LOG_FILE") 2>&1

log() {
  printf '%s [%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" "$2"
}

for executable in git docker flock timeout stat id tee "$ARCHIDEAL_PYTHON"; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    log ERROR "Missing required executable: $executable"
    exit "$EXIT_USAGE"
  fi
done

exec 9>"$ARCHIDEAL_LOCK_FILE"
if ! flock -n 9; then
  log INFO 'Another VPS update is already running; nothing was changed.'
  exit "$EXIT_LOCKED"
fi

if [[ ! "$ARCHIDEAL_REMOTE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  log ERROR 'ARCHIDEAL_REMOTE is invalid.'
  exit "$EXIT_USAGE"
fi
if ! git check-ref-format --branch "$ARCHIDEAL_BRANCH" >/dev/null 2>&1; then
  log ERROR 'ARCHIDEAL_BRANCH is invalid.'
  exit "$EXIT_USAGE"
fi
if [[ ! "$ARCHIDEAL_COMPOSE_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  log ERROR 'ARCHIDEAL_COMPOSE_PROJECT is invalid.'
  exit "$EXIT_USAGE"
fi
if [[ ! "$ARCHIDEAL_HEALTH_TIMEOUT" =~ ^[1-9][0-9]*(s|m|h)$ ]]; then
  log ERROR 'ARCHIDEAL_HEALTH_TIMEOUT must be a positive duration such as 5m.'
  exit "$EXIT_USAGE"
fi
if [[ "$ARCHIDEAL_BUILD_PULL" != "0" && "$ARCHIDEAL_BUILD_PULL" != "1" ]]; then
  log ERROR 'ARCHIDEAL_BUILD_PULL must be 0 or 1.'
  exit "$EXIT_USAGE"
fi
if [[ "$ARCHIDEAL_FORCE_REDEPLOY" != "0" && "$ARCHIDEAL_FORCE_REDEPLOY" != "1" ]]; then
  log ERROR 'ARCHIDEAL_FORCE_REDEPLOY must be 0 or 1.'
  exit "$EXIT_USAGE"
fi
if [[ ! "$ARCHIDEAL_HEALTH_URL" =~ ^https?://[^/@[:space:]]+(:[0-9]+)?(/[^[:space:]]*)?$ ]]; then
  log ERROR 'ARCHIDEAL_HEALTH_URL must be an HTTP(S) URL without credentials.'
  exit "$EXIT_USAGE"
fi
if [[ ! -s "$ARCHIDEAL_ENV_FILE" ]]; then
  log ERROR 'ARCHIDEAL_ENV_FILE must reference a non-empty Compose environment file.'
  exit "$EXIT_USAGE"
fi
secure_file "$ARCHIDEAL_ENV_FILE" 'The Compose environment file' || \
  exit "$EXIT_USAGE"

cd -- "$repo_dir"
if [[ "$(git rev-parse --show-toplevel 2>/dev/null)" != "$repo_dir" ]]; then
  log ERROR 'ARCHIDEAL_REPO_DIR must be the top level of its Git checkout.'
  exit "$EXIT_UNSAFE_REPOSITORY"
fi
if [[ ! -f compose.yaml || ! -f scripts/validate-monorepo.py || \
      ! -f scripts/check-architecture.py ]]; then
  log ERROR 'The checkout does not contain the expected ArchiDEAL deployment files.'
  exit "$EXIT_UNSAFE_REPOSITORY"
fi
if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
  log ERROR 'The checkout has local changes; refusing to overwrite or stash them.'
  exit "$EXIT_UNSAFE_REPOSITORY"
fi
if ! docker compose version >/dev/null 2>&1; then
  log ERROR 'Docker Compose v2 is required.'
  exit "$EXIT_USAGE"
fi
if ! git remote get-url "$ARCHIDEAL_REMOTE" >/dev/null 2>&1; then
  log ERROR 'The configured Git remote does not exist.'
  exit "$EXIT_USAGE"
fi

compose=(
  docker compose
  --project-name "$ARCHIDEAL_COMPOSE_PROJECT"
  --project-directory "$repo_dir"
  --env-file "$ARCHIDEAL_ENV_FILE"
  --file "$repo_dir/compose.yaml"
)

validate_checkout() {
  "$ARCHIDEAL_PYTHON" "$repo_dir/scripts/validate-monorepo.py"
  "${compose[@]}" config --quiet
}

health_check() {
  timeout --foreground "$ARCHIDEAL_HEALTH_TIMEOUT" \
    env ARCHIDEAL_BASE_URL="$ARCHIDEAL_HEALTH_URL" \
    "$ARCHIDEAL_PYTHON" "$repo_dir/scripts/check-architecture.py" --health-only
}

log INFO "Checking $ARCHIDEAL_REMOTE/$ARCHIDEAL_BRANCH."
if [[ "$dry_run" == "true" ]]; then
  remote_line="$(
    git ls-remote --exit-code --heads "$ARCHIDEAL_REMOTE" "$ARCHIDEAL_BRANCH"
  )" || {
    log ERROR 'The configured remote branch could not be resolved.'
    exit "$EXIT_UNSAFE_REPOSITORY"
  }
  target_commit="${remote_line%%[[:space:]]*}"
  current_commit="$(git rev-parse --verify 'HEAD^{commit}')"
  current_branch="$(git branch --show-current)"
  log INFO "Dry run: current branch=${current_branch:-detached}, current=${current_commit:0:12}, remote=${target_commit:0:12}."
  if ! validate_checkout; then
    log ERROR 'Dry-run validation failed.'
    exit "$EXIT_VALIDATION_FAILED"
  fi
  log INFO 'Dry run passed; no checkout, image or container was changed.'
  exit 0
fi

log INFO 'Fetching the configured branch without force-updating any local ref.'
git fetch --prune "$ARCHIDEAL_REMOTE" \
  "refs/heads/$ARCHIDEAL_BRANCH:refs/remotes/$ARCHIDEAL_REMOTE/$ARCHIDEAL_BRANCH"

if git show-ref --verify --quiet "refs/heads/$ARCHIDEAL_BRANCH"; then
  git switch "$ARCHIDEAL_BRANCH" >/dev/null
else
  git switch --create "$ARCHIDEAL_BRANCH" \
    --track "$ARCHIDEAL_REMOTE/$ARCHIDEAL_BRANCH" >/dev/null
fi

if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
  log ERROR 'Switching branches exposed local changes; refusing the update.'
  exit "$EXIT_UNSAFE_REPOSITORY"
fi

previous_commit="$(git rev-parse --verify 'HEAD^{commit}')"
target_commit="$(
  git rev-parse --verify \
    "refs/remotes/$ARCHIDEAL_REMOTE/$ARCHIDEAL_BRANCH^{commit}"
)"
previous_image_tag="git-${previous_commit:0:12}"
target_image_tag="git-${target_commit:0:12}"
checkout_updated="false"
deployment_started="false"
rollback_running="false"
failure_exit="$EXIT_DEPLOYMENT_FAILED"

restore_previous_checkout() {
  if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
    log ERROR 'Rollback cannot restore source because new local changes appeared.'
    return 1
  fi
  git switch --detach "$previous_commit" >/dev/null
  git branch --force "$ARCHIDEAL_BRANCH" "$previous_commit" >/dev/null
  git switch "$ARCHIDEAL_BRANCH" >/dev/null
}

rollback() {
  local rollback_ok="true"

  rollback_running="true"
  set +e
  trap - ERR INT TERM
  log WARN "Update failed; restoring commit ${previous_commit:0:12}."

  if [[ "$checkout_updated" == "true" ]]; then
    if ! restore_previous_checkout; then
      rollback_ok="false"
    fi
  fi

  if [[ "$deployment_started" == "true" && "$rollback_ok" == "true" ]]; then
    export ARCHIDEAL_IMAGE_TAG="$previous_image_tag"
    if ! validate_checkout || \
       ! "${compose[@]}" build || \
       ! "${compose[@]}" up -d --remove-orphans || \
       ! health_check; then
      rollback_ok="false"
    fi
  fi

  if [[ "$rollback_ok" == "true" ]]; then
    log WARN "Rollback to ${previous_commit:0:12} completed."
    exit "$failure_exit"
  fi
  log ERROR 'Automatic rollback failed; operator intervention is required.'
  exit "$EXIT_ROLLBACK_FAILED"
}

handle_error() {
  local command_status="$1"
  local line_number="$2"

  if [[ "$rollback_running" == "true" ]]; then
    exit "$EXIT_ROLLBACK_FAILED"
  fi
  log ERROR "Command failed during update (line $line_number, status $command_status)."
  rollback
}

handle_signal() {
  local signal_name="$1"
  log ERROR "Received $signal_name during update."
  failure_exit="$EXIT_DEPLOYMENT_FAILED"
  rollback
}

trap 'handle_error $? $LINENO' ERR
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

if ! git merge-base --is-ancestor "$previous_commit" "$target_commit"; then
  log ERROR 'The remote update is not a fast-forward; local commits were preserved.'
  exit "$EXIT_UNSAFE_REPOSITORY"
fi

if [[ "$previous_commit" == "$target_commit" && \
      "$ARCHIDEAL_FORCE_REDEPLOY" == "0" ]]; then
  failure_exit="$EXIT_VALIDATION_FAILED"
  validate_checkout
  failure_exit="$EXIT_DEPLOYMENT_FAILED"
  health_check
  log INFO "Commit ${target_commit:0:12} is already deployed and healthy."
  exit 0
fi

git merge --ff-only "$target_commit" >/dev/null
checkout_updated="true"
log INFO "Checkout advanced from ${previous_commit:0:12} to ${target_commit:0:12}."

failure_exit="$EXIT_VALIDATION_FAILED"
validate_checkout

export ARCHIDEAL_IMAGE_TAG="$target_image_tag"
build_arguments=()
if [[ "$ARCHIDEAL_BUILD_PULL" == "1" ]]; then
  build_arguments+=(--pull)
fi
"${compose[@]}" build "${build_arguments[@]}"

failure_exit="$EXIT_DEPLOYMENT_FAILED"
deployment_started="true"
"${compose[@]}" up -d --remove-orphans
health_check

trap - ERR INT TERM
log INFO "VPS update to ${target_commit:0:12} completed successfully."
