---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - .env.example
  - src/agent/llm.py
  - src/agent/graph.py
  - tests/test_llm_provider.py
autonomous: true
requirements: [QUICK-01]
must_haves:
  truths:
    - LLM_PROVIDER selects Anthropic (default) or Gemini without changing tool/graph wiring
    - Unsupported provider and missing API key fail with clear errors (no network calls)
    - .env loads safely; .env.example documents provider/model keys including empty GOOGLE_API_KEY
  artifacts:
    - path: src/agent/llm.py
      provides: Provider factory (Anthropic/Gemini) from LLM_PROVIDER
      exports: ["build_llm", "get_llm_provider"]
    - path: src/agent/graph.py
      provides: Shared bind_tools + graph using factory LLM
    - path: tests/test_llm_provider.py
      provides: No-network selection / unsupported / missing-key tests
    - path: .env.example
      provides: GOOGLE_API_KEY= plus LLM_PROVIDER / model examples
    - path: pyproject.toml
      provides: langchain-google-genai dependency
  key_links:
    - from: src/agent/graph.py
      to: src/agent/llm.py
      via: build_llm() then bind_tools(tools)
      pattern: "build_llm|bind_tools"
    - from: src/agent/llm.py
      to: LLM_PROVIDER env
      via: os.environ / dotenv
      pattern: "LLM_PROVIDER"
---

<objective>
Add env-driven Anthropic + Gemini LLM selection while keeping Anthropic as the default and preserving existing tool binding and LangGraph behavior.

Purpose: Demo/runtime flexibility across providers without forking the agent graph.
Output: Factory module, dependency + `.env.example` updates, graph wired through the factory, focused no-network unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@src/agent/graph.py
@pyproject.toml
@.env.example
@tests/test_agent_tools.py

<interfaces>
From src/agent/graph.py (current — refactor, do not change graph topology):
- `tools = [graph_bfs_tool, clickhouse_log_tool, qdrant_runbook_tool]`
- `llm_with_tools = llm.bind_tools(tools)`
- Nodes: `agent`, `tools` (ToolNode), `graceful_exit`; same edges/route_condition
- Default Anthropic model today: `claude-3-5-sonnet-20240620`, temperature=0

Target factory contract (create in src/agent/llm.py):
- `get_llm_provider() -> str` — reads `LLM_PROVIDER`, default `"anthropic"` (case-insensitive normalize to lowercase)
- `build_llm()` — returns chat model ready for `.bind_tools(...)`:
  - `anthropic` → `ChatAnthropic` with model from `ANTHROPIC_MODEL` (default `claude-3-5-sonnet-20240620`), requires `ANTHROPIC_API_KEY`
  - `gemini` → `ChatGoogleGenerativeAI` from `langchain_google_genai` with model from `GOOGLE_MODEL` / `GEMINI_MODEL` (prefer `GOOGLE_MODEL`, default a current Gemini flash/pro chat id e.g. `gemini-2.0-flash`), requires `GOOGLE_API_KEY`
  - other values → raise `ValueError` mentioning supported providers
  - missing required key for selected provider → raise `ValueError` (or `EnvironmentError`) naming the missing var — no API call
- Call `load_dotenv()` once at module import (or inside factory) with default path lookup; never override already-set OS env vars (`override=False`)

Dependency: add current PyPI `langchain-google-genai` (`>=4.3.2,<5` or lock to latest stable 4.x compatible with `langchain-core>=1.4.7,<2`).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: No-network LLM provider tests</name>
  <files>tests/test_llm_provider.py</files>
  <behavior>
    - Default / anthropic: with LLM_PROVIDER unset or "anthropic" and ANTHROPIC_API_KEY set, build_llm returns ChatAnthropic (or mock constructor called with expected model); no network
    - Gemini: LLM_PROVIDER=gemini and GOOGLE_API_KEY set selects ChatGoogleGenerativeAI; no network
    - Unsupported: LLM_PROVIDER=openai (or similar) raises clear ValueError; no network
    - Missing key: anthropic without ANTHROPIC_API_KEY and gemini without GOOGLE_API_KEY each raise clear error naming the env var; no network
  </behavior>
  <action>
    Add unittest tests mirroring tests/test_agent_tools.py style. Patch ChatAnthropic and ChatGoogleGenerativeAI constructors (and optionally load_dotenv) so tests never hit the network. Use unittest.mock.patch.dict(os.environ, ..., clear=False) to isolate LLM_PROVIDER and API keys. Import build_llm / get_llm_provider from src.agent.llm (module may not exist yet — write failing tests first, then implement in Task 2). Assert exception messages include the provider name or missing key name as appropriate.
  </action>
  <verify>
    <automated>cd /Users/nsarswat/personal/incimin.io && python -m pytest tests/test_llm_provider.py -x 2>&1 | head -40; test $? -ne 0</automated>
  </verify>
  <done>RED: focused provider/selection/unsupported/missing-key tests exist and fail only because src.agent.llm is missing or incomplete.</done>
