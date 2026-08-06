#!/bin/bash
_GSD_SHIM_NAME="gsd-tools.cjs"; _GSD_RUNTIME_ROOT="${RUNTIME_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; GSD_TOOLS="${_GSD_RUNTIME_ROOT}/gsd-core/bin/${_GSD_SHIM_NAME}"; if [ -f "$GSD_TOOLS" ]; then gsd_run() { node "$GSD_TOOLS" "$@"; }; elif [ -f "${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}" ]; then GSD_TOOLS="${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}"; gsd_run() { node "$GSD_TOOLS" "$@"; }; fi

PHASE_ARG="1"
INIT=$(gsd_run query init.phase-op "${PHASE_ARG}")
if [[ "$INIT" == @file:* ]]; then INIT=$(cat "${INIT#@file:}"); fi
PADDED_PHASE=$(echo "$INIT" | jq -r '.padded_phase')
PHASE_NUMBER=$(echo "$INIT" | jq -r '.phase_number')
PHASE_NAME=$(echo "$INIT" | jq -r '.phase_name')
PHASE_DIR=$(echo "$INIT" | jq -r '.phase_dir')
COMMIT_DOCS=$(echo "$INIT" | jq -r '.commit_docs')

REVIEW_PATH="${PHASE_DIR}/${PADDED_PHASE}-REVIEW.md"
REVIEW_DEPTH="standard"

if [ -f "${REVIEW_PATH}" ]; then
  HAS_STATUS=$(REVIEW_PATH="${REVIEW_PATH}" node -e "
    const fs = require('fs');
    const content = fs.readFileSync(process.env.REVIEW_PATH, 'utf-8');
    const match = content.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---/);
    if (match && /status:/.test(match[1])) { console.log('valid'); } else { console.log('invalid'); }
  " 2>/dev/null)
  
  if [ "$HAS_STATUS" = "valid" ]; then
    echo "REVIEW.md created at ${REVIEW_PATH}"
    
    if [ "$COMMIT_DOCS" = "true" ]; then
      gsd_run query commit \
        "docs(${PADDED_PHASE}): add code review report" \
        --files "${REVIEW_PATH}"
    fi
  else
    echo "Warning: REVIEW.md exists but has invalid or missing frontmatter (no status field)."
    echo "Agent may have produced malformed output. Not committing. Review manually: ${REVIEW_PATH}"
  fi
else
  echo "Warning: Agent completed but REVIEW.md not found at ${REVIEW_PATH}. This may indicate an agent issue."
  echo "No REVIEW.md to commit. Please retry with /gsd-code-review ${PHASE_ARG}"
fi

# Present Results
FRONTMATTER=$(REVIEW_PATH="${REVIEW_PATH}" node -e "
  const fs = require('fs');
  const content = fs.readFileSync(process.env.REVIEW_PATH, 'utf-8');
  const match = content.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---/);
  if (match) process.stdout.write(match[1]);
" 2>/dev/null)

STATUS=$(echo "$FRONTMATTER" | grep "^status:" | cut -d: -f2 | xargs)
FILES_REVIEWED=$(echo "$FRONTMATTER" | grep "^files_reviewed:" | cut -d: -f2 | xargs)
CRITICAL=$(echo "$FRONTMATTER" | grep -E "^[[:space:]]*(critical|blocker):" | head -1 | cut -d: -f2 | xargs)
WARNING=$(echo "$FRONTMATTER" | grep "warning:" | head -1 | cut -d: -f2 | xargs)
INFO=$(echo "$FRONTMATTER" | grep "info:" | head -1 | cut -d: -f2 | xargs)
TOTAL=$(echo "$FRONTMATTER" | grep "total:" | head -1 | cut -d: -f2 | xargs)

echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Code Review Complete: Phase ${PHASE_NUMBER} (${PHASE_NAME})"
echo ""
echo "───────────────────────────────────────────────────────────────"
echo ""
echo "  Depth:           ${REVIEW_DEPTH}"
echo "  Files Reviewed:  ${FILES_REVIEWED}"
echo "  "
echo "  Findings:"
echo "    Critical:  ${CRITICAL}"
echo "    Warning:   ${WARNING}"
echo "    Info:      ${INFO}"
echo "    ──────────"
echo "    Total:     ${TOTAL}"
echo ""
echo "───────────────────────────────────────────────────────────────"

if [ "$STATUS" = "clean" ]; then
  echo "✓ No issues found. All ${FILES_REVIEWED} files pass review at ${REVIEW_DEPTH} depth."
  echo ""
  echo "Full report: ${REVIEW_PATH}"
elif [ "$TOTAL" != "0" ] && [ -n "$TOTAL" ]; then
  echo "⚠ Issues found. Review the report for details."
  echo ""
  echo "Full report: ${REVIEW_PATH}"
  echo ""
  echo "Next steps:"
  echo "  /gsd-code-review ${PHASE_NUMBER} --fix  — Auto-fix issues"
  echo "  cat ${REVIEW_PATH}                     — View full report"
  
  if [ "${CRITICAL:-0}" -gt 0 ] || [ "${WARNING:-0}" -gt 0 ]; then
    echo "Top issues:"
    grep -A 3 "^### CR-\|^### BL-\|^### WR-" "${REVIEW_PATH}" | head -n 12
  fi
fi
echo "═══════════════════════════════════════════════════════════════"

