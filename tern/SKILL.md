---
name: tern
description: "Control Tern terminal sessions, tabs, blocks, remote hosts, and cross-block headed peer agents (IRC channels). Use when the user mentions Tern, manages terminal layouts/blocks/remote hosts, or coordinates independent headed agent sessions across blocks."
---

# Tern

Tern organizes terminals and native views into **Window (`--window KEY`) → Session (`SESSION`) → Tab (`tab N`) → Block (`BLOCK`)**, backed by a persistent daemon (`$XDG_RUNTIME_DIR/tern/daemon.sock`).

## 1. Context & Addressing

Managed blocks inherit:
- `TERN_PANE`: Numeric ID of the calling block (use `"$TERN_PANE"` for self; `@focused` tracks whichever block the user is viewing).
- `TERN_PANE_SOCKET` / `TERN_DAEMON_SOCKET`: Daemon Unix socket path.
- `TERN_WINDOW_KEY`: Window key (`""` for first window, `"2"`, etc.).
- `TERN_IDENTITY`: Client auth hop chain JSON (`tern whoami --json`).

> **Terminology (`Block` vs `pane`)**: User-facing concepts, CLI selectors, and `tern ls --json` use **Block**. Underlying env vars (`$TERN_PANE`, `$TERN_PANE_SOCKET`), `tern inspect --json` (`.panes[]`, `.pane`), `tern process --json` (`.pane`), and `tern events` (`pane_*`) retain the literal `pane` field name.

Outside a Tern block (e.g. over SSH), `tern` commands still work against the host's running daemon (`TERN_PANE` is unset—pass explicit selectors). Always invoke `tern` with a subcommand (bare `tern` opens a new GUI window/tab).

- **Window resolution**: `--window KEY` > window holding `$TERN_PANE` > `$TERN_WINDOW_KEY` > first window (`""`).
- **`SESSION` selector**: Numeric `id` or exact `name` (e.g. `Default`). Unattached sessions appear in `.detached`.
- **`BLOCK` selector**: Pass a non-empty numeric ID in scripts (`""` matches every block title and errors); also accepts `@focused`, title/program substring, or `SESSION/BLOCK`.

## 2. CLI Reference

All commands accept `[--json] [--window KEY]`.
`LAUNCH` args for `new`/`split`: `[--cwd DIR] [--keep-open] [--end-on-success] [-- COMMAND...]`.
- **Flag ordering rule**: `--json`, `--window KEY`, `--cwd`, `--keep-open`, `--end-on-success` **MUST precede `-- COMMAND...`** (anything after `--` is passed to `COMMAND`).
- **Auto-close rule**: A block launched with `-- COMMAND...` closes automatically on exit `0` unless `--keep-open` is set (non-zero exit stays open).

### Inspection
- `tern ls --json` → `{"sessions":[{"id","name","shown","tabs":[{"id","number","name","shown","zoomed","blocks":[{"id","title","cwd","program","args","command","cols","rows","exited","keep_open","focused","live"}],"splits"}]}],"detached":[...]}`
- `tern inspect --json` → `ls` fields + `.panes[]` (`{"pane","program","args","cwd","cols","rows","width","height","exited","identity","keep_open","title","followed","quiet_ms","working"}`) + `.clients[]` (`{"conn","window","identity","kind","since"}`)
- `tern process BLOCK --json` → `{"pane","child":{"pid","name","argv","cwd"},"group":<pgid>,"foreground":{"pid","name","argv","cwd"}}` (`.child.pid == .foreground.pid` means shell is idle at prompt)
- `tern whoami --json` → `{"hops":[{"principal","method","from","host","user"}]}`
- `tern events [--filter all|client_connected|client_left|pane_spawned|pane_resized|pane_closed|pane_exited|layout_changed|title_changed|cwd_changed|bell]` (streams JSONL)

