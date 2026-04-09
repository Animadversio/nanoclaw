---
name: email-to-tasks-v3
description: Thorough email check with 100% recall. Fetches ALL emails, reads every body, creates Google Tasks. No email left behind. Uses subagents for analysis.
version: 1.0.0
---

# Email to Tasks v3

**100% recall email processing.** Every email gets read. Every action item gets a task.

## Architecture

```
Script (mechanical)  →  Agent (understanding)  →  Script (mechanical)
   collect emails          read + classify           create tasks
   dedup                   extract actions            validate
   fetch bodies            consult preferences
```

**Design principles:**
1. Scripts handle fetching and dedup (no shortcuts possible). Agent handles comprehension and classification (can't skip — must classify every email). Validation ensures nothing was missed.
2. **Agents judge, scripts move data.** Subagents output ONLY compact verdicts (~5K tokens), never echo back the input data (~50K tokens). Scripts apply verdicts back to original files. This prevents timeout and saves ~90% output tokens.

## Outbound Email Tracking

Binxu BCCs his sent emails to his HMS address (`biw905@hu.mail.onmicrosoft.com`), which are forwarded to Gmail via the `outlook-threads` label. This means **outbound replies appear alongside inbound emails** in the collection.

**Agent rule:** If an outbound email from Binxu exists in a thread that is more recent than an inbound email in the same thread → that inbound is already handled. Downgrade it from "action" to "fyi" or "skip". The outbound email itself is always "skip".

## Quick Start

### Full Pipeline (recommended)

```
PHASE 1: Collect
  cd /workspace/group/skills/email-to-tasks-v3
  python3 scripts/email_collect.py [--outlook-days 5] [--inbox-days 3]
  → Report collection stats to user
  → Output: /tmp/emails_to_review.json

PHASE 2: Analyze (spawn subagent)
  → Subagent reads preferences.yaml + emails_to_review.json
  → Fills verdict + actions for EVERY email
  → Output: /tmp/emails_analyzed.json

PHASE 3: Validate
  python3 scripts/validate_verdicts.py /tmp/emails_analyzed.json --action-only --output /tmp/emails_action_items.json
  → Report validation stats to user
  → Confirms 0 missing verdicts

PHASE 4: Create Tasks
  python3 scripts/task_creator.py --input /tmp/emails_action_items.json
  → Report task creation stats to user

PHASE 5: Summary
  → Send final report to user with all categories
```

## Phase 1: Collect (Script)

```bash
cd /workspace/group/skills/email-to-tasks-v3

# Default (5 days outlook, 3 days inbox)
python3 scripts/email_collect.py

# Custom time windows
python3 scripts/email_collect.py --outlook-days 7 --inbox-days 5

# After vacation
python3 scripts/email_collect.py --outlook-days 14 --inbox-days 7

# Reprocess everything (ignore existing tasks)
python3 scripts/email_collect.py --skip-dedup

# Outlook only
python3 scripts/email_collect.py --outlook-only
```

**Output:** `/tmp/emails_to_review.json` — every email with full body text, verdict=null.

Then filter out previously processed emails:
```bash
python3 scripts/processed_cache.py filter /tmp/emails_to_review.json
```

This removes emails already classified in prior runs (even if they weren't turned
into tasks — e.g., FYI/skip items). Works alongside Google Tasks dedup.

**Report to user:** Send collection stats (how many found, deduped, cache-skipped, to review).

## Phase 2: Analyze (Subagents)

Split emails into chunks (~25 per chunk), condense for agent reading, spawn parallel subagents.

### Step 2a: Split into chunks + condense

```bash
# Split (25 per chunk to stay under read tool limits after condensing)
python3 scripts/split_chunks.py /tmp/emails_to_review.json --chunk-size 25
# Output: /tmp/emails_chunk_1.json, /tmp/emails_chunk_2.json, ...

# Condense each chunk (strips giant URLs, truncates bodies, ~75% smaller)
for f in /tmp/emails_chunk_*.json; do
  python3 scripts/condense_chunk.py "$f" --body-limit 800
done
# Output: /tmp/emails_chunk_1_condensed.json, etc.
```

**Why condense?** The `read` tool truncates at 50KB. Raw chunks are 150-250KB
(mostly urldefense.proofpoint.com URLs). Condensed chunks are 34-37KB — safely
under the limit. The agent reads the condensed version; full data stays in the
original chunk for apply_verdicts.py to merge into.

**Report to user:** How many chunks created, condensed sizes.

### Step 2b: Spawn subagents (one per chunk)

For each chunk file, spawn a subagent.

**KEY DESIGN: Verdict-only output.** Subagents write ONLY a compact verdicts file
(~2-5K tokens), NOT the full email JSON (~50K tokens). This prevents timeout from
massive output generation. A script then applies verdicts back to the original chunks.

```python
sessions_spawn(
    runtime="subagent",
    model="sonnet",
    mode="run",
    task=f"""
You are analyzing emails for action items. You MUST classify every single email.

## Instructions

1. Read the preferences file:
   cat /workspace/group/skills/email-to-tasks-v3/preferences.yaml

2. Read your assigned chunk (use the CONDENSED version):
   cat /tmp/emails_chunk_N_condensed.json

3. For EVERY email in the "emails" array, classify it.
   Check metadata.emails_in_chunk to verify you classified ALL of them.

4. RULES (from preferences.yaml):
   - When unsure between action and FYI → choose action
   - Read Slack/Discord notification bodies for actual messages
   - OAIR, OpenReview, conference emails → always action
   - Known contacts → never skip
   - Check body for hidden deadlines
   - FW: prefix means Selina forwarded from HMS — she thought it worth seeing

5. Write ONLY the verdicts to /tmp/emails_verdicts_N.json — a COMPACT file:

   {{"verdicts": [
     {{"email_id": "xxx", "verdict": "action", "urgency": "urgent",
       "deadline": "YYYY-MM-DD", "actions": [{{"description": "...", "priority": 1}}],
       "context": "Brief summary (1-2 sentences)"}},
     {{"email_id": "yyy", "verdict": "fyi", "urgency": null, "deadline": null,
       "actions": [], "context": "Brief note"}},
     {{"email_id": "zzz", "verdict": "skip", "urgency": null, "deadline": null,
       "actions": [], "context": "Why skipped"}}
   ]}}

   ⚠️ DO NOT write the email bodies, subjects, senders, or any other original fields.
   ⚠️ ONLY write email_id + verdict + urgency + deadline + actions + context.
   ⚠️ This keeps output small (~5K tokens instead of ~50K).

6. Print a summary: how many action / fyi / skip

CRITICAL: Every email MUST have a verdict entry. Zero exceptions.
""",
    runTimeoutSeconds=600,
)
```

### Step 2c: Apply verdicts + Merge chunks

After all subagents complete, apply verdicts back to original chunks, then merge:

```bash
# Apply each verdict file to its chunk
python3 scripts/apply_verdicts.py /tmp/emails_verdicts_1.json /tmp/emails_chunk_1.json
python3 scripts/apply_verdicts.py /tmp/emails_verdicts_2.json /tmp/emails_chunk_2.json
# ... for each chunk

# Merge into single file
python3 scripts/merge_chunks.py /tmp/emails_chunk_*.json --output /tmp/emails_analyzed.json
```

**Report to user:** Merge stats + verdict breakdown.

## Phase 3: Validate

```bash
# Check all verdicts are filled
python3 scripts/validate_verdicts.py /tmp/emails_analyzed.json --strict --action-only --output /tmp/emails_action_items.json
```

**Report to user:** Validation stats (N action, N fyi, N skip, N missing).

If any verdicts are missing → re-run subagent for just the missing emails.

After successful validation, update the processed cache:
```bash
python3 scripts/processed_cache.py add /tmp/emails_analyzed.json
```
This prevents re-reading these emails on the next run.

## Phase 4: Create Tasks

```bash
python3 scripts/task_creator.py --input /tmp/emails_action_items.json
```

**Existing task_creator.py** from v2 — handles parent tasks + subtasks, email ID in notes for dedup.

**Report to user:** How many tasks created, skipped, errors.

## Phase 5: Final Report

Send user a complete report:

```
📬 Email Check — [Date]

📊 Collection: [N] emails found, [M] deduped, [K] reviewed
⏱️ Processing time: [X] seconds

🚨 ACTION ITEMS ([N] tasks created)
1. [Task title] — [urgency] — [deadline if any]
   From: [sender]
   Actions: [what needs to be done]

2. ...

ℹ️ FYI ([N] emails)
• [Brief note on each FYI email]
• ...

⏭️ Skipped ([N] emails)
• [Brief reason for each skip]
```

## preferences.yaml

Located at: `/workspace/group/skills/email-to-tasks-v3/preferences.yaml`

**What it contains:**
- Default time windows
- "Always action" patterns (OAIR, OpenReview, deadlines)
- "Always read carefully" patterns (Slack, Discord, BioArt)
- Known contacts (never skip)
- Known skip patterns (marketing)
- Learned patterns (agent appends over time)

**How to update:**
- Agent can append to `learned:` section after discovering new patterns
- Selina can edit directly to add contacts, adjust rules
- Changes take effect on next run (no restart needed)

## Files

```
email-to-tasks-v3/
├── SKILL.md                  # This documentation
├── preferences.yaml          # Agent guidance + learned patterns
└── scripts/
    ├── email_collect.py      # Phase 1: Fetch all + dedup + extract bodies
    ├── split_chunks.py       # Phase 2a: Split into chunks for parallel processing
    ├── condense_chunk.py     # Phase 2a: Strip URLs + truncate bodies for agent reading
    ├── apply_verdicts.py     # Phase 2c: Apply compact verdicts back to chunks
    ├── merge_chunks.py       # Phase 2c: Merge analyzed chunks
    ├── processed_cache.py    # Cross-run cache: skip already-classified emails
    ├── validate_verdicts.py  # Phase 3: Ensure no missing verdicts
    ├── task_creator.py       # Phase 4: Create Google Tasks (from v2)
    └── utils.py              # Shared: Gmail fetch, body extraction, dedup
```

## Deduplication

**How it works:**
1. `email_collect.py` checks ALL existing Google Tasks in EmailCommunication list
2. Extracts `Email ID: xxx` from task notes
3. Filters out emails that already have tasks
4. Only new emails go to agent for review

**Force reprocessing:**
```bash
python3 scripts/email_collect.py --skip-dedup
```

## Error Handling

- **Fetch failure for individual email:** Logged as error, other emails still processed
- **Subagent timeout:** Re-spawn with remaining unclassified emails
- **Missing verdicts after analysis:** `validate_verdicts.py --strict` catches this
- **Task creation failure:** Logged per-email, doesn't block other tasks

## Changelog

### v1.0.3 (2026-03-13)
- Added `processed_cache.py` — tracks classified email IDs across runs
- Filter step after collection removes already-processed emails
- Cache updated after successful validation
- Prevents re-reading emails from prior runs (not just task-deduped ones)
- Supports: add, filter, list, clear, prune (auto-expire old entries)

### v1.0.2 (2026-03-13)
- **FIX:** Added `condense_chunk.py` — strips urldefense URLs, truncates bodies to 800 chars.
  Raw chunks 150-250KB → condensed 34-37KB (under 50KB read tool limit).
  Prevents silent truncation that caused chunk 3 to miss 13/34 emails.
- Reduced default chunk size from 35 to 25 for safer margin.
- Added email count verification instruction to subagent task.

### v1.0.1 (2026-03-13)
- **CRITICAL FIX:** Subagents now write compact verdicts file (~5K tokens) instead of
  rewriting entire email JSON (~50K tokens). Prevents timeout on chunks 2/3.
- Added `apply_verdicts.py` script to merge verdicts back into chunk files
- Updated subagent task template to output verdict-only format
- Lesson: LLM agents should judge, not copy data. Scripts handle structural work.

### v1.0.0 (2026-03-13)
- Complete rewrite from v2
- Script-based collection (no agent shortcuts)
- Mandatory verdict for every email
- preferences.yaml for configurable agent guidance
- Validation step ensures 100% recall
- Subagent-based analysis for token efficiency
