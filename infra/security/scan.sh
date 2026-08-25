#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

security_die() {
  printf '{"status":"error","code":"%s"}\n' "$1" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || security_die "MISSING_COMMAND_$1"
}

require_safe_directory() {
  local candidate=$1
  local code=$2
  [[ "$candidate" == /* && -d "$candidate" && ! -L "$candidate" ]] ||
    security_die "$code"
  [[ "$(realpath -e -- "$candidate")" != "/" ]] || security_die "$code"
}

for command_name in chmod cp dirname docker git id jq mkdir mktemp realpath rm stat; do
  require_command "$command_name"
done
: "${SECURITY_OUTPUT_DIR:?SECURITY_OUTPUT_DIR is required}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
require_safe_directory "$SECURITY_OUTPUT_DIR" "INVALID_SECURITY_OUTPUT_DIR"
[[ -w "$SECURITY_OUTPUT_DIR" ]] || security_die "SECURITY_OUTPUT_NOT_WRITABLE"

REPOSITORY_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
WORKTREE_SCAN_ROOT=
security_cleanup() {
  local exit_code=$?
  if [[ -n "$WORKTREE_SCAN_ROOT" &&
    "$WORKTREE_SCAN_ROOT" == /tmp/pnx-gitleaks-worktree.* &&
    -d "$WORKTREE_SCAN_ROOT" &&
    ! -L "$WORKTREE_SCAN_ROOT" ]]; then
    rm -rf -- "$WORKTREE_SCAN_ROOT"
  fi
  return "$exit_code"
}
trap security_cleanup EXIT

[[ -d "$REPOSITORY_ROOT/.git" ]] || security_die "REPOSITORY_GIT_MISSING"
docker image inspect "$BACKEND_IMAGE" "$FRONTEND_IMAGE" >/dev/null 2>&1 ||
  security_die "APPLICATION_IMAGE_MISSING"

GITLEAKS_IMAGE='zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f'
SYFT_IMAGE='anchore/syft@sha256:678bfa565b60f747aac0f8e964fe5588a24445b8d0a480e91f6efd70020dfbb0'
TRIVY_IMAGE='aquasec/trivy@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969'
TRIVY_DB_REPOSITORY='ghcr.io/aquasecurity/trivy-db:2'
TRIVY_CHECKS_REPOSITORY='ghcr.io/aquasecurity/trivy-checks:2'
HOST_UID=$(id -u)
HOST_GID=$(id -g)
DOCKER_SOCKET_GID=$(stat -c %g /var/run/docker.sock)

WORKTREE_SCAN_ROOT=$(mktemp -d /tmp/pnx-gitleaks-worktree.XXXXXX)
chmod 0700 "$WORKTREE_SCAN_ROOT"
while IFS= read -r -d '' relative_path; do
  [[ "$relative_path" != /* &&
    "$relative_path" != ".." &&
    "$relative_path" != ../* &&
    "$relative_path" != */../* &&
    "$relative_path" != */.. ]] || security_die "UNSAFE_REPOSITORY_PATH"
  source_path="$REPOSITORY_ROOT/$relative_path"
  [[ -f "$source_path" || -L "$source_path" ]] || continue
  destination_path="$WORKTREE_SCAN_ROOT/$relative_path"
  mkdir -p -- "$(dirname -- "$destination_path")"
  cp -P -- "$source_path" "$destination_path"
done < <(git -C "$REPOSITORY_ROOT" ls-files --cached --others --exclude-standard -z)

docker run --rm \
  --user "$HOST_UID:$HOST_GID" \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --volume "$REPOSITORY_ROOT:/repo:ro" \
  --volume "$SECURITY_OUTPUT_DIR:/output:rw" \
  "$GITLEAKS_IMAGE" detect \
  --source /repo \
  --no-banner \
  --no-color \
  --redact=100 \
  --report-format json \
  --report-path /output/gitleaks-history.json || security_die "SECRET_HISTORY_SCAN_FAILED"
[[ -s "$SECURITY_OUTPUT_DIR/gitleaks-history.json" ]] ||
  printf '[]\n' >"$SECURITY_OUTPUT_DIR/gitleaks-history.json"

docker run --rm \
  --user "$HOST_UID:$HOST_GID" \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --volume "$WORKTREE_SCAN_ROOT:/worktree:ro" \
  --volume "$SECURITY_OUTPUT_DIR:/output:rw" \
  "$GITLEAKS_IMAGE" dir /worktree \
  --no-banner \
  --no-color \
  --redact=100 \
  --report-format json \
  --report-path /output/gitleaks-worktree.json || security_die "SECRET_WORKTREE_SCAN_FAILED"
[[ -s "$SECURITY_OUTPUT_DIR/gitleaks-worktree.json" ]] ||
  printf '[]\n' >"$SECURITY_OUTPUT_DIR/gitleaks-worktree.json"

jq -s 'add | unique_by([.RuleID, .File, .StartLine, .EndLine, .Commit])' \
  "$SECURITY_OUTPUT_DIR/gitleaks-history.json" \
  "$SECURITY_OUTPUT_DIR/gitleaks-worktree.json" >"$SECURITY_OUTPUT_DIR/gitleaks.json"

for target in backend frontend; do
  if [[ "$target" == "backend" ]]; then
    image_reference=$BACKEND_IMAGE
  else
    image_reference=$FRONTEND_IMAGE
  fi
  docker run --rm     --user "$HOST_UID:$HOST_GID"   --tmpfs /tmp:rw,nosuid,nodev,mode=1777   --env SYFT_CHECK_FOR_APP_UPDATE=false     --group-add "$DOCKER_SOCKET_GID"     --volume /var/run/docker.sock:/var/run/docker.sock     --volume "$SECURITY_OUTPUT_DIR:/output:rw"     "$SYFT_IMAGE" "docker:$image_reference"     --output "spdx-json=/output/$target.spdx.json"     --quiet ||
    security_die "SBOM_GENERATION_FAILED"
  [[ -s "$SECURITY_OUTPUT_DIR/$target.spdx.json" ]] ||
    security_die "SBOM_EMPTY"

  docker run --rm     --user "$HOST_UID:$HOST_GID"   --tmpfs /tmp:rw,nosuid,nodev,mode=1777     --group-add "$DOCKER_SOCKET_GID"     --volume /var/run/docker.sock:/var/run/docker.sock     --volume "$SECURITY_OUTPUT_DIR:/output:rw"     "$TRIVY_IMAGE" image   --db-repository "$TRIVY_DB_REPOSITORY"     --cache-dir /output/trivy-cache     --scanners vuln     --severity HIGH,CRITICAL     --exit-code 1     --format json     --output "/output/$target.trivy.json"     "$image_reference" ||
    security_die "IMAGE_VULNERABILITY_SCAN_FAILED"
  [[ -s "$SECURITY_OUTPUT_DIR/$target.trivy.json" ]] ||
    security_die "IMAGE_SCAN_REPORT_EMPTY"
done

docker run --rm \
  --user "$HOST_UID:$HOST_GID" \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --volume "$REPOSITORY_ROOT:/repo:ro" \
  --volume "$SECURITY_OUTPUT_DIR:/output:rw" \
  "$TRIVY_IMAGE" config \
  --checks-bundle-repository "$TRIVY_CHECKS_REPOSITORY" \
  --cache-dir /output/trivy-cache \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --format json \
  --output /output/config.trivy.json \
  /repo ||
  security_die "CONFIGURATION_SCAN_FAILED"
[[ -s "$SECURITY_OUTPUT_DIR/config.trivy.json" ]] ||
  security_die "CONFIGURATION_SCAN_REPORT_EMPTY"

jq -nc   --argjson secret_findings "$(jq 'length' "$SECURITY_OUTPUT_DIR/gitleaks.json")"   --argjson backend_packages "$(jq '[.packages[]?] | length' "$SECURITY_OUTPUT_DIR/backend.spdx.json")"   --argjson frontend_packages "$(jq '[.packages[]?] | length' "$SECURITY_OUTPUT_DIR/frontend.spdx.json")"   '{
    status:"ok",
    secret_findings:$secret_findings,
    sbom_packages:{backend:$backend_packages,frontend:$frontend_packages},
    high_or_critical_vulnerabilities:0,
    high_or_critical_misconfigurations:0
  }'
