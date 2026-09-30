---
title: Handoff — Loom Pipeline Pending Items to claude.ai/code
date: 2026-09-26T03:06-07:00
source: "Claude conversation, AI Methods project"
model: Claude Opus 4.7
keywords: [handoff, Loom pipeline, Drive collision, xlsx-vs-gsheets, four-tier corpus, project-agnostic, canon boundary, backfill]
---

# Handoff — Loom Pipeline Pending Items to claude.ai/code

*2026-09-26 03:06 PDT · Source: Claude conversation, AI Methods project · Model: Claude Opus 4.7*

## Abstract

Pipeline code work moved to claude.ai/code and substantial progress has already
been made there — this handoff cannot report on that current state. What it
carries is the list of items this chat left unresolved as of its final turn, so
that claude.ai/code (or its user) can quickly determine which are still open,
which have been superseded, and which never needed doing there in the first
place. Compression: medium; format: hierarchical, prose within items.
Items are grouped by domain and each notes whether the ruling is Nick's own
[S1] or a proposal by this chat that Nick accepted.

## About this handoff

This chat's authority extends to its own contents. It does not know what
claude.ai/code has built, what it has decided, or how far the pipeline has
moved since. Every "pending" item below carries an implicit "as of when this
chat ended" — claude.ai/code should verify current state before acting on any
of them.

Two kinds of item appear:

- **Nick's own outstanding decisions**, which stand until Nick revises them.
- **Chat-proposed work items** that Nick accepted but that were not executed
  before the handoff. These may already be done or may have been reshaped.

Where a proposal from this chat has an obvious better implementation in a
code environment (e.g., Drive API scripts vs. rclone workarounds), the
proposal here is a floor, not a ceiling.

## Drive collision cleanup — highest priority

The rclone push fails on `.xlsx` files whose display name (minus extension)
collides with a native Google Sheet at the same Drive folder, producing:

> ERROR : ... `.xlsx`: Failed to copy: can't update google document type
> without `--drive-import-formats`

The naive fix (adding the flag) was tried and rolled back, because it converts
the local `.xlsx` into a Sheets update, silently dropping Excel-only features
that Nick's actual files use. The `#NAME?` errors visible via
`Google Drive:read_file_content` were a preview of that damage, not
pre-existing damage: Nick confirmed local Error Checking finds nothing.

**Nick's rule** [S1, tier 0]: identify Google Sheets on Drive that collide
with local `.xlsx` files. Delete the Sheet **only if** the `.xlsx` is newer
than or equal to the Sheet in modifiedTime. If the Sheet is newer, leave it
alone — Matt may have made edits in Sheets that the local `.xlsx` does not
yet have.

**Work not done before the handoff:**

1. Enumerate colliding pairs across the corrected Drive corpus at
   `drive:RPG/_Design/Loom`. A pair is: a native Sheet (mime
   `application/vnd.google-apps.spreadsheet`) plus a `.xlsx` blob whose title
   is `<Sheet title>.xlsx` in the same `parentId`.
2. For each pair, compare `modifiedTime`. Deletion candidates are those
   where the local `.xlsx` (or its Drive blob copy) is newer than or equal to
   the Sheet.
3. Produce a review list. Nick reviews, deletes chosen Sheets manually in
   the Drive web UI (or authorizes deletion via API), then the push can
   complete.

**Complication surfaced late:** the initial Sheet-mimetype search returned
titles like `Character Sheet v3.1.xlsx` — Sheets whose title includes the
`.xlsx` extension, which is unusual for hand-made "Open with Google Sheets"
conversions. These may be artifacts of an earlier push that briefly ran with
`--drive-import-formats` enabled. The chat could not distinguish
"user-intentional Sheet sidecar" from "accidental rclone-created Sheet". A
code-based tool with more Drive API access should be able to.

## Re-merge and rogue-folder deletion

Two smaller items downstream of collision cleanup:

**Re-merge to correct Drive location.** `merge_loom_to_drive.bat` and
`push_loom.bat` were patched from `drive:Loom` to `drive:RPG/_Design/Loom`
[chat proposal accepted at S1, tier 1]. The correct destination folder on
Drive has months-stale content from before the pipeline ran. First real
run after cleanup will be a large upload. Pass 1's dry-run will show the
scope.

**Delete rogue top-level folder.** `My Drive/Loom/` (Drive folder ID
`1mL1gapkTsDxB9IqriLwF88fKCRYdybOs`) was created by the initial merge before
the path bug was caught. It contains a full copy of what was pushed
before the fix. After the re-merge to the correct location succeeds, this
folder is safe to delete via the Drive web UI. Not before — its existence
is currently the only off-site copy of parts of the corpus.

## RPG-wide backfill

Separate from the Loom-specific pipeline. Nick was planning to run a
one-shot rclone copy of `I:\RPG\` (excluding `/_*/**` top-level folders)
to `drive:RPG`, ≈278 GB into 1.2 TB of available Drive space [S1, tier 0].

**State at handoff:** the dry-run looked correct to Nick. Real run had not
been executed. Nick was also using WinMerge in the reverse direction (Drive
down to local) to close a 128 GB gap where Drive content did not exist
locally.

**Note on interaction with collision cleanup:** the RPG-wide backfill would
hit the same `.xlsx`-vs-Sheet collision problem in any RPG subfolder where a
past "Open with Google Sheets" created a Sheet sibling. The collision
cleanup should either precede the backfill or be scoped to run over both
trees.

## Documentation

Three separate documentation streams. Only one was left open by this chat.

**Pipeline docs (`readme.txt`, `QUICK-README.txt`) — closed.** All drift
from the multi-day session was reconciled. Path change (`drive:Loom` →
`drive:RPG/_Design/Loom`) documented. New destinations under
`FromNick\Notes\AI\<source>\Conversations\Exported\` documented. Log-file
mechanism corrected from shell-redirect to rclone's `--log-file` flag,
with the failed-shell-redirect noted as historical. A new principle #5 was
added to `PRINCIPLES` making the pipeline's project-agnostic stance
explicit [chat proposal, tier 1].

**Charter and brief — open, Nick-owned.** Nick stated he would revise the
charter and brief himself to reflect the tier-model clarifications from
this conversation [S1, tier 0]:

- The four tiers: `1-Raw` (human-authored, any format), `2-Digested`
  (pipeline output, uniform Markdown), `3-Reporting` (pipeline-derived
  Markdown), `4-Canon` (human-authored released works — zine articles and
  the like).
- The write-relationship asymmetry: humans write to `1-Raw` and `4-Canon`;
  pipeline writes to `2-Digested` (and eventually `3-Reporting`). Neither
  writes across.
- `4-Canon` is Google-safe / format-portable by construction because that
  is the boundary where work crosses to Matt and to AI tools, and
  eventually to GitHub.
- `4-Canon` is *new writing* about corpus material, not a cleaned-up
  version of it. "Reader's Digest of the corpus", in Nick's phrasing.

**Distribution `.md` files for other Claude conversations.** Not touched
this session. `loom-charter-and-skill-changes.md` and
`digestion-pipeline-index-changes.md` remain as they were. If Nick's
charter/brief revision changes the framing significantly, these will need
a matching pass.

## Deferred future work

Not "pending" in the sense of blocking anything — Nick explicitly deferred
these. Listed so claude.ai/code has the map.

- **Three-tier local backup architecture.** Blocked on bigger SSD boot
  drive. Plan [S1, tier 0]: `I:\RPG\` remains primary working copy
  (portable USB); a mirror at `C:\Users\nick\OneDrive\Documents\RPG\`
  gives OneDrive-versioned backup; Drive is the collaboration surface;
  GitHub is the durable canon home. Only `I:` is authoritative; everything
  else is downstream. This chat noted (Nick corrected) that OneDrive does
  **not** currently back up `I:\RPG\` — only User Documents.

- **GitHub repository for `4-Canon`.** Deferred. Plan [S1, tier 0]:
  4-Canon lives in a GitHub repo, and Matt gets onboarded to git (or at
  least git read-access via GitHub Desktop) as a separate task. Nick
  raised the possibility of also including `3-Reporting`; this chat
  argued against (pipeline-generated content makes noisy commits), and
  Nick did not respond to that argument [chat proposal, tier 7 —
  Indeterminate]. Recommend surfacing the question again in code work.

- **OCR pre-digester for the RPG PDF library** at
  `I:\RPG\_SearchLibrary\1-Raw`. 204 folders of game-system PDFs. Nick has
  a `batch_ocr.bat` skeleton using `ocrmypdf --skip-text` [chat awareness
  of prior context — see S2]. Fits the generic converter model as another
  pre-digester step.

- **`index_canon.py`** — a future companion to the existing pipeline
  index script, to produce indexes for `4-Canon` and `3-Reporting`. From
  earlier session context [S2]. Design was scoped as explicit non-goal
  for the current pipeline release.

- **Optional: redirect `digest_all.bat` stale-check output to a log file.**
  Low priority quality-of-life item.

## Reporter's commentary

Two observations that are the reporter's, not Nick's:

**The collision cleanup deserves a proper Drive-API tool, not another
rclone workaround.** The rclone matching model collapses same-name-different-mime
into a single update target, which is the entire cause of the family of
problems this chat spent a night on. A small Python script using the Drive
API directly could enumerate collisions, compare timestamps, and either
report or delete with far less ceremony than the "search, list, copy IDs
into Drive web UI, delete manually" workflow the rclone constraint forced.
Whether this is worth building depends on how often the collision case
recurs.

**The Drive-collaboration constraint is doing a lot of work in this
architecture.** Nick prefers Excel, Matt does not have it, and the entire
"Google-safe at the 4-Canon boundary" rule exists because of this. If Matt
onboards to git for canon, that rule becomes almost redundant for canon
(git treats `.xlsx` opaquely), though it still applies at the 3-Reporting
and lower tiers as long as Matt views them via Drive.

## Provenance

The subject is Nick. This report was written by Claude Opus 4.7 in a Claude
web conversation with access to the current chat and to one prior transcript
file. Rubric version 4.4; provenance standard version 4.4.

Compression choice: medium, hierarchical prose within items. Filename by
timestamp convention (this is not a versioned document).

Substantive attributions in the body:

- **Drive collision cleanup rule** (delete Sheet only when `.xlsx` is newer or
  equal): Nick's own position ([S1], user-acceptance tier 0 — Subject's Own
  Assertion). Stated explicitly in reaction to the chat's earlier general
  "delete colliding Sheets" proposal, as a refinement Nick required.
- **Four-tier model with authorship asymmetry**: Nick's own position
  ([S1], tier 0), stated and clarified across several turns. Specifically,
  the framing of 4-Canon as human-authored *new works* rather than
  pipeline-cleaned content is Nick's, correcting the chat's earlier
  assumption.
- **Format-portability at the 4-Canon boundary**: Nick's own position
  ([S1], tier 0).
- **`drive:Loom` → `drive:RPG/_Design/Loom` path correction and the patches
  to push/merge .bats**: chat proposal that Nick explicitly accepted
  ("Fix the files") ([S1], user-acceptance tier 1 — Explicitly Accepted).
- **Rollback of `--drive-import-formats`**: chat proposal accepted after
  Nick's data (local Error Check finds no errors) contradicted the
  chat's earlier reading of the `.xlsx` content ([S1], tier 1).
- **New pipeline principle #5 (project-agnostic)**: chat proposal Nick
  directly ordered ("Draft that one sentence and patch it in") ([S1],
  tier 1 with commitment).
- **RPG-wide backfill scope and exclusion pattern**: Nick's own position
  ([S1], tier 0).
- **Three-tier backup architecture and GitHub-for-canon plan**: Nick's own
  positions ([S1], tier 0). The chat's argument against including
  `3-Reporting` in the GitHub repo did not receive a Nick response and is
  therefore Indeterminate ([S1], user-acceptance tier 7 —
  Indeterminate); it is noted here as an open question rather than a
  ruling.
- **OCR pre-digester and `index_canon.py` context**: these are from
  earlier sessions summarized in [S2]. Chat carries them forward as
  "still deferred, still relevant" but has not verified with Nick in this
  session whether they remain so.

Uncertainties this report explicitly does not resolve:

- Current state of the pipeline code in claude.ai/code. This chat has no
  visibility.
- Whether the `.xlsx`-titled Sheets found late in the collision-search
  work are user-intentional or rclone artifacts. Could not distinguish.
- Whether Nick's charter/brief revision (which he stated he would do
  himself) has begun or completed.

No overrides taken. This report follows the write-report skill defaults
and Nick's userPreferences (conciseness, uncertainty flagged, no
overconfidence).

## Sources

### S1 — Conversation: this Claude web chat, AI Methods project

- Type: Claude conversation (in progress at time of writing)
- Locator: current conversation; UUID not available inside conversation
- Accessed: 2026-09-26
- Note: covers roughly the final quarter of a multi-day pipeline session;
  earlier context available via S2.

### S2 — Transcript: prior sessions of this pipeline work

- Type: local transcript file
- Locator: `/mnt/transcripts/2026-05-20-16-54-35-loom-pipeline-multiday-session.txt`
- Accessed: 2026-09-26
- Note: compacted summary presented at the start of the current chat;
  full text available on disk. Contains the multi-day session on Phases
  1-7 including the docx/xlsx/pptx/pdf converter work, the manifest→index
  rename cutover, the rclone log-mechanism iterations, the pull_matt
  rclone-cycle debugging, the sync_loom destination change, and the
  earlier Drive-path bug discovery.

---

## Triage on receipt — 2026-09-26, Code side

The note asked to be checked against current state rather than acted on
blind. Verified against the repository.

**Done or decided against**

| Item | Verdict |
|---|---|
| OCR pre-digester | Built as `ocr_pdf.py`, with caching and without modifying `1-Raw` |
| Re-merge to the correct Drive location | Superseded. No hardcoded Drive path survives; `DRIVE_PATH` is per-corpus configuration |
| Pipeline docs reconciliation | Done. Principle #5, project-agnostic, verified still present after the conversion to Markdown |
| `index_canon.py` | **Decided against, not deferred.** `repository-structure.md` 2.4 rules that the authored tiers carry no index by design. `tier_sidecars.py` catalogues `4-Canon` and `stamp_tier.py` stamps `3-Reporting` instead. Recorded so the old plan is not revived by accident |
| Stale-check output to a log | Built, and widened: four passes now take `--log`, sharing `run_log.py` |
| Drive collision cleanup | Detection built as `drive_collisions.py`. The deletions remain Nick's |

**Nick's, outside the pipeline:** deleting the rogue `My Drive/Loom/` folder
— only after a successful push, since it is currently the only off-site copy
of part of the corpus; the RPG-wide backfill; the charter and brief revision;
the three-tier backup architecture.

**Still genuinely open, and worth re-surfacing:** whether `3-Reporting` joins
`4-Canon` in a GitHub repository. The note records this as tier 7,
Indeterminate — the chat argued against it on the grounds that
pipeline-generated content makes noisy commits, and Nick did not respond.
That remains unanswered and is a real decision.

**One figure not to trust.** The note says 204 folders of game PDFs. Measured
on 2026-09-26 the archive is 96,774 files and 1.15 TB, roughly a thousand
games, with fewer than a hundred wanted in the search corpus. Nothing depends
on the older number, but it should not be carried forward.
