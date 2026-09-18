# Pipeline Development Brief — Part 1

**Conversation scope:** A Python-based file digestion pipeline; Claude data export support refinement; manifest-based project grouping; keyword extraction improvements; directory restructuring into two distinct libraries; setup of a parallel RPG search library.

---

## 1. Starting state (carried over from prior sessions)

Pipeline at `/mnt/user-data/outputs/` consisting of these files:

- `process_folder.py` — orchestrator
- `process_folder.bat` — Windows launcher
- `docx_to_markdown.py`, `xlsx_to_markdown.py`, `pdf_to_markdown.py`, `html_to_markdown.py`, `rtf_to_markdown.py` — format converters
- `chatgpt_to_markdown.py` — ChatGPT JSON export converter
- `claude_to_markdown.py` — Claude data export converter
- `add_metadata.py` — keyword/index frontmatter pass
- `rename_chatgpt_projects.py` — folder rename utility
- `project_names.tsv` — ChatGPT project ID → human name mapping
- `readme.txt` — documentation
- `fix_apostrophes.py` — historical one-time migration script

**Core principle:** "Human canon, AI commentary." Lossless mechanical conversion. Zero information loss by default. No AI in the pipeline itself (deterministic, idempotent, runs offline).

**Output convention:** Each input file produces a `.md` Markdown file plus a `.nlm.md` sidecar (frontmatter-stripped, for NotebookLM). Searchable via Obsidian property search, Claude's Drive connector, and grep.

**Tone preferences (carried from prior sessions):**

- Citations: APA with DOI links, footnote-style
- TOC summary trigger phrase: "TOC summary with percentages"
- Structured outputs: numbered lists, tables with honest tradeoffs
- Pushes back when responses are inaccurate; values correctness and honest acknowledgment of limitations
- Windows Chrome and Claude Android app primary clients; Claude Max plan; uses Cowork

**Identity (historical context only):** This pipeline was developed in support of "The Loom" (a TTRPG design project), but as work progressed it became clear the tool is general-purpose. This conversation explicitly purged Loom-specific branding from the codebase.

---

## 2. Claude data export refinements (this session's earlier work)

### The project metadata gap

Discovered: Claude's data export does not always include project metadata files for every project. The user's export contained metadata for only 25 of 38 projects. The RPG Theory project (`8011ce26-dae6-441b-9c3d-6668e04cc56f`) was missing its metadata file specifically.

**Consequence:** When the converter routed conversations via manifest, projects without metadata files got fallback folder names like `project_8011ce26__untitled` because no project name was available.

**Workaround applied:** User manually renamed `project_8011ce26__untitled` → `project_8011ce26__rpg-theory`. Sticky-folder logic (find by content not name) preserves this rename across future runs.

**Permanent fix proposed but deferred:** Extend the manifest format to include `project_name`, so manifests can supply the name when project metadata is missing. The update-manifest skill prompt already includes this; the converter needs a small change to honor it as fallback.

### The orphan untitled-conversation issue

Discovered: 146 empty `Untitled conversation` .md files with `source: "ChatGPT export"` frontmatter were sitting in the Claude export digested folder. Root cause: leftover from a previous pipeline run, before Claude detection was implemented, when the Claude `conversations.json` file was incorrectly processed by the ChatGPT converter.

**Resolution:** User manually deleted all of them. Today's pipeline doesn't write these (Claude detection prevents it), so they won't recur.

**Lesson recorded:** Pipeline does not auto-clean stale outputs. Old garbage from previous runs lingers indefinitely. A `--clean-stale` flag was discussed but not implemented (deferred; respects "no information loss by default" principle).

### The recent_chats pagination bug

Discovered during manifest generation: `recent_chats` tool has a pagination edge case at batch boundaries when timestamps are shared. One conversation ("Archery discussion") was missed in the RPG - The Loom manifest (26 of 27 captured). User patched the manifest manually and reported the bug to Anthropic.