### Layout & Lifecycle
`new` and `split` print bare `<block_id>` by default, or `{"session","tab","block"}` with `--json`.
- `tern new session NAME [LAUNCH]` — creates session + tab and switches window to it.
- `tern new tab [SESSION] [LAUNCH]` — creates tab in `SESSION` (default: shown session) and switches to it.
- `tern split BLOCK right|down [LAUNCH]` — splits `BLOCK` (`right` = Row, `down` = Col) **without stealing focus**.
- `tern move BLOCK below|above|left-of|right-of TARGET | tab N | new-tab`
- `tern pip BLOCK [--over TARGET] [--corner tl|tr|bl|br]` / `tern dock BLOCK [left|right|up|down]`
- `tern rename SESSION|BLOCK NAME` (`""` resets custom tab name to follow block title)
- `tern keep-open BLOCK on|off`
- `tern focus BLOCK` — switches window/session/tab to focus `BLOCK`.
- `tern close BLOCK` / `tern kill session SESSION` — terminates immediately without confirmation.

### Execution, Sync & Capture
- `tern run BLOCK COMMAND...` — types `COMMAND...` + Enter.
- `tern send BLOCK keys COMBO...` — keys: `enter`, `escape`, `tab`, `space`, `backspace`, `delete`, `insert`, `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`, `menu`; mods: `ctrl+`, `alt+`, `shift+`, `cmd+`/`super+` (e.g. `ctrl+c`, `shift+tab`).
- `tern send BLOCK text TEXT` (no Enter) | `tern send BLOCK paste TEXT` (bracketed paste; use for multi-line input/prompts).
- `tern send BLOCK mouse press|release|move COL ROW [--button left|middle|right|wheel-up|wheel-down|wheel-left|wheel-right] [--mods ...]`
- `tern wait BLOCK [--until exit|prompt|idle=MS] [--timeout SECS]` → `{"block","status":<int|null>}` (exit status `124` on timeout).
  - `exit` (default): root process exits.
  - `prompt`: shell emits OSC 133 prompt mark (**use right after spawning a shell block and after `tern run`**).
  - `idle=MS`: output quiet for `MS` ms (use for TUI apps or remote `ssh` shells lacking OSC 133).
- `tern capture BLOCK [--html|--ansi] [--scrollback] [--surfaces]` → `{"block","text"}`
  - **`--surfaces` is mandatory** when reading agents or command-lens views that render TSP/ACP surfaces (the raw terminal grid underneath is blank).

### Native Blocks
- `tern open [--split right|down | --tab | --preview] [--wait] PATH[:LINE[:COL]]...`
- `tern db PATH|--project FILE [--read-only] [--sql FILE]... [--table T] [--import-csv FILE]... [--split right|down | --tab]`
- `tern browser JSON [--timeout SECS]` (run `tern browser --help` only when automating native browser blocks).

## 3. Workflows

### A. Running Commands & Lightweight Layout
Decide layout in one step from `tern ls --json` and proceed directly to the task:
- Cap any single row or column at 2 blocks: for a lead agent + subagents, keep the lead on the left and stack subagents vertically on the right; for peer agents, form a 2x2 (up to 3x3) grid, and open a new tab (`tern new tab`) beyond that.
- Co-locate closely collaborating blocks into the same tab when space allows (`tern move BLOCK right-of|below TARGET` or `tern move BLOCK tab N`), or break a block out with `tern move BLOCK new-tab`.
- Preserve manual user layout changes: when the user moves, floats, or reorganizes blocks, continue addressing them in place by numeric ID.

```bash
# Reusable interactive shell (wait for initial prompt before running!)
B=$(tern split "$TERN_PANE" right --cwd "$PWD" --json | jq -r '.block')
tern wait "$B" --until prompt --timeout 10
tern run "$B" "pytest -q"
tern wait "$B" --until prompt --timeout 120
tern capture "$B" --scrollback

# One-shot command (--keep-open prevents auto-close on exit 0 before capture)
B=$(tern split "$TERN_PANE" right --cwd "$PWD" --keep-open --json -- sh -c 'cargo test' | jq -r '.block')
tern wait "$B" --until exit --timeout 300
tern capture "$B" --scrollback
tern close "$B"
```

