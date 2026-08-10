#!/usr/bin/env bash
# This project was developed with assistance from AI tools.
#
# Replaces all occurrences of old cluster apps domains with the current one
# across GitOps manifests. Auto-detects the domain from the logged-in cluster.
#
# Usage:
#   ./scripts/update-cluster-domain.sh              # auto-detect from cluster
#   ./scripts/update-cluster-domain.sh --dry-run     # preview only
#   ./scripts/update-cluster-domain.sh <domain>      # explicit override
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEARCH_DIR="${REPO_ROOT}/infrastructure/gitops"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    shift
fi

if [[ -n "${1:-}" ]]; then
    NEW_DOMAIN="${1}"
else
    if ! command -v oc &>/dev/null; then
        echo "ERROR: oc not found. Install the OpenShift CLI or pass the domain as an argument." >&2
        exit 1
    fi
    if ! oc whoami &>/dev/null; then
        echo "ERROR: Not logged in. Run 'oc login' first or pass the domain as an argument." >&2
        exit 1
    fi
    NEW_DOMAIN=$(oc get ingress.config.openshift.io cluster -o jsonpath='{.spec.domain}')
    echo "Detected cluster domain: ${NEW_DOMAIN}"
fi

echo "Scanning ${SEARCH_DIR} for stale domains..."
mapfile -t DOMAINS < <(
    grep -roh 'apps\.[a-z0-9_-]*\.[a-z0-9]*\.p[0-9]\.openshiftapps\.com' \
        "${SEARCH_DIR}" 2>/dev/null \
    | sort -u \
    | grep -v "^${NEW_DOMAIN}$" || true
)

if [[ ${#DOMAINS[@]} -eq 0 ]]; then
    echo "No stale domains found — all references already use ${NEW_DOMAIN}"
    exit 0
fi

echo ""
echo "Stale domains found:"
for d in "${DOMAINS[@]}"; do
    count=$(grep -rl "${d}" "${SEARCH_DIR}" 2>/dev/null | wc -l | tr -d ' ')
    echo "  ${d}  (${count} files)"
done
echo ""

for OLD in "${DOMAINS[@]}"; do
    FILES=$(grep -rl "${OLD}" "${SEARCH_DIR}" 2>/dev/null || true)
    if [[ -z "${FILES}" ]]; then
        continue
    fi

    echo "Replacing: ${OLD}"
    echo "     With: ${NEW_DOMAIN}"

    echo "${FILES}" | while read -r f; do
        REL_PATH="${f#"${REPO_ROOT}/"}"
        COUNT=$(grep -c "${OLD}" "${f}")
        if [[ "${DRY_RUN}" == "true" ]]; then
            echo "  [dry-run] ${REL_PATH} (${COUNT} occurrences)"
        else
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' "s|${OLD}|${NEW_DOMAIN}|g" "${f}"
            else
                sed -i "s|${OLD}|${NEW_DOMAIN}|g" "${f}"
            fi
            echo "  updated  ${REL_PATH} (${COUNT} occurrences)"
        fi
    done
    echo ""
done

if [[ "${DRY_RUN}" == "true" ]]; then
    echo "Dry run complete. Re-run without --dry-run to apply."
else
    REMAINING=$(grep -roh 'apps\.[a-z0-9_-]*\.[a-z0-9]*\.p[0-9]\.openshiftapps\.com' \
        "${SEARCH_DIR}" 2>/dev/null | sort -u | grep -v "^${NEW_DOMAIN}$" | wc -l | tr -d ' ')
    if [[ "${REMAINING}" -gt 0 ]]; then
        echo "WARNING: ${REMAINING} stale domain(s) still found"
    else
        echo "Done. All references now use ${NEW_DOMAIN}"
    fi
fi