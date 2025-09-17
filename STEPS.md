# AtlasAgents Implementation Steps

## Overview
Building a lean MVP of a local-first multi-agent coding system with MCP integration and Telegram approvals.

---

## ✅ Phase 1: Core Orchestrator & State Machine (COMPLETED)

### Completed Steps:
1. **Project Structure & Dependencies** ✅
   - Created directory structure (orchestrator/, templates/, workspaces/)
   - Setup pyproject.toml with dependencies
   - Created __init__.py files and README

2. **Configuration Management** ✅
   - Created config.py with Pydantic models
   - Built settings.json and atlas.config.yaml templates
   - Implemented PathManager for workspace management

3. **Database Layer (SQLite)** ✅
   - Created lean SQLite database (no SQLAlchemy)
   - Implemented all tables (projects, jobs, approvals, messages, etc.)
   - Added CRUD operations

4. **State Machine Core** ✅
   - Defined state enums (IDEA → PLAN → SPEC → CODE → REVIEW → DONE)
   - Built transition rules and validation
   - Implemented job management system
   - Added state persistence

5. **Orchestrator Class** ✅
   - Created main Orchestrator coordinating all components
   - Implemented job scheduling logic
   - Added project context management
   - Built event system for state changes

6. **CLI Interface** ✅
   - Implemented all core commands (init, switch, status, run, list)
   - Added Click framework with Rich output
   - Created entry point script

7. **Logging & Error Handling** ✅
   - Setup structured logging with structlog
   - Created custom exception classes
   - Added graceful shutdown handling
   - Implemented retry logic with circuit breaker

---

## ✅ Phase 2: Basic MCP Integration (COMPLETED)

### Completed Steps:
1. **MCP Connection Manager** ✅
   - Created async MCP client wrapper
   - Implemented persistent connection management
   - Added server startup/shutdown
   - Built health checks

2. **Tool Registry** ✅
   - Created comprehensive tool registry with categorization
   - Implemented automatic tool discovery
   - Added operation type detection (read/write/delete/execute)
   - Built metadata tracking and statistics

3. **Permission System** ✅
   - Implemented orchestrator-level permission checking
   - Integrated trust policy from config
   - Added audit logging for all operations
   - Built permission enforcement with caching

4. **Tool Execution** ✅
   - Created ToolExecutor with database recording
   - Implemented approval state tracking
   - Built simple approval flow (no complex previews)
   - Added CLI commands for approval management

---

## ✅ Phase 3: Simple Agent Framework (COMPLETED)

### Step 1: Base Agent Architecture ✅
- [x] Create abstract base agent class with common interface
- [x] Define agent input/output contracts
- [x] Implement context management for agents
- [x] Add agent lifecycle methods (initialize, execute, cleanup)

### Step 2: Agent-MCP Integration Layer ✅
- [x] Create tool calling interface for agents
- [x] Implement permission-aware tool requests
- [x] Add context injection for tool calls (project_id, job_id)
- [x] Build response handling and error recovery

### Step 3: Mock Agent Implementations ✅
- [x] **Planner Agent**: Returns mock plan.md
- [x] **Spec-Writer Agent**: Returns mock spec.md and tasks.json
- [x] **Coder Agent**: Returns mock code changes
- [x] **Reviewer Agent**: Returns mock review.md
- [x] Each with proper I/O contract validation

### Step 4: Agent Factory & Registry ✅
- [x] Create agent factory for instantiating agents
- [x] Build agent registry for available agents
- [x] Implement agent selection based on stage
- [x] Add agent configuration loading

### Step 5: Integration with Job Executor ✅
- [x] Connect agents to job_manager
- [x] Update JobExecutor to use real agents
- [x] Implement artifact storage from agent outputs
- [x] Add error handling for agent failures

---

## 🔜 Phase 4: Basic Telegram Integration

### Step 1: Telegram Bot Setup
- [ ] Initialize bot with python-telegram-bot
- [ ] Configure webhook/polling
- [ ] Add authentication/group verification

### Step 2: Approval Flow
- [ ] Send approval requests to Telegram
- [ ] Implement inline keyboard with approve/deny buttons
- [ ] Handle button callbacks
- [ ] Update database with decisions

### Step 3: Status Updates
- [ ] Send stage transition notifications
- [ ] Report errors to Telegram
- [ ] Add progress updates for long-running tasks

---

## 🔜 Phase 5: Local Model Integration

### Step 1: Model Router
- [ ] Implement Ollama client integration
- [ ] Create simple prompt/response interface
- [ ] Add model selection logic

### Step 2: Agent Prompts
- [ ] Write basic prompts for each agent role
- [ ] Implement context injection (files, previous outputs)
- [ ] Add output parsing logic

### Step 3: Connect Agents to Models
- [ ] Replace mock responses with LLM calls
- [ ] Add streaming support (optional)
- [ ] Implement token counting

---

## 🔜 Phase 6: Git Safety (MINIMAL)

### Step 1: Git Wrapper
- [ ] Use MCP git server for operations
- [ ] Implement branch creation for features
- [ ] Add basic commit functionality

### Step 2: Simple Checkpoints
- [ ] Create Git commits at stage boundaries
- [ ] Implement basic restore capability
- [ ] Add checkpoint listing

---

## 🔜 Phase 7: MVP Testing & Polish

### Step 1: End-to-End Flow
- [ ] Test full PLAN → SPEC → CODE → REVIEW cycle
- [ ] Fix integration issues
- [ ] Verify approval flow works

### Step 2: Documentation
- [ ] Update SETUP.md with final instructions
- [ ] Create example project walkthrough
- [ ] Add troubleshooting guide

### Step 3: Critical Bug Fixes
- [ ] Fix only blocking issues
- [ ] Ensure core flow works reliably
- [ ] Add minimal error recovery

---

## Deferred (Post-MVP)

- Complex previews (diffs, suggestions)
- Advanced refinement (smart retries)
- Full Git integration (shadow repos, complex merges)
- PM agent
- Context caching
- Vector embeddings
- HTTP fetch tools
- Advanced ATLAS.md memory
- Multi-file patches
- Postgres support

---

## Testing Milestones

1. **After Phase 2** (Current): Basic smoke test
   ```bash
   atlas init testproject
   atlas mcp tools
   atlas mcp test filesystem.read --args '{"path": "README.md"}'
   ```

2. **After Phase 3**: Mock agent integration test

3. **After Phase 5**: Full LLM integration test

4. **After Phase 7**: Complete MVP validation

---

## Progress Summary

- **Completed**: Phases 1-2 (Core system + MCP integration)
- **Current**: Phase 3 (Agent framework)
- **Remaining**: Phases 4-7 (Telegram, LLMs, Git, Polish)
- **Estimated Completion**: ~60% of MVP complete