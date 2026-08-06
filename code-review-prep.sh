#!/bin/bash
_GSD_SHIM_NAME="gsd-tools.cjs"; _GSD_RUNTIME_ROOT="${RUNTIME_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; GSD_TOOLS="${_GSD_RUNTIME_ROOT}/gsd-core/bin/${_GSD_SHIM_NAME}"; if [ -f "$GSD_TOOLS" ]; then gsd_run() { node "$GSD_TOOLS" "$@"; }; elif [ -f "${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}" ]; then GSD_TOOLS="${ANTIGRAVITY_CONFIG_DIR:-$HOME/.gemini/antigravity}/gsd-core/bin/${_GSD_SHIM_NAME}"; gsd_run() { node "$GSD_TOOLS" "$@"; }; fi

PHASE_ARG="1"
INIT=$(gsd_run query init.phase-op "${PHASE_ARG}")
if [[ "$INIT" == @file:* ]]; then INIT=$(cat "${INIT#@file:}"); fi
PADDED_PHASE=$(echo "$INIT" | jq -r '.padded_phase')
PHASE_DIR=$(echo "$INIT" | jq -r '.phase_dir')

# check_config_gate
EXECUTE_POST_HOOKS_JSON=$(gsd_run loop render-hooks execute:post --raw)
ACTIVE=$(echo "$EXECUTE_POST_HOOKS_JSON" | jq '[.[] | select(.kind == "step" and .ref.skill == "code-review")] | length')
if [ "$ACTIVE" -eq 0 ]; then
  echo "Code review skipped (code-review capability inactive)"
  exit 0
fi

# resolve depth
CONFIG_DEPTH=$(gsd_run query config-get workflow.code_review_depth 2>/dev/null || echo "")
REVIEW_DEPTH="${CONFIG_DEPTH:-standard}"

# compute file scope
SUMMARIES=$(ls "${PHASE_DIR}"/*-SUMMARY.md 2>/dev/null)
REVIEW_FILES=()

if [ -n "$SUMMARIES" ]; then
  for summary in $SUMMARIES; do
    EXTRACTED=$(node -e "
      const fs = require('fs');
      const content = fs.readFileSync('$summary', 'utf-8');
      const match = content.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---/);
      if (!match) { process.exit(0); }
      const yaml = match[1];
      const files = [];
      let inSection = null;
      for (const line of yaml.split('\n')) {
        if (/^\s+created:/.test(line)) { inSection = 'created'; continue; }
        if (/^\s+modified:/.test(line)) { inSection = 'modified'; continue; }
        if (/^\s*[\w-]+:/.test(line) && !/^\s*-/.test(line)) { inSection = null; continue; }
        if (inSection && /^\s+-\s+(.+)/.test(line)) {
          let raw = line.match(/^\s+-\s+(.+)/)[1].trim();
          raw = raw.replace(/^['\"]|['\"]$/g, '');
          raw = raw.replace(/\s+\([^)]*\)\s*$/, '');
          raw = raw.split(/\s+—\s/)[0].trim();
          const KNOWN_EXTENSIONLESS_BUILD_FILES = new Set([
            'dockerfile', 'containerfile', 'makefile', 'justfile', 'procfile',
          ]);
          const hasExtension = /\.[A-Za-z0-9]+$/.test(raw);
          const basename = raw.split('/').pop().toLowerCase();
          if (hasExtension || KNOWN_EXTENSIONLESS_BUILD_FILES.has(basename)) {
            files.push(raw);
          }
        }
      }
      if (files.length) console.log(files.join('\n'));
    " 2>/dev/null)
    
    if [ -n "$EXTRACTED" ]; then
      while IFS= read -r file; do
        if [ -n "$file" ]; then
          REVIEW_FILES+=("$file")
        fi
      done <<< "$EXTRACTED"
    fi
  done
fi

PHASE_COMMITS=$(git log --oneline --all --grep="${PADDED_PHASE}" --format="%H" 2>/dev/null)
DIFF_BASE=""
if [ -n "$PHASE_COMMITS" ]; then
  DIFF_BASE=$(echo "$PHASE_COMMITS" | tail -1)^
  if ! git rev-parse "${DIFF_BASE}" >/dev/null 2>&1; then
    DIFF_BASE=$(echo "$PHASE_COMMITS" | tail -1)
  fi
fi

if [ ${#REVIEW_FILES[@]} -eq 0 ]; then
  if [ -n "$DIFF_BASE" ]; then
    DIFF_FILES=$(git diff --name-only "${DIFF_BASE}..HEAD" -- . \
      ':!.planning/' ':!ROADMAP.md' ':!STATE.md' \
      ':!*-SUMMARY.md' ':!*-VERIFICATION.md' ':!*-PLAN.md' \
      ':!package-lock.json' ':!yarn.lock' ':!Gemfile.lock' ':!poetry.lock' 2>/dev/null)

    while IFS= read -r file; do
      [ -n "$file" ] && REVIEW_FILES+=("$file")
    done <<< "$DIFF_FILES"
  fi
elif [ -n "$DIFF_BASE" ]; then
  DIFF_FILES=$(git diff --name-only "${DIFF_BASE}..HEAD" -- . \
    ':!.planning/' ':!ROADMAP.md' ':!STATE.md' \
    ':!*-SUMMARY.md' ':!*-VERIFICATION.md' ':!*-PLAN.md' \
    ':!package-lock.json' ':!yarn.lock' ':!Gemfile.lock' ':!poetry.lock' 2>/dev/null)

  MISSING_FROM_SUMMARY=()
  while IFS= read -r file; do
    [ -z "$file" ] && continue
    if printf '%s\n' "${REVIEW_FILES[@]}" | grep -Fxq -- "$file" 2>/dev/null; then
      :
    else
      MISSING_FROM_SUMMARY+=("$file"); REVIEW_FILES+=("$file")
    fi
  done <<< "$DIFF_FILES"
fi

EXPANDED_FILES=()
for file in "${REVIEW_FILES[@]}"; do
  case "$file" in
    "~/"*) file="${HOME}${file#\~}" ;;
  esac
  EXPANDED_FILES+=("$file")
done
REVIEW_FILES=("${EXPANDED_FILES[@]}")

FILTERED_FILES=()
for file in "${REVIEW_FILES[@]}"; do
  if [[ "$file" == .planning/* ]] || [[ "$file" == ROADMAP.md ]] || [[ "$file" == STATE.md ]] || [[ "$file" == *-SUMMARY.md ]] || [[ "$file" == *-VERIFICATION.md ]] || [[ "$file" == *-PLAN.md ]]; then
    continue
  fi
  FILTERED_FILES+=("$file")
done
REVIEW_FILES=("${FILTERED_FILES[@]}")

EXISTING_FILES=()
DELETED_COUNT=0
for file in "${REVIEW_FILES[@]}"; do
  if [ -f "$file" ]; then
    EXISTING_FILES+=("$file")
  else
    DELETED_COUNT=$((DELETED_COUNT + 1))
  fi
done
REVIEW_FILES=("${EXISTING_FILES[@]}")

DEDUPED=()
while IFS= read -r line; do
  [ -n "$line" ] && DEDUPED+=("$line")
done < <(printf '%s\n' "${REVIEW_FILES[@]}" | sort -u)
REVIEW_FILES=("${DEDUPED[@]}")

echo "DIFF_BASE=$DIFF_BASE"
echo "REVIEW_DEPTH=$REVIEW_DEPTH"
echo "FILES="
for file in "${REVIEW_FILES[@]}"; do
  echo "$file"
done

