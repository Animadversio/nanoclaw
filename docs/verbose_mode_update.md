# Verbose Mode Feature

Adds `/verbose`, `/verbose bash`, `/verbose edit`, and `/quiet` commands so agents narrate their progress during long tasks instead of staying silent until the final result.

## What It Does

When verbose mode is active, the agent emits a notification to the channel each time it uses a tool, so you can see what it's doing mid-task:

```
🔧 `python3 nanoclaw_cost.py /data/sessions --plot --output report.png`
📝 Writing `/workspace/group/report.md`
✏️ Editing `/workspace/group/config.yaml`
🤖 Spawning subagent: analyze the CSV file and return summary stats
```

### Levels

| Command | What you see |
|---------|-------------|
| `/verbose` or `!verbose` | All tool calls (Bash, Read, Write, Edit, Grep, Web...) |
| `/verbose edit` or `!verbose edit` | Bash + Write + Edit + subagent spawns (no reads) |
| `/verbose bash` or `!verbose bash` | Bash commands only |
| `/quiet` or `!quiet` | Turn off — final result only |

On **Discord**, `/verbose` is a registered slash command with autocomplete. On other channels (Telegram, Slack, WhatsApp), use the `!` prefix.

The setting is **per-channel** and **persists across restarts**. It is stored as `groups/{folder}/.verbose` with content `all`, `edit`, or `bash`. Delete the file to turn it off manually.

---

## Files Changed

| File | What changed |
|------|-------------|
| `src/index.ts` | `handleVerbosityCommand()` — writes flag, returns confirmation string; text-command interception in `onMessage`; `onVerbosityCommand` wired into `channelOpts` |
| `src/channels/discord.ts` | `DiscordChannelOpts.onVerbosityCommand` callback; `/verbose` slash command registered on `ClientReady`; `InteractionCreate` handler |
| `container/agent-runner/src/index.ts` | `formatToolNotification()` — emoji-formatted tool notifications; verbose flag re-read on every assistant message; `edit`/`bash`/`all` level filtering; verbose system prompt appended |

### Commits (in order)

```
58b55d4  feat: add /verbose, /verbose bash, /quiet commands for mid-task progress
2139b40  fix: accept !verbose/!quiet prefix for Discord compatibility
564cfd5  fix: re-read verbose flag on each tool call to handle mid-session activation
2fbf6ff  fix: truncate bash verbose notification at 150 chars with ellipsis
179a64f  feat: /verbose Discord slash command with all/edit/bash/off levels
<latest>  fix: redact secrets in verbose notifications before truncation
```

---

## Applying to Another NanoClaw Instance

### Step 1 — Add the remote (once)

```bash
git remote add animadversio https://github.com/Animadversio/nanoclaw.git
git fetch animadversio feature/verbose-mode
```

### Step 2 — Cherry-pick the 5 commits

```bash
git cherry-pick 58b55d4^..179a64f
```

