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
replace_config="false"

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
readonly cron_dir="/etc/cron.d"
readonly cron_file="$cron_dir/archideal-vps-auto-update"

usage() {
  cat <<'EOF'
Usage: install-auto-update.sh --user USER --repo PATH [OPTIONS]

Install the guarded ArchiDEAL Compose updater and a dedicated /etc/cron.d job.
Run this installer as root from a clean ArchiDEAL checkout.

Required on first installation:
  --user USER                 Existing non-root service account.
  --repo PATH                 Absolute ArchiDEAL checkout owned by USER.
  --compose-env PATH          Existing mode-0600 env file owned by USER.

Options:
  --remote NAME               Git remote (default: origin).
  --branch NAME               Checked-out branch (default: main).
  --interval-minutes N        Cron interval from 1 to 59 (default: 10).
  --health-url URL            Local HTTP(S) entry point.
  --health-timeout DURATION   Positive s/m/h duration (default: 5m).
  --python COMMAND            Python executable name/path (default: python3).
  --build-pull                Refresh base-image layers while building.
  --replace-compose-env       Replace the installed secret env file after checks.
  --replace-config            Replace a differing managed updater configuration.
  -h, --help                  Show this help.

Reinstallation is idempotent. Existing secrets and differing configurations
are never overwritten without their explicit replacement option. This script
does not edit the target user's existing crontab.
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
    --replace-config)
      replace_config="true"
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
  exit 2
}

log() {
  printf 'install-auto-update: %s\n' "$1"
}

if ((EUID != 0)); then
  fail "run this installer as root (for example with sudo)."
fi

