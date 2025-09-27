# AtlasAgents — Requirements

## Current Status (Updated: Sep 27, 2024)

### ✅ Completed:
1. **Core Orchestrator**: State machine, job management, database layer
2. **Agent Framework**: Base classes, factory pattern, role-based agents
3. **LLM Integration**: Ollama support with streaming, timeout handling
4. **Pipeline Stages**: PLAN → SPEC → CODE working end-to-end
5. **CLI**: Basic commands (init, switch, run, approve, status, list)
6. **Requirements Integration**: Agents now receive actual project requirements
7. **File Generation**: CODE stage creates actual files in src/
8. **Logging System**: Comprehensive logging with rotation
9. **Bug Fixes**:
   - Async/threading conflicts resolved (converted to sync)
   - File parsing regex fixed for various LLM output formats
   - CLI progress monitoring fixed

### 🚧 In Progress:
- **REVIEW Stage**: Basic structure exists, needs iteration logic

### 📋 Next Steps:
1. **Review-Code Iteration Loop**:
   - If review finds issues → update review.md with required changes
   - Transition back to CODE stage with review feedback
   - Continue until review approves

2. **MCP Integration**: Currently using mock mode
3. **Telegram Integration**: Approval system exists but uses CLI
4. **Git Integration**: Checkpointing and branching not implemented
5. **Testing**: Unit tests for critical components

# AtlasAgents — Requirements 

## 0) Scope

A local-first, multi-agent coding system that uses **Model Context Protocol (MCP)** tools to perform capabilities such as filesystem access, database access, HTTP fetch, and Git operations. Human approval gates occur in a single **Telegram** group. Work is organized into per-project **workspaces** stored on disk and versioned with Git.

---

## 1) Core Components

1. **Orchestrator (Python)**

   * Runs agent graph and state machine.
   * Hosts MCP **client** and tool **registry** with trust/approval policies.
   * Integrates with Telegram (inline buttons) for approvals.
   * Persists state (SQLite initially; Postgres optional).

2. **Agents (roles)**

   * **Planner → Spec-Writer → Coder → Reviewer** (+ optional PM).
   * Agents call tools exclusively via MCP through the Orchestrator.
   * Each role has an I/O contract and a fixed artifact format.

3. **MCP Servers (local)**

   * Filesystem (root-scoped to the active workspace).
   * SQLite (read/write, optional Postgres later).
   * Git (local repo operations).
   * HTTP/Fetch (optional; disabled by default).

4. **Telegram UI**

   * One group for all projects.
   * Messages contain stage summaries, diffs/previews, and **Approve / Revise / Stop / Restore** buttons.

5. **Git (local)**

   * Branch-based flow; merges only after approval.
   * Shadow checkpoints before any mutating write.

---

## 2) Workspace Layout

```
/atlas/
  orchestrator/
  templates/
  ~/.atlas/
    ATLAS.md                  # global memory
    settings.json             # model + trust + defaults
    history/<project_hash>/   # checkpoints
  workspaces/
    <project>/
      .atlas/ATLAS.md         # project/memory
      README.md
      requirements.yaml
      docs/
      src/
      .internal/
        diffs/
        prs/
        logs/
```

---

## 3) State Machine

Stages: `IDEA → PLAN → SPEC → CODE → REVIEW → DONE`
Control states: `HOLD`, `STOPPED`, `ERROR`

* Each stage **blocks** on approval.
* Stage transitions only via Orchestrator events (no agent self-advance).

---

## 4) Data Persistence (SQLite → Postgres-ready)

### Tables

* `projects(id PK, name, workspace_path, status, created_at, updated_at)`
* `jobs(id PK, project_id FK, stage ENUM, agent ENUM, input_ref TEXT, output_ref TEXT, created_at, updated_at)`
* `approvals(id PK, job_id FK, status ENUM('pending','approved','revise','stopped'), reason TEXT, actor TEXT, created_at)`
* `messages(id PK, project_id FK, role ENUM('user','system','agent','tool','orchestrator','telegram'), content TEXT, meta JSON, created_at)`
* `artifacts(id PK, job_id FK, path TEXT, type TEXT, sha TEXT, created_at)`
* `tool_calls(id PK, job_id FK, server TEXT, tool TEXT, params JSON, preview JSON, executed BOOLEAN, result JSON, created_at)`
* `checkpoints(id PK, project_id FK, ref TEXT, created_at)`