</task>

<task type="auto">
  <name>Task 2: Factory, deps, env example, graph wire-up</name>
  <files>src/agent/llm.py, src/agent/graph.py, pyproject.toml, .env.example</files>
  <action>
    1. Add `langchain-google-genai>=4.3.2,<5` to pyproject.toml dependencies (current stable on PyPI is 4.3.2); run `uv sync` so the lock/env picks it up.
    2. Create src/agent/llm.py implementing get_llm_provider + build_llm per the interface contract above. load_dotenv(override=False) safely at import/factory entry. Anthropic remains default when LLM_PROVIDER is unset/empty. Do not call remote APIs in the factory beyond constructing the client object.
    3. Update .env.example: keep existing ANTHROPIC_API_KEY=; add empty `GOOGLE_API_KEY=`; add commented or active example lines for `LLM_PROVIDER=anthropic` (document that anthropic is default), `LLM_PROVIDER=gemini`, `ANTHROPIC_MODEL=claude-3-5-sonnet-20240620`, and `GOOGLE_MODEL=gemini-2.0-flash` (or the chosen default). No real secrets.
    4. Refactor src/agent/graph.py: replace direct ChatAnthropic construction with `llm = build_llm()` from src.agent.llm; keep the same tools list, `llm.bind_tools(tools)`, system prompt, nodes, routing, and compiled `app`. Do not change ToolNode or remaining_steps behavior.
  </action>
  <verify>
    <automated>cd /Users/nsarswat/personal/incimin.io && python -m pytest tests/test_llm_provider.py -x && rg -n "build_llm|bind_tools|LLM_PROVIDER" src/agent/llm.py src/agent/graph.py && rg -n "^GOOGLE_API_KEY=$|^LLM_PROVIDER=|^ANTHROPIC_MODEL=|^GOOGLE_MODEL=" .env.example && rg -n "langchain-google-genai" pyproject.toml</automated>
  </verify>
  <done>Factory selects anthropic/gemini; graph still binds the same three tools; deps and .env.example updated; tests pass without network.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| developer filesystem → process env | `.env` / OS env supply API keys and provider choice |
| agent process → Anthropic/Google APIs | LLM client may call external APIs at runtime (out of scope for unit tests) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Information disclosure | `.env` / `.env.example` | mitigate | Only empty placeholders in `.env.example`; never commit real keys; keep `.env` gitignored |
| T-quick-02 | Elevation / misuse | `LLM_PROVIDER` | mitigate | Allowlist anthropic\|gemini only; reject others with ValueError |
| T-quick-03 | Tampering | pip/uv install `langchain-google-genai` | mitigate | Pin to known PyPI range `>=4.3.2,<5`; official langchain-ai package |
| T-quick-SC | Tampering | package install | accept | Single well-known LangChain integration package; no obscure deps |
</threat_model>

<verification>
- `pytest tests/test_llm_provider.py` passes with constructors mocked (no network)
- `graph.py` still uses one shared `tools` list and `bind_tools`
- Default provider remains Anthropic when `LLM_PROVIDER` unset
</verification>

<success_criteria>
Anthropic and Gemini are selectable via LLM_PROVIDER (Anthropic default); langchain-google-genai is declared; .env loads safely; .env.example documents GOOGLE_API_KEY and provider/model examples; graph/tool behavior unchanged; focused no-network tests cover selection, unsupported provider, and missing keys.
</success_criteria>

<output>
Create `.planning/quick/260806-llm-provider-anthropic-gemini/260806-llm-provider-anthropic-gemini-01-SUMMARY.md` when done
</output>
