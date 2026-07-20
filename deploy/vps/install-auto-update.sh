#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

target_user=""
repo_input=""
compose_env_source=""
remote="origin"
branch="main"
interval_minutes=10
health_url="http://127.0.0.1:8080"
health_timeout="5m"
python_command="python3"
build_pull=0
replace_compose_env="false"

readonly install_dir="/usr/local/libexec/archideal"
readonly installed_updater="$install_dir/update-vps.sh"
readonly config_dir="/etc/archideal"
readonly config_file="$config_dir/update-vps.env"
readonly compose_env_file="$config_dir/compose.env"
readonly log_dir="/var/log/archideal"
readonly log_file="$log_dir/vps-update.log"
readonly state_dir="/var/lib/archideal"
readonly updater_lock="$state_dir/vps-update.lock"
readonly installer_lock="/run/lock/archideal-vps-auto-update-installer.lock"
readonly cron_begin="# BEGIN ARCHIDEAL VPS AUTO UPDATE"
readonly cron_end="# END ARCHIDEAL VPS AUTO UPDATE"

usage() {
  cat <<'EOF'
Usage: install-auto-update.sh --user USER --repo PATH [OPTIONS]

Install the guarded ArchiDEAL Compose updater and its user crontab entry.
Run this installer as root from a clean ArchiDEAL checkout.

Required on first installation:
  --user USER                 Existing non-root service account.
  --repo PATH                 Absolute ArchiDEAL checkout owned by USER.
  --compose-env PATH          Existing mode-0600 Compose environment file.

Options:
  --remote NAME               Git remote (default: origin).
  --branch NAME               Checked-out branch (default: main).
  --interval-minutes N        Cron interval from 1 to 59 (default: 10).
  --health-url URL            Local HTTP(S) entry point.
  --health-timeout DURATION   Positive s/m/h duration (default: 5m).
  --python COMMAND            Python executable name/path (default: python3).
  --build-pull                Refresh base-image layers while building.
  --replace-compose-env       Replace the installed secret env file explicitly.
  -h, --help                  Show this help.

An existing managed configuration is preserved. Its repository, env-file and
lock-file assignments must match this installation. Other crontab entries are
never removed or rewritten.
EOF
}

while (($#)); do
  case "$1" in
    --user)
      target_user="${2:-}"
      shift 2
      ;;
    --repo)
      repo_input="${2:-}"
      shift 2
      ;;
    --compose-env)
      compose_env_source="${2:-}"
      shift 2
      ;;
    --remote)
      remote="${2:-}"
      shift 2
      ;;
    --branch)
      branch="${2:-}"
      shift 2
      ;;
    --interval-minutes)
      interval_minutes="${2:-}"
      shift 2
      ;;
    --health-url)
      health_url="${2:-}"
      shift 2
      ;;
    --health-timeout)
      health_timeout="${2:-}"
      shift 2
      ;;
    --python)
      python_command="${2:-}"
      shift 2
      ;;
    --build-pull)
      build_pull=1
      shift
      ;;
    --replace-compose-env)
      replace_compose_env="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

fail() {
  printf 'install-auto-update: %s\n' "$1" >&2
  exit "${2:-2}"
}

log() {
  printf 'install-auto-update: %s\n' "$1"
}

if ((EUID != 0)); then
  fail "run this installer as root (for example with sudo)."
fi

for executable in awk cmp crontab docker flock getent git id install mktemp \
  readlink runuser stat; do
  command -v "$executable" >/dev/null 2>&1 || \
    fail "missing required executable: $executable"
done