(For Postgres: add `vectors` when pgvector is enabled later; not required now.)

---

## 5) Configuration

### `~/.atlas/settings.json`

```json
{
  "models": {
    "default": "local_gemma",
    "per_agent": {
      "planner": "local_gemma",
      "spec_writer": "local_gemma",
      "coder": "local_qwen",
      "reviewer": "local_qwen"
    },
    "providers": {
      "local_gemma": {"type": "ollama", "model": "gemma2:latest", "url": "http://localhost:11434"},
      "local_qwen":  {"type": "ollama", "model": "qwen2.5:latest", "url": "http://localhost:11434"},
      "api_gpt4o":   {"type": "openai", "model": "gpt-4o-mini"}
    }
  },
  "trust": {
    "default": "deny",
    "allow": {
      "planner":   ["fs.read", "git.branch.list"],
      "spec":      ["fs.read", "fs.write.preview"],
      "coder":     ["fs.write.preview", "git.branch.create", "git.diff"],
      "reviewer":  ["git.diff", "fs.write.preview"]
    },
    "require_approval": ["*.write*", "git.*merge*", "git.*push*", "sql.write*"]
  },
  "telegram": {"group_id": "<REDACTED>"},
  "limits": {"max_files_per_patch": 20, "max_patch_kb": 256}
}
```

### `atlas.config.yaml` (MCP transports)

```yaml
mcp:
  transports:
    - name: filesystem
      type: stdio
      cmd: ["uvx","modelcontextprotocol-servers","filesystem"]
      env: { ROOT: "/abs/path/to/workspaces/current" }

    - name: sqlite
      type: stdio
      cmd: ["uvx","modelcontextprotocol-servers","sqlite"]
      env: { SQLITE_PATH: "/abs/path/to/atlas.db" }

    - name: git
      type: stdio
      cmd: ["uvx","mcp-server-git"]
      env: { REPO_PATH: "/abs/path/to/workspaces/current" }

    - name: fetch
      type: http
      url: "http://localhost:8822"
      enabled: false
```

---

## 6) Agent Role Contracts

### 6.1 Planner

* **Input:** `README.md`, `requirements.yaml`, `.atlas/ATLAS.md` (global+project), prior stage summaries.
* **Output artifacts:**

  * `docs/plan.md` (scope, tasks, folder tree, risks, questions).
* **Tool permissions:** `fs.read`, `git.branch.list`, `fs.write.preview` (docs only).

### 6.2 Spec-Writer

* **Input:** `plan.md`, repo scan (read-only).
* **Output artifacts:**

  * `docs/spec.md` (API/component contracts, data flow).
  * `docs/tasks.json` (atomic tasks). JSON schema below.
* **Tool permissions:** `fs.read`, `fs.write.preview` (docs only).

`docs/tasks.json` schema:

```json
{
  "type":"object",
  "properties":{
    "tasks":{"type":"array","items":{
      "type":"object",
      "required":["id","title","files","acceptance"],
      "properties":{
        "id":{"type":"string"},
        "title":{"type":"string"},
        "desc":{"type":"string"},
        "files":{"type":"array","items":{"type":"string"}},
        "acceptance":{"type":"array","items":{"type":"string"}}
      }
    }}
  },
  "required":["tasks"]
}
```

### 6.3 Coder

* **Input:** `spec.md`, `tasks.json`, allowed file list.
* **Output artifacts:**

  * Feature branch `feat/<slug>`.
  * Code changes + `docs/commit_plan.md` + `docs/test_notes.md`.
* **Tool permissions:** `fs.read`, `fs.write.preview`, `git.branch.create`, `git.diff`.
* **Mutations require approval** (diff preview + checkpoint).

### 6.4 Reviewer

* **Input:** Diff of feature branch vs `main`, `spec.md`.
* **Output artifacts:**

  * `docs/review.md` (summary, inline notes).
  * Optional **small patch** via `fs.write.preview`.
* **Tool permissions:** `git.diff`, `fs.write.preview` (docs or trivial nits).

### 6.5 PM (optional)

* **Input:** stage status, `tasks.json`.
* **Output:** Telegram summaries, ETA text, blockers file `docs/status.md`.
* **Tool permissions:** `fs.read`, `fs.write.preview` (docs only).

