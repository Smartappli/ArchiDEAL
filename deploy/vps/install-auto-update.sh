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
readonly runtime_dir="/run/archideal"
readonly installer_lock="$runtime_dir/vps-auto-update-installer.lock"
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
  --interval-minutes N        Cron interval dividing 60 (default: 10).
  --health-url URL            Local HTTP(S) entry point.
  --health-timeout DURATION   Positive s/m/h duration (default: 5m).
  --python COMMAND            Python executable name/absolute path (default: python3).
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

for executable in awk bash cat chmod chown cmp cp docker env flock getent git id \
  install mktemp readlink rm rmdir runuser sha256sum sh stat; do
  command -v "$executable" >/dev/null 2>&1 || \
    fail "missing required executable: $executable"
done
bash_path="$(command -v bash)"
bash_path="$(readlink -f -- "$bash_path")" || fail "cannot resolve the Bash executable."
[[ "$bash_path" == /* && -x "$bash_path" && "$bash_path" =~ ^/[A-Za-z0-9_./+-]+$ ]] || \
  fail "the Bash executable must have an absolute path without whitespace."

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
case "$interval_minutes" in
  1|2|3|4|5|6|10|12|15|20|30) ;;
  *) fail "--interval-minutes must be one of: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30." ;;
esac
[[ "$health_timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]] || \
  fail "--health-timeout must look like 30s, 5m or 1h."
[[ "$health_url" =~ ^https?://[^/@[:space:]]+(:[0-9]+)?(/[^[:space:]]*)?$ ]] || \
  fail "--health-url must be an HTTP(S) URL without credentials."
[[ "$python_command" =~ ^[A-Za-z0-9_.+-]+$ || \
   "$python_command" =~ ^/[A-Za-z0-9_./+-]+$ ]] || \
  fail "--python must be an executable name or an absolute path without whitespace."

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
source_commit="$("${run_as_target[@]}" git -C "$repo_dir" \
  rev-parse --verify 'HEAD^{commit}')" || fail "the checkout HEAD is invalid."
[[ "$source_commit" =~ ^[0-9a-fA-F]{40,64}$ ]] || fail "the checkout HEAD is invalid."
updater_mode="$("${run_as_target[@]}" git -C "$repo_dir" \
  ls-tree "$source_commit" -- scripts/update-vps.sh | awk 'NR == 1 {print $1}')"
[[ "$updater_mode" == "100755" ]] || \
  fail "scripts/update-vps.sh must be an executable file in the current commit."

prepare_root_directory() {
  local path="$1"
  local mode="$2"
  local group="$3"
  local expected_gid

  expected_gid="$(getent group "$group" | awk -F: 'NR == 1 {print $3}')"
  [[ "$expected_gid" =~ ^[0-9]+$ ]] || fail "cannot resolve managed group: $group"

  [[ ! -L "$path" ]] || fail "managed directory must not be a symlink: $path"
  if [[ -e "$path" ]]; then
    [[ -d "$path" ]] || fail "managed directory is not a directory: $path"
    [[ "$(stat -c '%u' -- "$path")" == "0" ]] || \
      fail "$path must be root-owned before installation (use: chown root:$group $path)."
    [[ "$(stat -c '%g' -- "$path")" == "$expected_gid" ]] || \
      fail "$path belongs to another group; refusing to alter an existing installation."
  fi
  install -d -m "$mode" -o root -g "$group" "$path"
}

ensure_system_directory() {
  local path="$1"
  local mode mode_value

  [[ ! -L "$path" ]] || fail "system directory must not be a symlink: $path"
  if [[ ! -e "$path" ]]; then
    install -d -m 0755 -o root -g root "$path"
    return
  fi
  [[ -d "$path" && "$(stat -c '%u' -- "$path")" == "0" ]] || \
    fail "system directory must be a root-owned directory: $path"
  mode="$(stat -c '%a' -- "$path")"
  mode_value=$((8#$mode))
  (( (mode_value & 022) == 0 )) || \
    fail "system directory must not be writable by group or other users: $path"
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

secure_root_file() {
  local path="$1"
  local description="$2"
  local mode mode_value

  [[ -f "$path" && ! -L "$path" ]] || fail "$description is not a regular file."
  [[ "$(stat -c '%u' -- "$path")" == "0" ]] || fail "$description is not root-owned."
  mode="$(stat -c '%a' -- "$path")"
  mode_value=$((8#$mode))
  (( (mode_value & 022) == 0 )) || \
    fail "$description must not be writable by group or other users."
}

for managed_path in "$installed_updater" "$config_file" "$compose_env_file" \
  "$log_file" "$updater_lock" "$installer_lock" "$cron_file"; do
  [[ ! -L "$managed_path" ]] || fail "managed path must not be a symlink: $managed_path"
done
prepare_root_directory "$runtime_dir" 0700 root

if [[ ! -e "$installer_lock" ]]; then
  install -m 0600 -o root -g root /dev/null "$installer_lock"
fi
[[ -f "$installer_lock" && "$(stat -c '%u' -- "$installer_lock")" == "0" ]] || \
  fail "the installer lock is not a root-owned regular file."
chmod 0600 "$installer_lock"
exec 8<>"$installer_lock"
flock -n 8 || fail "another installer is already running."

# Refuse a different service account before changing any existing directory.
for target_file in "$config_file" "$compose_env_file" "$log_file" "$updater_lock"; do
  if [[ -e "$target_file" ]]; then
    secure_installed_file "$target_file" "existing managed file $target_file"
  fi
done
if [[ -e "$installed_updater" ]]; then
  secure_root_file "$installed_updater" "the installed updater"
fi
if [[ -e "$cron_file" ]]; then
  secure_root_file "$cron_file" "the dedicated cron file"
fi

prepare_root_directory "$install_dir" 0755 root
prepare_root_directory "$config_dir" 0750 "$target_group"
prepare_root_directory "$log_dir" 0750 "$target_group"
prepare_root_directory "$state_dir" 0750 "$target_group"
ensure_system_directory "$cron_dir"

if [[ ! -e "$updater_lock" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$updater_lock"
fi
secure_installed_file "$updater_lock" "the updater lock"
chmod 0600 "$updater_lock"
exec 9<>"$updater_lock"
flock -n 9 || fail "an automatic update is currently running; retry later."

if [[ ! -e "$log_file" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" /dev/null "$log_file"
fi
secure_installed_file "$log_file" "the updater log"
chmod 0600 "$log_file"

work_dir="$(mktemp -d /run/archideal-auto-update-install.XXXXXX)"
chown root:"$target_group" "$work_dir"
chmod 0710 "$work_dir"
root_config="$work_dir/update-vps.root.env"
dry_run_config="$work_dir/update-vps.dry-run.env"
dry_run_secret="$work_dir/compose.dry-run.env"
root_secret="$work_dir/compose.root.env"
staged_updater="$work_dir/update-vps.sh"
cron_candidate="$work_dir/archideal-vps-auto-update.cron"
check_lock="$work_dir/dry-run.lock"
updater_backup="$work_dir/update-vps.backup"
config_backup="$work_dir/update-vps.env.backup"
secret_backup="$work_dir/compose.env.backup"
cron_backup="$work_dir/cron.backup"
updater_existed="false"
config_existed="false"
secret_existed="false"
cron_existed="false"
activation_started="false"
activation_complete="false"

restore_or_remove() {
  local path="$1"
  local backup="$2"
  local existed="$3"
  local owner="$4"
  local group="$5"
  local mode="$6"

  if [[ "$existed" == "true" ]]; then
    install -m "$mode" -o "$owner" -g "$group" "$backup" "$path"
  else
    rm -f -- "$path"
  fi
}

rollback_activation() {
  local rollback_failed=0

  # Cron is restored last, after every file it can invoke is coherent again.
  rm -f -- "$cron_file" || rollback_failed=1
  restore_or_remove "$installed_updater" "$updater_backup" "$updater_existed" \
    root root 0755 || rollback_failed=1
  if [[ "$install_secret" == "true" ]]; then
    restore_or_remove "$compose_env_file" "$secret_backup" "$secret_existed" \
      "$target_user" "$target_group" 0600 || rollback_failed=1
  fi
  restore_or_remove "$config_file" "$config_backup" "$config_existed" \
    "$target_user" "$target_group" 0600 || rollback_failed=1
  restore_or_remove "$cron_file" "$cron_backup" "$cron_existed" \
    root root 0644 || rollback_failed=1

  if ((rollback_failed)); then
    printf '%s\n' 'install-auto-update: ERROR: activation rollback was incomplete; cron remains disabled.' >&2
    rm -f -- "$cron_file"
  else
    printf '%s\n' 'install-auto-update: restored the previous installation after an activation error.' >&2
  fi
}

cleanup() {
  local exit_status=$?

  trap - EXIT
  set +e
  if [[ "$activation_started" == "true" && "$activation_complete" != "true" ]]; then
    rollback_activation
  fi
  rm -f -- "$root_config" "$dry_run_config" "$dry_run_secret" \
    "$root_secret" "$staged_updater" "$cron_candidate" "$check_lock" \
    "$updater_backup" "$config_backup" "$secret_backup" "$cron_backup"
  rmdir -- "$work_dir" 2>/dev/null || true
  exit "$exit_status"
}
trap cleanup EXIT

# Read the validated Git blob with target-user privileges. Root opens a
# root-owned destination first, so the target user never controls its inode.
install -m 0600 -o root -g root /dev/null "$staged_updater"
updater_blob="${source_commit}:scripts/update-vps.sh"
"${run_as_target[@]}" git -C "$repo_dir" show "$updater_blob" >"$staged_updater" || \
  fail "the committed updater could not be staged."
[[ -s "$staged_updater" ]] || fail "the committed updater is empty."
chown root:"$target_group" "$staged_updater"
chmod 0750 "$staged_updater"
bash -n "$staged_updater" || fail "the committed updater has invalid Bash syntax."

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
  [[ ! -L "$compose_env_source" ]] || \
    fail "the Compose env source must not be a symlink."
  compose_env_source="$(readlink -f -- "$compose_env_source")" || \
    fail "cannot resolve --compose-env."
  [[ -f "$compose_env_source" ]] || \
    fail "the Compose env source must be a regular file."
  [[ "$(stat -c '%u' -- "$compose_env_source")" == "$target_uid" ]] || \
    fail "the Compose env source must be owned by $target_user."
  source_mode="$(stat -c '%a' -- "$compose_env_source")"
  source_mode_value=$((8#$source_mode))
  (( (source_mode_value & 077) == 0 )) || \
    fail "the Compose env source must not be accessible to group or other users."

  install -m 0600 -o root -g root /dev/null "$root_secret"
  "${run_as_target[@]}" cat -- "$compose_env_source" >"$root_secret" || \
    fail "the Compose env could not be staged."
  [[ -s "$root_secret" ]] || fail "the Compose env source is empty."
  install -m 0600 -o "$target_user" -g "$target_group" \
    "$root_secret" "$dry_run_secret"
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
"${run_as_target[@]}" "$staged_updater" --config "$dry_run_config" --dry-run || \
  fail "the updater dry-run failed; cron was not activated."

if [[ "$install_secret" == "true" ]]; then
  [[ "$(sha256sum "$dry_run_secret" | awk '{print $1}')" == "$secret_digest" ]] || \
    fail "the staged Compose env changed during validation."
fi
[[ -z "$("${run_as_target[@]}" git -C "$repo_dir" status --porcelain=v1 --untracked-files=all)" ]] || \
  fail "the checkout changed during installation; cron was not activated."
[[ "$("${run_as_target[@]}" git -C "$repo_dir" branch --show-current)" == "$branch" ]] || \
  fail "the checkout branch changed during installation; cron was not activated."
[[ "$("${run_as_target[@]}" git -C "$repo_dir" rev-parse --verify 'HEAD^{commit}')" == \
   "$source_commit" ]] || fail "the checkout commit changed during installation; cron was not activated."

{
  printf 'SHELL=%s\n' "$bash_path"
  printf 'PATH=%s\n' "$PATH"
  printf '*/%s * * * * %s %s --config %s >/dev/null 2>&1\n' \
    "$interval_minutes" "$target_user" "$installed_updater" "$config_file"
} >"$cron_candidate"
chmod 0600 "$cron_candidate"

# Keep root-only snapshots for rollback, then disable the old schedule before
# changing any file it can invoke. The replacement cron file is installed last.
if [[ -e "$installed_updater" ]]; then
  install -m 0600 -o root -g root "$installed_updater" "$updater_backup"
  updater_existed="true"
fi
if [[ -e "$config_file" ]]; then
  install -m 0600 -o root -g root "$config_file" "$config_backup"
  config_existed="true"
fi
if [[ "$install_secret" == "true" && -e "$compose_env_file" ]]; then
  install -m 0600 -o root -g root "$compose_env_file" "$secret_backup"
  secret_existed="true"
fi
if [[ -e "$cron_file" ]]; then
  install -m 0600 -o root -g root "$cron_file" "$cron_backup"
  cron_existed="true"
fi

activation_started="true"
rm -f -- "$cron_file"
install -m 0755 -o root -g root "$staged_updater" "$installed_updater"
if [[ "$install_secret" == "true" ]]; then
  install -m 0600 -o "$target_user" -g "$target_group" \
    "$root_secret" "$compose_env_file"
fi
install -m 0600 -o "$target_user" -g "$target_group" "$root_config" "$config_file"
install -m 0644 -o root -g root "$cron_candidate" "$cron_file"
activation_complete="true"

log "installation complete."
if [[ "$install_secret" == "true" ]]; then
  log "installed the Compose env without displaying its contents."
fi
log "cron checks for updates every $interval_minutes minute(s) as $target_user."
log "dedicated cron file: $cron_file"
log "updater log: $log_file"
log "ensure the host cron daemon is enabled and remove any older manual updater entry."