### B. Multi-Tab Background Setup (Preserving User Focus)
`tern new tab` / `tern new session` switches active view; re-focus `"$TERN_PANE"` afterward if setting up background services:

```bash
B=$(tern new tab --cwd "$PWD" --json | jq -r '.block')
tern rename "$B" "api-server"
tern wait "$B" --until prompt --timeout 10
tern run "$B" "npm run dev"
tern focus "$TERN_PANE"
```

### C. Coordinate Headed Peer Agents
Tern peer agents are full, independent **headed** sessions—heavier than an agent's built-in subagents. Use built-in subagents for ordinary single-session delegation; reach for Tern peer blocks when you need deep workspace/worktree or cross-repo isolation, human visibility and direct interaction with the peer, or ad-hoc coordination between already-running blocks.

- **Default agent**: Unless specified, launch the same agent CLI running in `"$TERN_PANE"` (`tern process "$TERN_PANE" --json` → `.foreground.name`), or a native ACP block (`tern acp <agent> [--model M] [--mode MODE] [--prompt TEXT] [--resume ID|--fork ID|--continue] [--add-dir DIR]`).
- **Read-only inspection**: Check peer liveness with `tern inspect --json` (`.panes[] | {pane, title, working, quiet_ms, exited}`) and `tern capture "$B" --surfaces`—prefer read-only observation over sending status pings into a busy block.
- **Cross-block collaboration (2+ headed blocks)**: Read [`IRC.md`](IRC.md) and use `scripts/irc.py` for channel `join`/`claim`/`say`/`inbox`/`part`, TTL file reservations, Dialog Guard, and 0-token deferred doorbells. Do not paste repeated follow-ups into a busy peer or close a peer's block when it leaves a channel.

```bash
# Launch a headed peer block beside self (without stealing focus)
SELF_AGENT=$(tern process "$TERN_PANE" --json | jq -r '.foreground.name')
B=$(tern split "$TERN_PANE" right --cwd "$PWD" --json | jq -r '.block')
tern wait "$B" --until prompt --timeout 10
tern run "$B" "$SELF_AGENT"
tern wait "$B" --until idle=1500 --timeout 30
# For ongoing collaboration, initialize/join a channel per IRC.md instead of raw polling.
```

### D. Cross-Remote-Host Workflows
1. **Remote host with `tern daemon` (`tern remote serve`)**: Block/session IDs are per-host. Run `tern` over SSH (ensure `~/.local/bin` in `PATH`); changes sync live to any Tern window attached to that host:
   ```bash
   REM_B=$(ssh user@host 'export PATH="$HOME/.local/bin:$PATH"; tern new tab --cwd ~/repo --json' | jq -r '.block')
   ssh user@host "export PATH=\"\$HOME/.local/bin:\$PATH\"; tern wait $REM_B --until prompt --timeout 10 && tern run $REM_B 'cargo test'"
   ```
2. **Remote shell block inside current local tab (`tern ssh`)**: Use `tern ssh` (transfers `xterm-kitty` terminfo and falls back to `xterm-256color`) and synchronize with `--until idle=MS`:
   ```bash
   SSH_B=$(tern split "$TERN_PANE" right --cwd "$PWD" --json -- tern ssh user@host | jq -r '.block')
   tern wait "$SSH_B" --until idle=800 --timeout 15
   tern run "$SSH_B" "uname -a && uptime"
   tern wait "$SSH_B" --until idle=800 --timeout 30
   tern capture "$SSH_B" --scrollback
   ```
3. **Remote host diagnostics & management**: `tern remote hosts` (`~/.config/tern/hosts`), `tern remote discover`, `tern remote doctor [user@]HOST`, `tern remote doctor --host [--mode system|user]`, `tern remote host-key [--user]`. Only run mutating setup commands (`tern remote setup|install|update|trust`) when explicitly asked.

## 4. Safety Rules
- Only close or kill blocks, tabs, and sessions that you created for the current task, unless the user explicitly asks.
- Keep `tern-remote.service` and `tern daemon` running at all times.
