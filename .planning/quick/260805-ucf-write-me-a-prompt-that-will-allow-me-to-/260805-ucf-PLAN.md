---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: ["prompt_autonomous.txt"]
autonomous: true
requirements: [QUICK-01]
must_haves:
  truths:
    - User has a clear prompt for autonomous execution
  artifacts:
    - prompt_autonomous.txt
  key_links: []
---

<objective>
Provide a prompt that will allow the user to run the rest of the GSD phases without any manual input, automatically continuing as phases and plans complete.

Purpose: Automate the completion of the remaining phases.
Output: A text file `prompt_autonomous.txt` containing the requested prompt.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Generate Autonomous Prompt</name>
  <files>prompt_autonomous.txt</files>
  <action>Create a file named `prompt_autonomous.txt` in the root directory. In it, write the following prompt that the user can use: "Please run the gsd-autonomous skill to run all remaining phases in the roadmap without any manual input. Automatically iterate through discuss-phase, plan-phase, and execute-phase for each phase. As each plan and phase completes, seamlessly continue to the next one until the entire project roadmap is fully completed." Also mention they can use the `/gsd autonomous` shortcut if available.</action>
  <verify>
    <automated>test -f prompt_autonomous.txt</automated>
  </verify>
  <done>The `prompt_autonomous.txt` file exists and contains the actionable prompt.</done>
</task>

</tasks>

<success_criteria>
A file containing the exact prompt to trigger fully autonomous phase execution is created.
</success_criteria>

<output>
Create `.planning/quick/260805-ucf-write-me-a-prompt-that-will-allow-me-to-/260805-ucf-01-SUMMARY.md` when done
</output>