**Workflow accommodation:** The manifest-generation prompt now includes a deduplication step. User glances at manifest count vs. sidebar count after generation; off-by-one means manual patch.

### Manifest validation hardening in claude_to_markdown.py

The converter now:

1. Pre-discovers existing project folders BEFORE the conversation loop (fixes race condition that split writes between renamed and default folders)
2. Reports stale manifest entries (UUIDs not in export — usually deleted conversations)
3. Reports title mismatches (conversations renamed in Claude after manifest generation)
4. Reports cross-manifest UUID conflicts (same conversation claimed by two projects — indicates manifest bug)

### The `.nlm.md` sidecar bug fix (applied to all three locations)

Critical bug found and fixed: `find_existing_project_folder` (Claude), `existing_folder_for_template` (ChatGPT), and `find_folder_by_template_id` (rename script) all globbed `*.md` to find the canonical .md file, but the pattern matches `.nlm.md` sidecars too. Sidecars have frontmatter stripped, so the project-id needle never matched, and the `break` exited before checking the canonical .md.

**Impact:** Sticky-folder behavior was silently broken across re-runs on any previously-processed archive. ChatGPT renamed folders may have drifted.

**Fix applied** in all three locations: filter out `.nlm.md`, take first canonical .md.

### Slug fix

Collapse runs of hyphens to single hyphen so "RPG - The Loom" slugifies to `rpg-the-loom` instead of `rpg---the-loom`.

---

## 3. The update-manifest skill

Created `/mnt/user-data/outputs/update-manifest/SKILL.md`. A YAML-frontmatter SKILL.md file in the format used by Claude's skill system.

**Trigger phrases:** "update manifest," "refresh manifest," "generate manifest for project X."

**Behavior:** Inside a Claude project, the user prompts with the skill name plus a project UUID. The skill instructs Claude to:

1. Paginate `recent_chats` with `n=20` per call, using `before` parameter set to earliest `updated_at` from previous batch

2. Deduplicate by UUID across batches (handles the pagination boundary bug)

3. Extract UUID + title for each conversation

4. Write JSON to `/mnt/user-data/outputs/<PROJECT_UUID>_manifest.json` with structure:
   
   ```json
   {
     "project_uuid": "...",
     "project_name": "...",
     "conversation_count": N,
     "conversations": [{"uuid": "...", "title": "..."}]
   }
   ```

5. Present the file for download

**Installation:** Save SKILL.md as a Google Doc in Drive, add to each Claude project where you'll generate manifests. Triggering relies on Claude reading the description and recognizing the trigger phrase.

**Future use:** Once installed across projects, refreshing all manifests becomes: open each project → say "update manifest for `<uuid>`" → save to AI Backups Claude export folder → re-run pipeline.

---

## 4. Architecture decision: two-library structure

**Problem identified:** AI conversation exports were being treated as Loom-specific material because they happened to live inside the Loom folder. But AI exports span all topics (health, sustainability, philosophy, RPG, Loom, etc.). They're a reference library, not a Loom-specific input. Pruning non-Loom content from the Loom Digested tree was fighting the natural shape of the data.

**Decision:** Split into two libraries.

**AI Backups** at `I:\AI\Backups\` — reference library for ALL AI conversations:

```
I:\AI\Backups\
    ChatGPT\Exported\1-Raw\         ← raw ChatGPT exports
    ChatGPT\Exported\2-Digested\    ← digested
    Claude\Exported\1-Raw\          ← raw Claude exports
    Claude\Exported\2-Digested\     ← digested
    _Tools\Digestion Pipeline\      ← the shared pipeline tool