---

## 7) MCP Tool Contracts (required)

> **All mutating tools must support a preview path** returning a unified diff or structured preview; final execution only occurs after approval.

### 7.1 Filesystem (prefix `fs.`)

* `fs.list(dir, glob?) -> { entries: [ {path, type, size} ] }`
* `fs.read(path, start_line?, end_line?) -> { content, sha }`
* `fs.write.preview(path, new_content, mode: "create"|"overwrite"|"append", base_sha?) -> { patch, stats, tool_call_id }`
* `fs.replace.preview(path, old_string, new_string, occurrences: "first"|"all", context:{before:int,after:int}) -> { patch, matches, tool_call_id }`

  * **Refinement**: if `old_string` not found, server returns `suggested_old_strings:[...]` with best matches; Orchestrator will re-issue preview using suggestion (still needs approval).
* `fs.apply_patch(tool_call_id) -> { applied: true, files_changed, new_shas }`
* Constraints:

  * All paths must resolve under the configured **ROOT**.
  * Max files per patch and patch size enforced by Orchestrator (`settings.json.limits`).

### 7.2 Git (prefix `git.`)

* `git.branch.list() -> { branches:[name] }`
* `git.branch.create(name, from="main") -> { name }`
* `git.diff(base, head, paths?) -> { patch }`
* `git.stage(paths:[...]) -> { staged:[...] }`
* `git.commit(message, author) -> { commit_sha }`
* `git.merge.preview(base, head) -> { patch, conflicts? }`
* `git.merge.apply(tool_call_id) -> { merged_into: base, commit_sha }`
* `git.push.preview(remote, branch) -> { summary }`  *(disabled by default)*
* `git.push.apply(tool_call_id) -> { pushed:true }` *(approval required)*

### 7.3 SQLite (prefix `sql.`)

* `sql.query(sql, params?) -> { rows, columns }`
* `sql.write.preview(sql, params?) -> { summary, affected_tables }`
* `sql.write.apply(tool_call_id) -> { rowcount }`
* Defaults: **read-only** unless explicitly enabled per role.

### 7.4 Fetch/HTTP (prefix `fetch.`) *(optional, default disabled)*

* `fetch.get(url, headers?) -> { status, content_type, body_md_or_json }`
* **No cross-write effects**; adhere to content length/timeouts from settings.

---

## 8) Approval & Telegram Integration

### 8.1 Mutating Operation Flow

1. Agent requests a mutating tool → **preview** generated (`tool_call_id` issued).

2. Orchestrator creates a **checkpoint** (shadow Git) if none exists for current stage.

3. Orchestrator posts to Telegram:

   * Title: `[Stage][Agent][Tool]`
   * Body: summary, files touched / tables affected.
   * Attachment: unified diff or SQL preview (truncated + downloadable file).
   * Buttons: **Approve**, **Revise**, **Stop**, **Restore**.

4. On **Approve** → Orchestrator replays `*.apply(tool_call_id)` and logs result.

5. On **Revise** → reason is appended to agent input; stage remains the same.

6. On **Stop** → stage transitions to `HOLD` or `STOPPED`.

7. On **Restore** → revert to last checkpoint (files and index), post confirmation.

### 8.2 Telegram Callback Payload (JSON)

```json
{
  "action": "approve|revise|stop|restore",
  "job_id": "<uuid>",
  "tool_call_id": "<uuid>",
  "reason": "<string|null>",
  "user": "<telegram_username>"
}
```

---

## 9) Checkpointing

* **Create** a checkpoint (hidden Git repo under `~/.atlas/history/<project_hash>/`) before the first mutation of each stage.
* **Restore** reverts workspace files to checkpoint and clears staged changes.
* Log checkpoint ref in `checkpoints.ref` and link it in Telegram messages.

---

## 10) Model Router (interface)

```ts
generate({
  agent: "planner"|"spec_writer"|"coder"|"reviewer",
  system?: string,
  prompt: string,
  temperature?: number,
  stop?: string[],
  max_tokens?: number
}) => { text: string, usage: {input: number, output: number}, model_id: string }
```

* Provider backends: `ollama`, `openai`, `anthropic`, `vllm` (extensible).
* Per-agent model selection from `~/.atlas/settings.json`.
* Optional **context caching** when provider supports it (API) — not required for local models.

