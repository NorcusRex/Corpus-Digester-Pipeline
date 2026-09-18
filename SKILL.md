---
name: update-manifest
description: Generate or refresh a project manifest JSON file for a Claude project, listing every conversation in the project by UUID and title. Use this skill whenever the user says "update manifest", "refresh manifest", "generate manifest", "regenerate manifest", or asks for a manifest of conversations in a project, especially when they include a project UUID. The manifest file is downstream input to the digestion pipeline, which uses it to group exported conversations by project. Always use this skill for these requests, even if the user doesn't say the word "skill".
---

# Update Manifest

Generate a JSON manifest file that lists every conversation in the current Claude project. The manifest is consumed by the digestion pipeline to recover the conversation-to-project mapping that Claude's data export does not preserve.

## When to use

The user is in (or asking about) a Claude project, and wants to enumerate that project's conversations so the pipeline can group them after export. Trigger phrases include:

- "Update manifest for `<uuid>`"
- "Refresh manifest"
- "Generate manifest for this project"
- "Make a manifest of this project's conversations"

The user will typically supply a project UUID (a string of the form `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`). If they don't, ask for it before proceeding — the UUID comes from the project URL and cannot be reliably inferred from context.

## What to produce

A single JSON file at `/mnt/user-data/outputs/<PROJECT_UUID>_manifest.json` with this exact structure:

```json
{
  "project_uuid": "<PROJECT_UUID>",
  "project_name": "<project name as it appears in the UI>",
  "conversation_count": <integer>,
  "conversations": [
    { "uuid": "<conversation-uuid>", "title": "<conversation-title>" }
  ]
}
```

Field requirements:

- `project_uuid`: the UUID the user supplied, exactly as given.
- `project_name`: the project's display name as it appears in the project sidebar or instructions. If you cannot identify the name with certainty, ask the user instead of guessing.
- `conversation_count`: integer count of entries in the `conversations` array. Must match exactly.
- `conversations`: array of objects, each with `uuid` and `title`. Order from oldest to newest (so future regenerations produce stable diffs — new conversations append at the end).

## How to enumerate conversations

Use the `recent_chats` tool with these specific settings:

1. Call `recent_chats` with `n=20` and no `before` parameter on the first call. This returns the 20 most recently updated conversations in the current project.
2. For each subsequent call, set `before` to the earliest `updated_at` from the previous batch. Continue paginating until the tool returns no results (or fewer results than expected, indicating the end).
3. **Deduplicate by UUID across batches.** The `recent_chats` tool has a known boundary issue where conversations sharing an `updated_at` timestamp at the batch boundary may appear in two consecutive batches, or may be missed entirely. Deduplication catches the duplicates. The skip case is harder — see "Verification" below.
4. Extract each conversation's UUID from its URL (`https://claude.ai/chat/<uuid>`) and its title from the tool's `title` field.

## Verification

Before writing the file:

1. **Count check.** If the user has mentioned an expected count (e.g., "the project should have 27 conversations"), compare it against your collected count. If they differ, tell the user and ask whether to proceed, retry, or adjust manually.
2. **UUID format check.** Every UUID must match `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (32 hex characters in 8-4-4-4-12 grouping). If any UUID looks malformed, do not include it; flag it to the user.
3. **No invented UUIDs.** Do not generate UUIDs from pattern-matching or memory. Every UUID in the manifest must come from a `recent_chats` tool result. If the tool fails or returns no data, abort and tell the user, do not improvise.

## Output

Write the JSON file using the file-creation tool, then call `present_files` so the user can download it. The expected next step is for the user to save this file into their Claude data export's `projects/` folder before running the digestion pipeline.

## Edge cases

- **Empty project.** If `recent_chats` returns no conversations, write a manifest with `conversation_count: 0` and an empty `conversations` array. The pipeline handles this fine.
- **Project name unclear.** If you cannot determine the project name with certainty, ask the user. Do not write `"untitled"` or guess.
- **Pagination boundary skips.** If the user says the result is off-by-one compared to what they see in the sidebar, ask them to identify the missing conversation by title. Then patch it in by adding the entry manually before writing the file. Note the inserted entry in your response so they know what was added.
- **Quotes in titles.** Properly escape any double quotes in conversation titles using `\"` so the JSON is valid.

## Format notes

The output JSON must be valid JSON (parseable by `json.loads`) and human-readable (use 2-space indentation). UTF-8, no BOM. Sample output for visual reference:

```json
{
  "project_uuid": "019cfa39-2239-73f8-b318-26995911b88a",
  "project_name": "Example Project",
  "conversation_count": 3,
  "conversations": [
    { "uuid": "9db5e73f-e6d6-4a90-a62a-5886a70ca42d", "title": "First conversation title" },
    { "uuid": "11169ea5-4bfb-42db-87f1-5eb691b943d8", "title": "Second conversation title" },
    { "uuid": "2110db42-33e5-4e95-954e-b62721f00155", "title": "Third conversation title" }
  ]
}
```