```

(User opted to keep `Exported\` middle layer; pipeline doesn't care.)

**Loom** at `I:\RPG\_Design\Loom\` — focused work area for Loom-specific material only:

```
I:\RPG\_Design\Loom\
    1-Raw\        (Loom notes, drafts, Evernote exports, Matt's contributions)
    2-Digested\
    3-Reporting\
    4-Canon\
    _Tools\Claude - Writing Suite\
```

**Cross-access:** Via Obsidian (open both vaults), Claude with Drive (point at both folders), grep (specify both paths). Optionally Windows symlinks (`mklink /D`) or Drive shortcuts to make AI Backups appear within Loom for browsing. **No file duplication.**

**Files only have one home.** Loom conversations from Claude live in the AI Backups library (in the `project_019cfa39__rpg-the-loom` folder). When working on Loom, you point your tools at both libraries.

### Migration completed by user

Steps 0-6 of the migration plan executed:

- [x] Backup made
- [x] Pipeline tool moved to `I:\AI\Backups\_Tools\Digestion Pipeline\`
- [x] AI exports confirmed intact at `I:\AI\Backups\`
- [x] (Skipped step to flatten Exported layer; user kept it)
- [x] AI export duplicates deleted from Loom Raw tree
- [x] AI export duplicates deleted from Loom Digested tree
- [x] Pipeline re-run against new structure — 0 errors reported

**Tree verified post-migration.** Loom tree no longer contains `From ChatGPT` or `From Claude` subfolders under `Notes\AI\`. AI Backups tree intact with both ChatGPT and Claude libraries.

---

## 5. Phase A1 keyword extraction improvements (applied this session)

Three changes to `add_metadata.py`, all stdlib-only, no new dependencies:

### Extended stopwords (~150 new terms added)

Categories added:

- Hedge words & qualifiers (essentially, basically, fundamentally, particularly, certainly, etc.)
- Conversational connectives (approach, consider, context, perspective, framework, etc.)
- AI assistant phrases (heres, lets, okay, however, moreover, etc.)
- Discussion verbs (discuss, mentioned, explain, suggest, indicate, etc.)
- Generic process/work nouns (work, task, issue, problem, question, point, etc.)
- Demonstratives and general pronouns (anything, something, nothing, everything, etc.)
- Generic adjectives (different, similar, various, certain, common, simple, etc.)
- Conversation-meta words (conversation, chat, thread, message, response)

**Rationale:** The "other Claude" identified (correctly) that TF-IDF systematically demotes recurring topics in a personal knowledge base, while AI conversation framing language survives because it's distributed across the corpus and looks "normal." Extending the stopword list addresses the noise problem directly.

### Wordcount-scaled keyword count

```python
def keyword_count_for(word_count):
    if word_count < 500:    return 8
    if word_count < 2000:   return 12
    if word_count < 5000:   return 18
    if word_count < 15000:  return 25
    return min(40, 10 + word_count // 500)
```

Long conversations are typically richer in topics; flat 10-keyword cap was insufficient.

### Sorted output (alphabetical)

Keywords now stored alphabetically in frontmatter. Ranking by score happens during extraction; alphabetical sort is the storage order. Stable diffs across re-runs, easier visual scanning, greppable consistently.

### CLI changes

- `add_metadata.py`'s `--keywords` flag default changed from `10` to `None` (meaning auto-scale)
- `process_folder.py`'s `--keywords` flag default also changed to `None`
- Explicit integer override still works

---

## 6. Phase A2 and B (deferred — not implemented)

**Phase A2 (not done):** scikit-learn `TfidfVectorizer` replacing hand-rolled TF-IDF. Supports n-grams (multi-word concepts like "dawn phenomenon" as single keywords). Would require `pip install scikit-learn`.

**Phase B (not done):** spaCy + noun-focused vocabulary curation + `topics:` frontmatter field. The architectural answer to TF-IDF's recurring-topic blindness. Would require `pip install spacy` and `python -m spacy download en_core_web_sm`.

**Design decided for Phase B if pursued:**

- `build_vocabulary.py` script aggregates noun frequencies across the corpus, outputs `vocab.md` (Markdown table, searchable)
- `add_metadata.py` extended to read vocab and write `topics:` field to each conversation's frontmatter
- Per-document term sidecars (`.terms.json`) ruled out — frontmatter `topics:` is sufficient for all search consumers (Obsidian property search, Claude with Drive, grep), and sidecars create search-pollution problems

**Stylistic analysis (deferred indefinitely):** User decided not to pre-compute readability metrics. Lexical/stylistic analysis can be done by Claude on demand for finished works in `4-Canon`. The vast majority of digested files are notes and drafts where stylistic analysis isn't needed.

**Trigger to revisit:** If after using Phase A1 results, searches still feel poor on recurring topics (kidney, vitamin D, etc.), Phase B becomes worth the dependency cost.

---

## 7. Loom-naming purge

The pipeline started as "Loom Digestion Pipeline" branding. This session genericized everything:

**Files updated:**

- `readme.txt`: Title changed to "ARCHIVE DIGESTION PIPELINE"; example paths use `C:\Users\YourName\Documents\Archive\` instead of `C:\Users\Nick\Documents\Loom\`; example project names use "My Project Name" instead of "RPG - The Loom"
- `process_folder.bat`: Title strings updated; example paths generic
- `rename_chatgpt_projects.py`: TSV example uses "My Project Name"
- `update-manifest/SKILL.md`: References "the digestion pipeline" not "the Loom digestion pipeline"; example project uses "Example Project"

**Files NOT updated (intentionally):**

- `fix_apostrophes.py`: Historical one-time migration script. Contains references to "Nick_s" and "Chris_s" because those were the actual data migration targets. Left as-is for archival accuracy. Won't be run again.

**Verification:** No Loom/Nick references remain in active code outside `fix_apostrophes.py`.

---

## 8. New convenience script: digest_all.bat

Created `/mnt/user-data/outputs/digest_all.bat` — runs the pipeline against all three libraries in sequence:

```batch
@echo off
setlocal
set "PIPELINE=%~dp0process_folder.py"
where py >nul 2>nul
if not errorlevel 1 (set "PY=py -3") else (set "PY=python")

echo --- ChatGPT Backup ---
%PY% "%PIPELINE%" "I:\AI\Backups\ChatGPT\1-Raw" "I:\AI\Backups\ChatGPT\2-Digested"

echo --- Claude Backup ---
%PY% "%PIPELINE%" "I:\AI\Backups\Claude\1-Raw" "I:\AI\Backups\Claude\2-Digested"

echo --- Loom ---
%PY% "%PIPELINE%" "I:\RPG\_Design\Loom\1-Raw" "I:\RPG\_Design\Loom\2-Digested"
```

**Note:** User opted to keep `Exported\` middle layer in AI Backups. Path in batch file may need adjustment to `I:\AI\Backups\ChatGPT\Exported\1-Raw` etc., or user updates batch when ready.

---

## 9. Obsidian vault placement

**Decision:** Two vaults, one per library.

- AI Backups vault rooted at `I:\AI\Backups\` (covers both ChatGPT and Claude)
- Loom vault rooted at `I:\RPG\_Design\Loom\2-Digested\` (or one level up if you want Drafts/Canon/Reporting visible)

Move existing `.obsidian/` from `Loom\2-Digested\FromNick\` up to the chosen Loom vault root to preserve settings.

Each vault has its own config, graph, property indexes. Switch via Obsidian's vault switcher. Open both windows side-by-side for cross-vault search.

---

## 10. RPG Search Library project (new initiative)

**Context:** User has a massive personal collection at `I:\RPG\` — 23,245 files, 2,161 folders, mostly PDFs (19,289 of them). Range covers most TTRPG history.

**File breakdown:**

- PDF: 19,289
- PNG: 808
- HTML: 806
- JPG: 530
- TXT: 451
- JSON: 322
- MD: 243
- ZIP: 185 (not handled by pipeline)
- DOCX: 57
- DJVU: 33 (not handled)
- EPUB: 33 (not handled)
- Plus many smaller categories

**Honest scale assessment:**

- ~27-54 hours of pipeline time for the full 19K PDFs at 5-10 seconds each
- Many older PDFs are likely image-only scans without text layers — those produce searchable-text-empty Markdown
- Output size likely 1.2-2× raw size (art-heavy books bloat output)
- Some formats (EPUB, DJVU, CBR, MOBI) get preserved as-is, not converted

### Workflow agreed

```
I:\RPG\_SearchLibrary\
    1-Raw\          ← COPIES (not moves) of core books wanted searchable
    2-Digested\     ← pipeline output
```

**Three-pass process:**

1. Copy chosen PDFs from `I:\RPG\<various>\` into `I:\RPG\_SearchLibrary\1-Raw\`
2. Run batch OCR on everything in `1-Raw\` (modifies copies in place; originals untouched)
3. Run digestion pipeline against `1-Raw\`, output to `2-Digested\`

**Batch OCR script provided** (`batch_ocr.bat` template):

```batch
@echo off
setlocal EnableDelayedExpansion
set "ROOT=I:\RPG\_SearchLibrary\1-Raw"
for /r "%ROOT%" %%f in (*.pdf) do (
    echo OCRing: %%f
    ocrmypdf --skip-text --output-type pdf "%%f" "%%f.ocr.tmp" 2>nul
    if exist "%%f.ocr.tmp" (move /y "%%f.ocr.tmp" "%%f" >nul)
)
```

**Key flags:**

- `--skip-text` — leaves text-based PDFs alone; only OCRs image-only ones
- `--output-type pdf` — standard PDF output, faster than PDF/A
- Temp-file dance prevents corruption from partial OCR failures

**Dependencies:** `pip install ocrmypdf` plus Tesseract on Windows (from UB-Mannheim's GitHub).

**Timing estimates:**

- Text-based PDFs: instant (skip-text recognizes them)
- Scanned PDFs: 2-10 minutes per book (200-300 pages typical)
- A few dozen core rulebooks: 1-2 hours
- Hundreds of books: overnight

**Then add to digest_all.bat:**

```batch
echo --- RPG Search Library ---
%PY% "%PIPELINE%" "I:\RPG\_SearchLibrary\1-Raw" "I:\RPG\_SearchLibrary\2-Digested"
```

**User confirmed setup complete for the games library.**

**Practical note about Claude project loading:** Don't dump 100+ digested core rulebooks into a single Claude project — context window and project file limits make it unworkable. Pattern: local Obsidian + grep handles "find which book covers this"; focused subsets get loaded into specific Claude projects per session.

---

## 11. The TTRPG Conversation research project (introduced at end)

User described a new research project:

> "TTRPGs have a core element we can call 'The Conversation'. Even solo mode games have it even if it is a monologue, a journal, or in one's head. The playstyle, systems, and theory discussions over the years have treated The Conversation differently, often only implicitly. I want to scan all the games and other content (e.g., Dragon magazines) in my library and compose a historical record of this element."

This is the natural use case for the SearchLibrary. Discussed at length (the next brief picks up here). Research project framing only; no work begun yet.

---

## 12. State at end of Part 1

**Pipeline state:**

- All Phase A1 keyword improvements applied
- Loom branding purged from active code
- Manifest support fully integrated with validation
- `.nlm.md` sidecar bug fixed in all three locations
- Sticky-folder behavior verified working

**Archive state:**

- Two-library structure (AI Backups + Loom) successfully migrated
- 0 errors in re-run after migration
- RPG search library structure planned, OCR tooling identified

**Pending work explicitly deferred:**

- Phase A2 (scikit-learn TfidfVectorizer)
- Phase B (spaCy + topics field)
- `project_name` fallback in claude_to_markdown when metadata file missing
- Optional `--clean-stale` flag for converter

**Active project carrying into Part 2:**

- The TTRPG Conversation historical record
- The RPG Search Library buildout