---

## 11) Prompt Context & Memory

* **ATLAS.md** hierarchy:

  * Global: `~/.atlas/ATLAS.md`
  * Project: `workspaces/<project>/.atlas/ATLAS.md`
  * (Optional) Module: any subfolder `.atlas/ATLAS.md`
* **ContextBuilder rules:**

  * Planner/Spec: include global + project ATLAS + README + requirements.
  * Coder: include `spec.md`, `tasks.json`, ATLAS snippets, and a **file list** (not full file contents unless needed; use `fs.read` with line windows).
  * Reviewer: include diff + `spec.md` summary.
* Command to refresh memory index: `orchestrator.memory.refresh(project_id)` (re-reads ATLAS files; no embeddings required).

---

## 12) CLI Commands (Orchestrator)

* `atlas init <project>` → scaffold workspace.
* `atlas switch <project>` → set active project + reconfigure MCP ROOT/REPO\_PATH.
* `atlas run <stage|agent>` → enqueue a job for current project.
* `atlas status` → print project stage, open approvals, active checkpoints.
* `atlas restore <checkpoint_ref>` → restore immediately (sends Telegram notice).

---

## 13) Constraints & Limits

* All filesystem operations must resolve under workspace root.
* Mutations: max `limits.max_files_per_patch`, `limits.max_patch_kb`, and per-stage **one open approval** at a time.
* No shell execution and no browser automation in MVP (tools present but disabled unless explicitly turned on in config).
* Network: HTTP fetch disabled by default.

---

## 14) Error Handling & Retries

* Tool server timeout → mark job `ERROR`, post Telegram with **Retry** button.
* Diff too large → split patch by directory or file; request multiple approvals.
* Git conflicts on merge.preview → block and require human revision or agent to rebase (with preview).

---

## 15) Logging & Audit

* Log every prompt/completion (`messages` table, `meta` includes model\_id and token usage).
* Log all tool calls with serialized params, preview, and final result.
* Save artifacts to `workspaces/<project>/.internal/` and register in `artifacts` table.
* Include Telegram message IDs in `messages.meta`.

---

## 16) Acceptance Criteria

1. **MCP wiring**

   * Orchestrator connects to configured MCP servers via `atlas.config.yaml`.
   * Filesystem root enforcement is verified with an attempted path escape (must fail).

2. **Diff-first writes**

   * `fs.write.preview` returns a unified diff for edits and creates.
   * Approval flow applies patch and updates file SHAs.

3. **Replace with refinement**

   * `fs.replace.preview` suggests alternatives when `old_string` not found.
   * A second preview using a suggestion succeeds.

4. **Git flow**

   * Coder can create a feature branch, produce diff, and on approval the merge is applied via `git.merge.apply`.
   * Shadow checkpoint created before first mutation; **Restore** brings the repo back.

5. **Telegram approvals**

   * Messages show summary + diff, and buttons trigger the correct actions.
   * Approvals change stage state and persist an `approvals` row.

6. **Role contracts**

   * Planner outputs `docs/plan.md`; Spec-Writer outputs `docs/spec.md` and `docs/tasks.json` (validates against schema); Coder writes code only in `src/`; Reviewer outputs `docs/review.md`.

7. **Persistence**

   * All jobs, tool calls, approvals, and artifacts are persisted and queryable.

8. **Safety**

   * Mutating DB and Git push operations require approval and are denied if disabled in `settings.json`.

---

## 17) Deliverables

* **Source tree** with Orchestrator, MCP client integration, role agents, and Telegram bot.
* **Config files**: `~/.atlas/settings.json`, `atlas.config.yaml`.
* **DB migrations** for SQLite (and Postgres scripts, optional).
* **Unit tests** for:

  * Path confinement,
  * Diff preview generation and application,
  * Replace-refinement path,
  * Checkpoint/restore,
  * Telegram callback handling.
* **Example workspace** with a minimal project demonstrating the full PLAN→SPEC→CODE→REVIEW flow.

---

## 18) Security Defaults

* Deny-by-default tool registry; explicit allow-lists per role.
* Disabled `git.push.*` and `sql.write.*` unless enabled in settings.
* All servers run locally; no secrets persisted in repo; `.env` used for tokens (if any).

---