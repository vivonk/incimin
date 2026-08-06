#!/bin/bash
_GSD_SHIM_NAME="gsd-tools.cjs"; _GSD_RUNTIME_ROOT="${RUNTIME_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; GSD_TOOLS="${_GSD_RUNTIME_ROOT}/gsd-core/bin/${_GSD_SHIM_NAME}"; if [ -f "$GSD_TOOLS" ]; then gsd_run() { node "$GSD_TOOLS" "$@"; }; elif [ -f "${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}" ]; then GSD_TOOLS="${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}"; gsd_run() { node "$GSD_TOOLS" "$@"; }; fi

PHASE_ARG="1"
INIT=$(gsd_run query init.phase-op "${PHASE_ARG}")
if [[ "$INIT" == @file:* ]]; then INIT=$(cat "${INIT#@file:}"); fi
PADDED_PHASE=$(echo "$INIT" | jq -r '.padded_phase')
PHASE_DIR=$(echo "$INIT" | jq -r '.phase_dir')
REVIEW_PATH="${PHASE_DIR}/${PADDED_PHASE}-REVIEW.md"

AGENT_SKILLS_REVIEWER=$(gsd_run query agent-skills gsd-code-reviewer)

DIFF_BASE="1d2cdbda8929a1c99d8775a3bcb399725cfe0743^"
REVIEW_DEPTH="standard"

FILES=$(./code-review-prep.sh | sed -n '/^FILES=/,$p' | tail -n +2)

FILES_TO_READ=""
CONFIG_FILES=""
while IFS= read -r file; do
  [ -z "$file" ] && continue
  FILES_TO_READ+="- ${file}"$'\n'
  CONFIG_FILES+="  - ${file}"$'\n'
done <<< "$FILES"

cat << PROMPT > reviewer-prompt.txt
<files_to_read>
${FILES_TO_READ}
</files_to_read>



<config>
depth: ${REVIEW_DEPTH}
phase_dir: ${PHASE_DIR}
review_path: ${REVIEW_PATH}
diff_base: ${DIFF_BASE}
files:
${CONFIG_FILES}
</config>

Review the listed source files at ${REVIEW_DEPTH} depth. Write findings to ${REVIEW_PATH}.
Do NOT commit the output — the orchestrator handles that.
${AGENT_SKILLS_REVIEWER}
PROMPT