[[ -n "$target_user" ]] || fail "--user is required."
[[ "$target_user" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || \
  fail "--user contains unsupported characters."
target_uid="$(id -u "$target_user" 2>/dev/null)" || \
  fail "the target user does not exist: $target_user"
[[ "$target_uid" != "0" ]] || fail "the updater must not run as root."
target_group="$(id -gn "$target_user")" || fail "the target group is unavailable."
target_home="$(getent passwd "$target_user" | awk -F: 'NR == 1 {print $6}')"
[[ "$target_home" == /* && -d "$target_home" ]] || \
  fail "the target user must have an existing absolute home directory."

[[ "$repo_input" == /* ]] || fail "--repo must be an absolute path."
[[ "$repo_input" != *$'\n'* && "$repo_input" != *$'\r'* ]] || \
  fail "--repo contains an invalid newline."
repo_dir="$(readlink -f -- "$repo_input")" || fail "cannot resolve --repo."
[[ "$repo_dir" =~ ^/[A-Za-z0-9._/-]+$ ]] || \
  fail "--repo must not contain whitespace or shell metacharacters."
[[ -d "$repo_dir/.git" ]] || fail "--repo is not a Git checkout."
[[ "$(stat -c '%u' -- "$repo_dir")" == "$target_uid" ]] || \
  fail "the checkout root must be owned by $target_user; no recursive chown is performed."

[[ "$remote" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || \
  fail "--remote is invalid."
git check-ref-format --branch "$branch" >/dev/null 2>&1 || \
  fail "--branch is invalid."
[[ "$interval_minutes" =~ ^[1-9][0-9]?$ ]] && \
  ((10#$interval_minutes <= 59)) || fail "--interval-minutes must be between 1 and 59."
[[ "$health_timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]] || \
  fail "--health-timeout must look like 30s, 5m or 1h."
[[ "$health_url" =~ ^https?://[^/@[:space:]]+(:[0-9]+)?(/[^[:space:]]*)?$ ]] || \
  fail "--health-url must be an HTTP(S) URL without credentials."
[[ "$python_command" =~ ^[A-Za-z0-9_./+-]+$ ]] || \
  fail "--python contains unsupported characters."

run_as_target=(
  runuser -u "$target_user" --
  env HOME="$target_home" USER="$target_user" LOGNAME="$target_user" PATH="$PATH"
)

repo_top="$("${run_as_target[@]}" git -C "$repo_dir" rev-parse --show-toplevel)" || \
  fail "the target user cannot inspect the checkout."
[[ "$repo_top" == "$repo_dir" ]] || fail "--repo must identify the checkout root."
[[ -z "$("${run_as_target[@]}" git -C "$repo_dir" status --porcelain=v1 --untracked-files=all)" ]] || \
  fail "the checkout has local changes; installation is refused."
current_branch="$("${run_as_target[@]}" git -C "$repo_dir" branch --show-current)"
[[ "$current_branch" == "$branch" ]] || \
  fail "the checkout must already be on branch $branch."
"${run_as_target[@]}" git -C "$repo_dir" remote get-url "$remote" >/dev/null 2>&1 || \
  fail "the configured Git remote does not exist."

source_updater="$repo_dir/scripts/update-vps.sh"
[[ -f "$source_updater" && ! -L "$source_updater" && -x "$source_updater" ]] || \
  fail "the tracked executable scripts/update-vps.sh is missing."
"${run_as_target[@]}" git -C "$repo_dir" ls-files --error-unmatch \
  scripts/update-vps.sh >/dev/null 2>&1 || fail "scripts/update-vps.sh is not tracked."

secure_secret_source() {
  local path="$1"
  local owner mode mode_value

  [[ -f "$path" && ! -L "$path" ]] || \
    fail "the Compose env source must be a regular, non-symlink file."
  owner="$(stat -c '%u' -- "$path")"
  [[ "$owner" == "0" || "$owner" == "$target_uid" ]] || \
    fail "the Compose env source must be owned by root or $target_user."
  mode="$(stat -c '%a' -- "$path")"
  mode_value=$((8#$mode))
  (( (mode_value & 077) == 0 )) || \
    fail "the Compose env source must not be accessible to group or other users."
  [[ -s "$path" ]] || fail "the Compose env source is empty."
}

secure_installed_file() {
  local path="$1"
  local description="$2"
  local owner mode mode_value

  [[ -f "$path" && ! -L "$path" ]] || fail "$description is not a regular file."
  owner="$(stat -c '%u' -- "$path")"
  [[ "$owner" == "$target_uid" ]] || fail "$description is not owned by $target_user."
  mode="$(stat -c '%a' -- "$path")"
  mode_value=$((8#$mode))
  (( (mode_value & 077) == 0 )) || \
    fail "$description must not be accessible to group or other users."
}

if [[ -n "$compose_env_source" ]]; then
  compose_env_source="$(readlink -f -- "$compose_env_source")" || \
    fail "cannot resolve --compose-env."
  secure_secret_source "$compose_env_source"
elif [[ ! -f "$compose_env_file" ]]; then
  fail "--compose-env is required for the first installation."
fi
if [[ "$replace_compose_env" == "true" && -z "$compose_env_source" ]]; then
  fail "--replace-compose-env also requires --compose-env."
fi

install -d -m 0755 -o root -g root "$install_dir"
install -d -m 0750 -o "$target_user" -g "$target_group" \
  "$config_dir" "$log_dir" "$state_dir"

exec 8>"$installer_lock"
flock -n 8 || fail "another installer is already running."

if [[ ! -e "$updater_lock" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$updater_lock"
fi
[[ -f "$updater_lock" && ! -L "$updater_lock" ]] || \
  fail "the updater lock path is not a regular file."
chown "$target_user:$target_group" "$updater_lock"
chmod 0600 "$updater_lock"
exec 9<>"$updater_lock"
flock -n 9 || fail "an automatic update is currently running; retry later."

work_dir="$(mktemp -d "$state_dir/.auto-update-install.XXXXXX")"
chown "$target_user:$target_group" "$work_dir"
chmod 0700 "$work_dir"
candidate_config="$work_dir/update-vps.env"
dry_run_config="$work_dir/update-vps.dry-run.env"
current_crontab="$work_dir/current.crontab"
clean_crontab="$work_dir/clean.crontab"
new_crontab="$work_dir/new.crontab"
check_lock="$work_dir/dry-run.lock"

cleanup() {
  rm -f -- "$candidate_config" "$dry_run_config" "$current_crontab" \
    "$clean_crontab" "$new_crontab" "$check_lock"
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT

write_candidate_config() {
  local destination="$1"
  local lock_path="$2"

  {
    printf '%s\n' '# Managed by deploy/vps/install-auto-update.sh.'
    printf 'ARCHIDEAL_REPO_DIR=%s\n' "$repo_dir"
    printf 'ARCHIDEAL_REMOTE=%s\n' "$remote"
    printf 'ARCHIDEAL_BRANCH=%s\n' "$branch"
    printf 'ARCHIDEAL_ENV_FILE=%s\n' "$compose_env_file"
    printf 'ARCHIDEAL_COMPOSE_PROJECT=archideal\n'
    printf 'ARCHIDEAL_HEALTH_URL=%s\n' "$health_url"
    printf 'ARCHIDEAL_HEALTH_TIMEOUT=%s\n' "$health_timeout"
    printf 'ARCHIDEAL_BUILD_PULL=%s\n' "$build_pull"
    printf 'ARCHIDEAL_FORCE_REDEPLOY=0\n'
    printf 'ARCHIDEAL_PYTHON=%s\n' "$python_command"
    printf 'ARCHIDEAL_LOG_FILE=%s\n' "$log_file"
    printf 'ARCHIDEAL_LOCK_FILE=%s\n' "$lock_path"
    printf 'ARCHIDEAL_UPDATE_PATH=%s\n' "$PATH"
  } >"$destination"
  chown "$target_user:$target_group" "$destination"
  chmod 0600 "$destination"
}

write_candidate_config "$candidate_config" "$updater_lock"

assignment_value() {
  local key="$1"
  local source_file="$2"
  local -a matches=()
  local value

  mapfile -t matches < <(awk -v key="$key" 'index($0, key "=") == 1 {print}' "$source_file")
  ((${#matches[@]} == 1)) || return 1
  value="${matches[0]#*=}"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] || return 1
  printf '%s\n' "$value"
}

if [[ -e "$config_file" ]]; then
  secure_installed_file "$config_file" "the installed updater configuration"
  configured_repo="$(assignment_value ARCHIDEAL_REPO_DIR "$config_file")" || \
    fail "the existing config has no single safe ARCHIDEAL_REPO_DIR assignment."
  configured_env="$(assignment_value ARCHIDEAL_ENV_FILE "$config_file")" || \
    fail "the existing config has no single safe ARCHIDEAL_ENV_FILE assignment."
  configured_lock="$(assignment_value ARCHIDEAL_LOCK_FILE "$config_file")" || \
    fail "the existing config has no single safe ARCHIDEAL_LOCK_FILE assignment."
  [[ "$configured_repo" == "$repo_dir" ]] || \
    fail "the existing config manages another repository; it was not overwritten."
  [[ "$configured_env" == "$compose_env_file" ]] || \
    fail "the existing config uses another env file; it was not overwritten."
  [[ "$configured_lock" == "$updater_lock" ]] || \
    fail "the existing config uses another lock file; it was not overwritten."
  config_for_dry_run="$config_file"
  log "preserving the existing updater configuration."
else
  config_for_dry_run="$candidate_config"
fi

if [[ -e "$compose_env_file" ]]; then
  secure_installed_file "$compose_env_file" "the installed Compose env file"
  if [[ "$replace_compose_env" == "true" ]]; then
    install -m 0600 -o "$target_user" -g "$target_group" \
      "$compose_env_source" "$compose_env_file"
    log "replaced the installed Compose env file explicitly."
  elif [[ -n "$compose_env_source" ]] && ! cmp -s -- "$compose_env_source" "$compose_env_file"; then
    log "the installed Compose env differs; it was preserved (use --replace-compose-env to replace it)."
  fi
else
  install -m 0600 -o "$target_user" -g "$target_group" \
    "$compose_env_source" "$compose_env_file"
  log "installed the Compose env file without displaying its contents."
fi

# Use the effective configuration for the admission test, but isolate its lock
# from the production lock held by this installer.
awk -v replacement="ARCHIDEAL_LOCK_FILE=$check_lock" '
  index($0, "ARCHIDEAL_LOCK_FILE=") == 1 {print replacement; next}
  {print}
' "$config_for_dry_run" >"$dry_run_config"
chown "$target_user:$target_group" "$dry_run_config"
chmod 0600 "$dry_run_config"

"${run_as_target[@]}" docker info --format '{{.ServerVersion}}' >/dev/null || \
  fail "$target_user cannot reach the Docker daemon from a cron-like environment."
log "running the updater admission check as $target_user."
"${run_as_target[@]}" "$source_updater" --config "$dry_run_config" --dry-run || \
  fail "the updater dry-run failed; cron was not activated."

# Recheck the invariant immediately before installing executable code.
[[ -z "$("${run_as_target[@]}" git -C "$repo_dir" status --porcelain=v1 --untracked-files=all)" ]] || \
  fail "the checkout changed during installation; cron was not activated."

install -m 0755 -o root -g root "$source_updater" "$installed_updater"
if [[ ! -e "$config_file" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" \
    "$candidate_config" "$config_file"
  log "installed the updater configuration."
fi

if ! crontab -u "$target_user" -l >"$current_crontab" 2>/dev/null; then
  : >"$current_crontab"
fi
if ! awk -v begin="$cron_begin" -v end="$cron_end" '
  $0 == begin {
    seen += 1
    if (inside || seen > 1) bad = 1
    inside = 1
    next
  }
  $0 == end {
    if (!inside) bad = 1
    inside = 0
    next
  }
  !inside {print}
  END {
    if (inside || bad) exit 1
  }
' "$current_crontab" >"$clean_crontab"; then
  fail "the existing crontab contains unbalanced or duplicate ArchiDEAL markers."
fi

cp -- "$clean_crontab" "$new_crontab"
if [[ -s "$new_crontab" ]]; then
  printf '\n' >>"$new_crontab"
fi
{
  printf '%s\n' "$cron_begin"
  printf '*/%s * * * * %s --config %s >/dev/null 2>&1\n' \
    "$interval_minutes" "$installed_updater" "$config_file"
  printf '%s\n' "$cron_end"
} >>"$new_crontab"
crontab -u "$target_user" "$new_crontab"

log "installation complete."
log "cron checks $remote/$branch every $interval_minutes minute(s) as $target_user."
log "updater log: $log_file"
