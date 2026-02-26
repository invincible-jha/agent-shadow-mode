#!/usr/bin/env bash
# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation
#
# fire-line-audit.sh — Scan all source files for forbidden identifiers.
# Exits 1 if any violations are found. Run in CI before every merge.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FORBIDDEN=(
    "progressLevel"
    "promoteLevel"
    "computeTrustScore"
    "behavioralScore"
    "adaptiveBudget"
    "optimizeBudget"
    "predictSpending"
    "detectAnomaly"
    "generateCounterfactual"
    "PersonalWorldModel"
    "MissionAlignment"
    "SocialTrust"
    "CognitiveLoop"
    "AttentionFilter"
    "GOVERNANCE_PIPELINE"
)

SOURCE_DIRS=(
    "${REPO_ROOT}/python/src"
    "${REPO_ROOT}/typescript/src"
    "${REPO_ROOT}/examples"
)

VIOLATIONS=0

echo "=== Fire Line Audit — agent-shadow-mode ==="
echo "Scanning: ${SOURCE_DIRS[*]}"
echo ""

for term in "${FORBIDDEN[@]}"; do
    for dir in "${SOURCE_DIRS[@]}"; do
        if [ ! -d "$dir" ]; then
            continue
        fi
        matches=$(grep -rn --include="*.py" --include="*.ts" "$term" "$dir" 2>/dev/null || true)
        if [ -n "$matches" ]; then
            echo "VIOLATION: '$term' found:"
            echo "$matches"
            echo ""
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    done
done

if [ "$VIOLATIONS" -eq 0 ]; then
    echo "PASS: No forbidden identifiers found."
    exit 0
else
    echo "FAIL: $VIOLATIONS violation(s) found. Fix before merging."
    exit 1
fi
