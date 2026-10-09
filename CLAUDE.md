# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BranchNexus is a multi-branch workspace orchestrator for tmux. It lets developers work on multiple git branches simultaneously in tmux panes/windows. Written in TypeScript as an ESM npm package, it targets Node >=18.

## Common Commands

```bash
npm run build          # Compile with tsup (outputs to dist/)
npm run dev            # Watch mode for development
npm run typecheck      # TypeScript strict checking
npm run lint           # ESLint
npm run lint:fix       # ESLint with auto-fix
npm run format         # Prettier formatting
npm run format:check   # Check formatting
npm run test           # Run tests (vitest)
npm run test:watch     # Tests in watch mode
npm run test:coverage  # Coverage report (80% lines/functions/statements, 70% branches)
npm run clean          # Remove dist/
```

Run a single test file: `npx vitest run tests/unit/layouts.test.ts`

## Architecture

The CLI entry point is `ts-src/cli.ts` (Commander.js). The public API is exported from `ts-src/index.ts`.

**Module layout under `ts-src/`:**

- **commands/** — CLI command handlers (`run` is the main command, `config` manages settings)
- **core/** — Orchestrator (main flow), config management (`conf` library storing to `~/.config/branchnexus/config.json`), session management, presets
- **git/** — Git operations via `simple-git`: `WorktreeManager` class for worktree lifecycle, branch listing, clone/fetch
- **github/** — GitHub API client (token via `BRANCHNEXUS_GH_TOKEN` env var)
- **hooks/** — Pre/post command hook execution
- **prompts/** — Interactive prompts via `inquirer` and `@clack/prompts`: setup wizard, repo/branch selection, WSL distro picker, panel config
- **runtime/** — Platform detection (Windows/macOS/Linux), WSL operations, shell command execution
- **tmux/** — tmux bootstrap/installation, layout building (grid/horizontal/vertical), session management
- **types/** — All TypeScript types with Zod schemas for runtime validation (config, errors with exit codes, session, worktree)
- **utils/** — Logger (file + console, levels: debug/info/warn/error) and input validators

## Key Patterns

- **Error handling**: Custom `BranchNexusError` with typed `ExitCode` enum (0-8) and user-facing `hint` field
- **Config validation**: Zod schemas in `ts-src/types/config.ts` define all config shapes; `conf` persists to JSON
- **Cross-platform paths**: Git/worktree code handles POSIX↔Windows path conversion; `isWSL()` detection for WSL environments
- **ESM only**: Package uses `"type": "module"` — use `import`/`export`, not `require`

## Code Style

- Prettier: single quotes, semicolons, 100 char width, 2-space indent, trailing commas (ES5)
- ESLint: strict TypeScript rules — explicit return types required, no implicit any, no floating promises, strict boolean expressions
- `console` usage is allowed (CLI tool)

## Git and PRs

- Only PRs go to `main`. Do each task on a short-lived branch cut from `main`. No direct push, force push, or GitHub auto-merge.
- When CI is fully green, the agent merges its own PR: `gh pr merge --squash --delete-branch` (use `--merge` if squash is not accepted). Never merge on red or pending CI.
- After merge, clean up locally: `git worktree remove` the task's worktree and `git branch -d` the local branch. Never touch worktrees with uncommitted changes or owned by another session.