for executable in awk cat chmod chown cmp cp docker env flock getent git id \
  install mktemp readlink rm rmdir runuser sha256sum sh stat; do
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
if [[ ! "$interval_minutes" =~ ^[1-9][0-9]?$ ]] || \
   ((10#$interval_minutes > 59)); then
  fail "--interval-minutes must be between 1 and 59."
fi
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

prepare_root_directory() {
  local path="$1"
  local mode="$2"
  local group="$3"

  [[ ! -L "$path" ]] || fail "managed directory must not be a symlink: $path"
  if [[ -e "$path" ]]; then
    [[ -d "$path" ]] || fail "managed directory is not a directory: $path"
    [[ "$(stat -c '%u' -- "$path")" == "0" ]] || \
      fail "$path must be root-owned before installation (use: chown root:$group $path)."
  fi
  install -d -m "$mode" -o root -g "$group" "$path"
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

for managed_path in "$installed_updater" "$config_file" "$compose_env_file" \
  "$log_file" "$updater_lock" "$installer_lock" "$cron_file"; do
  [[ ! -L "$managed_path" ]] || fail "managed path must not be a symlink: $managed_path"
done
prepare_root_directory "$install_dir" 0755 root
prepare_root_directory "$config_dir" 0750 "$target_group"
prepare_root_directory "$log_dir" 0750 "$target_group"
prepare_root_directory "$state_dir" 0750 "$target_group"
prepare_root_directory "$cron_dir" 0755 root
if [[ ! -e /run/lock ]]; then
  install -d -m 0755 -o root -g root /run/lock
fi
prepare_root_directory /run/lock 0755 root

if [[ ! -e "$installer_lock" ]]; then
  install -m 0600 -o root -g root /dev/null "$installer_lock"
fi
[[ -f "$installer_lock" && "$(stat -c '%u' -- "$installer_lock")" == "0" ]] || \
  fail "the installer lock is not a root-owned regular file."
chmod 0600 "$installer_lock"
exec 8<>"$installer_lock"
flock -n 8 || fail "another installer is already running."

if [[ ! -e "$updater_lock" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$updater_lock"
fi
secure_installed_file "$updater_lock" "the updater lock"
exec 9<>"$updater_lock"
flock -n 9 || fail "an automatic update is currently running; retry later."

if [[ ! -e "$log_file" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$log_file"
fi
secure_installed_file "$log_file" "the updater log"

work_dir="$(mktemp -d /run/archideal-auto-update-install.XXXXXX)"
chown root:"$target_group" "$work_dir"
chmod 0710 "$work_dir"
root_config="$work_dir/update-vps.root.env"
dry_run_config="$work_dir/update-vps.dry-run.env"
dry_run_secret="$work_dir/compose.dry-run.env"
root_secret="$work_dir/compose.root.env"
cron_candidate="$work_dir/archideal-vps-auto-update.cron"
check_lock="$work_dir/dry-run.lock"

cleanup() {
  rm -f -- "$root_config" "$dry_run_config" "$dry_run_secret" \
    "$root_secret" "$cron_candidate" "$check_lock"
  rmdir -- "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT

write_config() {
  local destination="$1"
  local env_path="$2"
  local lock_path="$3"

  {
    printf '%s\n' '# Managed by deploy/vps/install-auto-update.sh.'
    printf 'ARCHIDEAL_REPO_DIR=%q\n' "$repo_dir"
    printf 'ARCHIDEAL_REMOTE=%q\n' "$remote"
    printf 'ARCHIDEAL_BRANCH=%q\n' "$branch"
    printf 'ARCHIDEAL_ENV_FILE=%q\n' "$env_path"
    printf 'ARCHIDEAL_COMPOSE_PROJECT=archideal\n'
    printf 'ARCHIDEAL_HEALTH_URL=%q\n' "$health_url"
    printf 'ARCHIDEAL_HEALTH_TIMEOUT=%q\n' "$health_timeout"
    printf 'ARCHIDEAL_BUILD_PULL=%s\n' "$build_pull"
    printf 'ARCHIDEAL_FORCE_REDEPLOY=0\n'
    printf 'ARCHIDEAL_PYTHON=%q\n' "$python_command"
    printf 'ARCHIDEAL_LOG_FILE=%q\n' "$log_file"
    printf 'ARCHIDEAL_LOCK_FILE=%q\n' "$lock_path"
    printf 'ARCHIDEAL_UPDATE_PATH=%q\n' "$PATH"
  } >"$destination"
}

write_config "$root_config" "$compose_env_file" "$updater_lock"
chmod 0600 "$root_config"
if [[ -e "$config_file" ]]; then
  secure_installed_file "$config_file" "the installed updater configuration"
  if ! cmp -s -- "$root_config" "$config_file" && \
     [[ "$replace_config" != "true" ]]; then
    fail "the installed config differs; review it, then rerun with --replace-config."
  fi
fi

install_secret="false"
if [[ -e "$compose_env_file" ]]; then
  secure_installed_file "$compose_env_file" "the installed Compose env file"
  if [[ "$replace_compose_env" == "true" ]]; then
    install_secret="true"
  elif [[ -n "$compose_env_source" ]]; then
    log "preserving the installed Compose env; use --replace-compose-env to replace it."
  fi
else
  install_secret="true"
fi

if [[ "$install_secret" == "true" ]]; then
  [[ -n "$compose_env_source" ]] || \
    fail "--compose-env is required to install or replace the Compose env."
  compose_env_source="$(readlink -f -- "$compose_env_source")" || \
    fail "cannot resolve --compose-env."
  [[ -f "$compose_env_source" && ! -L "$compose_env_source" ]] || \
    fail "the Compose env source must be a regular, non-symlink file."
  [[ "$(stat -c '%u' -- "$compose_env_source")" == "$target_uid" ]] || \
    fail "the Compose env source must be owned by $target_user."
  source_mode="$(stat -c '%a' -- "$compose_env_source")"
  source_mode_value=$((8#$source_mode))
  (( (source_mode_value & 077) == 0 )) || \
    fail "the Compose env source must not be accessible to group or other users."

  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$dry_run_secret"
  "${run_as_target[@]}" sh -c 'cat -- "$1" >"$2"' sh \
    "$compose_env_source" "$dry_run_secret" || fail "the Compose env could not be staged."
  [[ -s "$dry_run_secret" ]] || fail "the Compose env source is empty."
  cp -- "$dry_run_secret" "$root_secret"
  chown root:root "$root_secret"
  chmod 0600 "$root_secret"
  secret_digest="$(sha256sum "$root_secret" | awk '{print $1}')"
  dry_run_env="$dry_run_secret"
else
  dry_run_env="$compose_env_file"
fi

install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$check_lock"
write_config "$dry_run_config" "$dry_run_env" "$check_lock"
chown "$target_user:$target_group" "$dry_run_config"
chmod 0600 "$dry_run_config"

"${run_as_target[@]}" docker info --format '{{.ServerVersion}}' >/dev/null || \
  fail "$target_user cannot reach Docker from a cron-like environment."
log "running the updater admission check as $target_user."
"${run_as_target[@]}" "$source_updater" --config "$dry_run_config" --dry-run || \
  fail "the updater dry-run failed; cron was not activated."

if [[ "$install_secret" == "true" ]]; then
  [[ "$(sha256sum "$dry_run_secret" | awk '{print $1}')" == "$secret_digest" ]] || \
    fail "the staged Compose env changed during validation."
fi
[[ -z "$("${run_as_target[@]}" git -C "$repo_dir" status --porcelain=v1 --untracked-files=all)" ]] || \
  fail "the checkout changed during installation; cron was not activated."
[[ "$("${run_as_target[@]}" git -C "$repo_dir" branch --show-current)" == "$branch" ]] || \
  fail "the checkout branch changed during installation; cron was not activated."

install -m 0755 -o root -g root "$source_updater" "$installed_updater"
if [[ "$install_secret" == "true" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" \
    "$root_secret" "$compose_env_file"
  log "installed the Compose env without displaying its contents."
fi
install -m 0600 -o "$target_user" -g "$target_group" "$root_config" "$config_file"

{
  printf 'SHELL=/bin/bash\n'
  printf 'PATH=%s\n' "$PATH"
  printf '*/%s * * * * %s %s --config %s >/dev/null 2>&1\n' \
    "$interval_minutes" "$target_user" "$installed_updater" "$config_file"
} >"$cron_candidate"
chmod 0600 "$cron_candidate"
install -m 0644 -o root -g root "$cron_candidate" "$cron_file"

log "installation complete."
log "cron checks for updates every $interval_minutes minute(s) as $target_user."
log "dedicated cron file: $cron_file"
log "updater log: $log_file"
log "ensure the host cron daemon is enabled and remove any older manual updater entry."