If you hit conflicts, see [Resolving Conflicts](#resolving-conflicts) below.

### Step 3 — Rebuild

```bash
# Always required
npm run build
cd container/agent-runner && npm run build && cd ../..

# Docker installs only — rebake the image
./container/build.sh
```

### Step 4 — Restart

```bash
# macOS (launchd)
launchctl kickstart -k gui/$(id -u)/com.nanoclaw

# Linux (systemd)
systemctl --user restart nanoclaw
```

### Step 5 — Test

In any registered channel, send `!verbose` (or `/verbose` on Discord). You should get a confirmation reply. Then give the agent a task involving file edits or bash commands and watch for tool notifications.

---

## Secret Redaction

Verbose notifications strip secrets from Bash commands and WebFetch URLs **before** truncating, so the 150-char limit applies to the already-safe string. Redacted patterns:

| Pattern | Example input | Shown as |
|---------|--------------|----------|
| Anthropic key | `sk-ant-api03-abc...` | `sk-ant-***` |
| OpenAI key | `sk-proj-abc123...` | `sk-***` |
| GitHub tokens | `ghp_abc...`, `gho_abc...`, `github_pat_...` | `ghp_***` etc. |
| HTTP auth headers | `Bearer eyJhbGc...` | `Bearer ***` |
| Flag args | `--token abc123`, `--api-key=xyz` | `--token ***` |
| Env var assignments | `ANTHROPIC_API_KEY=sk-...`, `MY_TOKEN=abc` | `ANTHROPIC_API_KEY=***` |
| URL query params | `?api_key=abc&token=xyz` | `?api_key=***&token=***` |

If a secret slips through (unusual format), open an issue or add a pattern to `SECRET_PATTERNS` in `container/agent-runner/src/index.ts`.

---

## Sharp Edges

### 1. Agent-runner rebuild is mandatory

The notification logic lives in `container/agent-runner/src/index.ts`. The host (`src/index.ts`) forwards notifications to the channel, but they're emitted by the agent-runner process. If you skip `cd container/agent-runner && npm run build`, the old `dist/index.js` runs silently and nothing appears.

### 2. Docker installs need a container rebuild

`AGENT_RUNTIME=local` installs use `container/agent-runner/dist/index.js` directly from disk. **Docker installs bake the agent-runner into the image** — the `dist/` changes won't take effect until you run `./container/build.sh`. Check your `.env` for `AGENT_RUNTIME=docker` to know which mode you're on.

### 3. Discord slash command needs `applications.commands` scope

The `/verbose` slash command is registered via the Discord REST API on `ClientReady`. This requires the bot to be invited with the `applications.commands` OAuth scope. If it was invited without it, registration fails silently with `403 Missing Access` in the logs.

**Fix**: re-invite the bot using a URL that includes `applications.commands` in the scope. You can generate one in the Discord Developer Portal → your app → OAuth2 → URL Generator.

**Workaround if you can't re-invite**: the `!verbose` text commands work without any special scope — only the slash command autocomplete is affected.

### 4. Verbose flag set while agent was already running

The flag is re-read on each tool call (not just at container startup), so changes take effect immediately — even mid-session. This is the fix in commit `564cfd5`. Without it, if you set `!verbose` while an agent was idle-but-alive, the current session would never pick it up.

### 5. Merge conflicts

These files are likely to conflict if you've customized them:

**`src/index.ts`** — look for the `handleVerbosityCommand` function (~line 547) and the `channelOpts` object (~line 582). The key additions are:
- The `handleVerbosityCommand` function returning `Promise<string>` instead of `Promise<void>`
- `edit` level in the level detection
- `onVerbosityCommand` key in `channelOpts`
- The text-command interception in `onMessage` handling `/verbose edit`

**`src/channels/discord.ts`** — look for the `connect()` method. The additions are:
- `onVerbosityCommand?` in `DiscordChannelOpts`
- `REST`, `Routes`, `SlashCommandBuilder` in the imports
- Slash command registration block inside `ClientReady`
- `InteractionCreate` handler before the error handler

**`container/agent-runner/src/index.ts`** — look for the `runQuery()` function. The additions are:
- `SKIP_VERBOSE_TOOLS` set and `formatToolNotification()` function (~line 266)
- Verbose flag read + system prompt append (~line 408)
- Per-message flag re-read and tool notification emission in the SDK event loop

### 6. discord.js version

`REST`, `Routes`, and `SlashCommandBuilder` require **discord.js v14+**. If a machine is pinned to v13, the last commit (`179a64f`) will fail to build. You can skip that commit and still get the core feature (`!verbose` text commands) from the first four commits.

### 7. Pre-enabling verbose for a group

To turn verbose on before the service starts (e.g. in a setup script):

```bash
echo "all" > groups/{folder}/.verbose
# or: echo "bash" > groups/{folder}/.verbose
```

Replace `{folder}` with the group folder name (visible in `groups/` or the DB). The agent-runner reads this file on every tool call.
