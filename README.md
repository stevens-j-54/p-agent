# P. Agent

An always-on AI agent with a persistent identity, memory, and the ability to administer its own GitHub repositories. The agent monitors a Gmail inbox and a Telegram bot for messages from authorised contacts and responds using Claude as its reasoning engine. It can also modify its own codebase by opening pull requests against its upstream repository.

## What it does

- Polls a Gmail inbox and a Telegram bot for messages from authorised contacts
- Processes each message using Claude (Sonnet 4.6) with a full tool-use loop
- Replies in-thread (email) or in-session (Telegram, with persistent history)
- Creates, edits, and manages files across multiple GitHub repositories
- Maintains persistent memory and a self-modifiable identity
- Proposes changes to its own codebase via GitHub pull requests, with CI gating

## Project structure

```
agent.py                  # Main agent loop and EmailAgent class
config.py                 # Environment config and constants
pyproject.toml            # Project metadata and dependencies

utils/
  messages.py             # build_messages() — assembles Claude message arrays
  email_utils.py          # strip_reply_prefix(), extract_body()
  auth.py                 # is_authorized_email_sender(), is_authorized_telegram_user()

prompts/
  system.py               # Composes system prompt from agent-core files
  email.py                # Email message template
  telegram.py             # Telegram message template

services/
  email.py                # Gmail API: polling, parsing, sending replies, thread context
  telegram_service.py     # Telegram Bot API: long-polling, sending messages
  workspace.py            # Git workspace management (file ops + commit/push)
  agent_core.py           # Agent-core repo management (identity, soul, memory)
  github_service.py       # GitHub API: repos, issues, branches, PRs, CI status, fork sync
  git_repo.py             # Base class for git repository operations

tools/
  definitions.py          # Claude tool schemas
  handlers.py             # Tool dispatch table and handler functions

tests/
  test_build_messages.py  # Unit tests for build_messages()
  test_email.py           # Unit tests for strip_reply_prefix()

agent-core/               # Local clone of the agent's configuration repo
  IDENTITY.md             # Character and working style (editable by agent)
  SOUL.md                 # Values and principles (editable by agent)
  MEMORY.md               # Persistent memory across conversations
  telegram_sessions.json  # Persisted Telegram conversation history

repos/                    # Local clones of agent-managed repositories
  workspace/              # Default general-purpose workspace
  <other repos>/          # Additional repos created by the agent
```

## Agent configuration

The agent's behaviour is driven by three files in its `agent-core` repository:

- **IDENTITY.md** — character, tone, and working style
- **SOUL.md** — values and principles that guide decisions
- **MEMORY.md** — episodic, semantic, and procedural memory written by the agent after each conversation

These are loaded and composed into the system prompt on every message. The agent can update all three files via tools, with changes committed and pushed to GitHub immediately.

## Tools available to the agent

**Workspace (file management)**
- `save_document`, `read_document`, `delete_document`, `rename_document`
- `create_folder`, `delete_folder`, `examine_workspace`, `commit_and_push`
- All tools accept an optional `repo_name` parameter (defaults to `"workspace"`)

**GitHub administration**
- `list_repos` — list all repositories on the account
- `create_repo` — create a new GitHub repo and initialise a local workspace
- `create_issue` — open a GitHub issue in any repository
- `create_branch` — create a branch and check it out locally
- `merge_branch` — merge a branch into a target branch
- `create_pull_request` — open a pull request on the agent's fork
- `open_upstream_pr` — open a pull request against the upstream codebase repo
- `check_ci_status` — poll GitHub Actions for a branch's CI result

**Self-modification**
- `list_agent_core`, `read_agent_core` — inspect configuration files
- `create_agent_core`, `update_agent_core` — modify identity, soul, or other config files
- `update_memory` — update persistent memory

## Self-modification flow

The agent can propose changes to its own codebase:

1. Create a feature branch on its fork (`stevens-j-54/p-agent`)
2. Commit changes to the branch
3. Open a pull request against the upstream repo (`quaneh2/p-agent`)
4. Poll `check_ci_status` until CI passes or fails
5. Self-review the diff before finalising
6. One PR per logical change; the agent never merges its own PRs

When a PR is merged and Render redeploys, the fork is synced with upstream on the next startup.

## Environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GITHUB_TOKEN` | GitHub personal access token for the agent's account |
| `GOOGLE_TOKEN_JSON` | Gmail OAuth token (for production deployment) |
| `AUTHORIZED_SENDERS` | JSON array of email addresses allowed to contact the agent |
| `UPSTREAM_CODEBASE_REPO` | Upstream repo for self-modification PRs (default: `quaneh2/p-agent`) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (Telegram disabled if unset) |
| `TELEGRAM_AUTHORIZED_IDS` | JSON array of Telegram user IDs allowed to contact the agent |

## Deployment

The agent is deployed on [Render](https://render.com) as a background worker. On startup it:

1. Authenticates with Gmail
2. Initialises the GitHub service
3. Clones (or pulls) the default workspace repo
4. Clones (or pulls) the agent-core repo, seeding default configuration if needed
5. Initialises Telegram (if `TELEGRAM_BOT_TOKEN` is set), skipping any backlogged messages
6. Syncs the fork with upstream and cleans up merged branches
7. Begins polling Gmail and Telegram every 10 seconds

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install ".[dev]"

# Run OAuth flow to generate token.json
python agent.py --auth

# Run the agent
python agent.py

# Run tests
pytest
```
