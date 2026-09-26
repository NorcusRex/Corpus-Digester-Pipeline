# Pipeline Guide

Full reference for the digestion pipeline. Converted from the original fixed-width text guide; sections that were ASCII tables or directory trees are kept as code blocks because their layout is the content.

## NAMED PIPELINE INPUTS

Data the pipeline reads but does not produce. All are configuration, not code, and belong beside a corpus's marshaling wrapper in its _Tools folder.

<PROJECT_UUID>`_manifest.json` Lists every conversation in a Claude project by UUID and title. Consumed by `claude_to_markdown.py` to recover the conversation-to-project mapping that Claude's data export does not preserve. Detected by content shape (project_uuid + conversations), never by filename, so it can sit anywhere inside an export. Its format contract is `project-manifest-format.md`, shipped in references/. Unknown keys are ignored, so a manifest from a newer format revision is read without complaint.

Note it deliberately does NOT follow the corpus filename convention. It is a machine-read input keyed by project UUID, not a corpus document.

`project_names.tsv` Maps ChatGPT project and GPT ids to human-readable folder names. Applied by `rename_chatgpt_projects.py` after conversion and before the metadata pass, so keywords and the index reflect the final names. Idempotent.

<corpus>_ai_subset.txt Selection list naming which digested AI conversations belong to a given corpus. Consumed by `sync_subset.py` via `sync_gdrive_corpus.bat`.

A word list (optional) Passed with `--dictionary`. Used only to PREVENT keyword rejections, never to cause them.

## NOTE ON SCRIPT NAMES

The Loom-specific batch files were replaced by generic ones that take the corpus root and remote as parameters:

```
sync_loom.bat            ->  sync_gdrive_corpus.bat
push_loom.bat            ->  push_gdrive_corpus.bat
merge_loom_to_drive.bat  ->  merge_corpus_local_to_drive.bat
pull_matt.bat            ->  pull_gdrive_folder.bat
digest_all.bat           ->  corpus_wrapper.template.bat
```

No corpus name, local path, or Drive path appears in any of them. Each corpus gets one copy of `corpus_wrapper.template.bat` in its _Tools folder, with its paths filled in; that wrapper calls the generic scripts in order. Configuration files such as the AI selection list and `project_names.tsv` are data, not code, and live beside the wrapper.

Sections below that still name the old scripts describe the same behaviour under the new names.

A set of Python scripts that convert mixed file formats (.docx, .xlsx, .pdf, .html, .rtf, ChatGPT JSON exports, Claude data exports, .md, .txt) into a parallel folder tree of Markdown files with searchable metadata. Designed for personal knowledge archives: AI conversation exports, notes from various sources, design documents, anything you want stored as clean Markdown for searching via Obsidian, Claude's Drive connector, NotebookLM, or grep.

Output is lossless. Every cell, footnote, comment, image, formula, tracked change, annotation, outline entry, and form field from the source is preserved -- either inline in the rendered Markdown, in a labeled appendix section, or extracted to a sibling _media/ folder and referenced by relative path.

## FILES IN THIS PACKAGE

- **`process_folder.bat`** — Windows launcher (double-click to run)
- **`process_folder.py`** — Orchestrator that walks a folder tree

```
docx_to_markdown.py       .docx  -> .md  (+ _media/)
xlsx_to_markdown.py       .xlsx  -> .md
pdf_to_markdown.py        .pdf   -> .md  (+ _media/)
html_to_markdown.py       .html  -> .md  (+ _media/ for inline images)
                          For Evernote exports and other HTML notes.
rtf_to_markdown.py        .rtf   -> .md
                          Pure stdlib RTF parser. Handles formatting,
                          lists, hyperlinks, headings, unicode.
chatgpt_to_markdown.py    ChatGPT export -> N .md files
claude_to_markdown.py     Claude data export -> N .md files
                          Detects exports by their (conversations.json
                          + users.json + projects/) signature. Renders
                          conversations with branches, thinking blocks,
                          tool use, attachments. Per-project memories
                          and metadata get sidecar .md files.
add_metadata.py           Adds keywords (TF-IDF when corpus has 5+
                          files), outline, indexed_at to every .md
                          file's frontmatter and body
```

- **`rename_chatgpt_projects.py`** — Renames ChatGPT project folders from project_<id>/ to human-readable names. Runs automatically as part of every pipeline run if project_names.tsv is present next to this script. Can also be run standalone.
- **`project_names.tsv`** — Optional. Maps ChatGPT Project / Custom GPT IDs to the human-readable folder names you want. See "PROJECT NAME MAP" section below for the format.

- **`clean_stale.py`** — Detects (and optionally deletes) digested .md files whose source no longer exists in the raw tree. Report-only by default. See "STALE FILE CLEANUP" section below.

- **`corpus_wrapper.template.bat`** — The one per-corpus artifact. Copy it into a corpus's `_Tools/`, edit the configuration block at the top, and run it: it mirrors the AI subset, digests, catalogues `4-Canon`, stale-checks and self-checks, optionally pushing to Drive. Replaces the old `digest_all.bat`, which digested several libraries in one run; each corpus now has its own copy. See "DIGESTING MULTIPLE LIBRARIES".
- **`pipeline_selfcheck.py`** — Six checks over the pipeline's own output: completeness against `1-Raw`, index integrity, frontmatter, filenames, duplicate content. Reports only; it has no deletion path.
- **`tier_sidecars.py`** — Writes a catalog record beside each artifact in an authored tier, leaving the artifact byte-identical. Used for `4-Canon`.
- **`inspect_chatgpt_assets.py`** — Read-only report on how a ChatGPT export refers to its images and audio. Prints no conversation text.
- **`lexicon/`** — Word lists and glossaries used to protect real terms from the keyword artifact filter. See `lexicon/README.md`.

- **`sync_subset.py`** — Generic engine: idempotently mirrors a named subset of digested subfolders from a source tree into a destination. Contains no site-specific knowledge. See "SUBSET MIRROR".
- **`sync_gdrive_corpus.bat`** — Generic launcher: takes a selection list, a source export tree and a destination, and calls sync_subset.py. Holds no corpus paths. Called once per source, so a corpus pulling from both Claude and ChatGPT calls it twice — which is what the per-corpus wrapper does.
- **`<corpus>_ai_subset.txt`** — Corpus DATA, not tooling: the list of which digested folders belong to that corpus. Lives beside the corpus's wrapper in its `_Tools/`, not in the pipeline folder.

Drive transfer helpers (optional -- only if you sync libraries to or from Google Drive). These require rclone, a free third-party tool; they are NOT Python and do NOT touch the converters. See the "GOOGLE DRIVE TRANSFER (rclone)" section below before using them.

- **`merge_corpus_local_to_drive.bat`** — One-time reconciliation: merges a local corpus up to its Google Drive copy using three guarded passes (two dry runs, then the real upload). Non-destructive.
- **`push_gdrive_corpus.bat`** — Ongoing use: pushes local corpus changes up to Google Drive. Non-destructive; never deletes anything in Drive.
- **`pull_gdrive_folder.bat`** — Pulls a shared Drive folder DOWN into the raw tree, converting native Google Docs to .docx during the copy so the pipeline can read them. Note it is *folder*, not *corpus*: pulling from a shared Drive folder is not specific to any collaborator or corpus.
- **`_rclone_common.bat`** — Shared preamble for the four above: finds rclone and checks the "drive:" remote exists. Not run directly.

All four take their paths as parameters. Nothing above holds a corpus name, a local path or a Drive path.

The core .py files and the .bat must live in the same folder. The two rename-related files (`rename_chatgpt_projects.py` and `project_names.tsv`) are optional -- the pipeline runs without them. The .bat finds the .py files via its own location, and the orchestrator imports the converters as Python modules.

## ONE-TIME SETUP

- **1.** Install Python 3.9 or newer. Download from https://www.python.org/downloads/ On the installer's first screen, tick "Add Python to PATH".

- **2.** Put all the .py files plus process_folder.bat in a stable directory, e.g.: C:\Tools\digestion-pipeline\

- **3.** Open process_folder.bat in Notepad and edit two lines near the top:

```
set "INPUT_DIR=C:\Users\YourName\Documents\Archive\source"
set "OUTPUT_DIR=C:\Users\YourName\Documents\Archive\digested"
```

Point INPUT_DIR at whatever folder holds your raw mixed files. OUTPUT_DIR will be created if it doesn't exist.

- **4.** Save the .bat file.

The first time you run it, the .bat will install the pypdf library automatically (needed for PDF support). If pypdf can't be installed, PDFs will be skipped and other formats still process normally.

## RUNNING THE PIPELINE

Three equivalent ways to run it:

- **A.** Double-click process_folder.bat in Explorer. Uses the INPUT_DIR / OUTPUT_DIR paths set inside the file.

- **B.** Drag a folder onto process_folder.bat in Explorer. The dragged folder overrides INPUT_DIR. OUTPUT_DIR comes from the .bat file.

- **C.** From a command prompt: process_folder.bat "C:\path\to\source" "C:\path\to\dest"

The .bat keeps its console window open at the end so you can read the summary. Press any key to close it.

Optional flags (added after the two paths):

- `--no-metadata` — Skip the keyword / index pass at the end. Useful for fast re-imports; you can run the metadata pass separately later.

- `--keywords N` — Number of keywords per file. Default 10.

- `--dry-run` — List what would happen without writing anything. Good for verifying the source tree.

- `--debug` — Print full tracebacks for any per-file errors.

- `--no-log` — Skip writing the log file.

- `--log-dir DIR` — Directory for the log file (default: OUTPUT_DIR).

- `--clean` — Delete the contents of OUTPUT_DIR before running. Use when you want a guaranteed-fresh build (e.g. after deleting source files and wanting their converted outputs gone too).

- `--no-rename` — Skip the ChatGPT project folder rename step. Otherwise, project_names.tsv next to this script is applied automatically if present.

`--rename-tsv` FILE Path to a different project name TSV. Defaults to `project_names.tsv` next to `process_folder.py`.

- `--no-nlm` — Skip emission of NotebookLM-friendly .nlm.md sidecar files. By default, every .md gets a frontmatter-stripped <name>.nlm.md sibling that NotebookLM can ingest cleanly.

Example: `process_folder.bat` "D:\Archive\raw" "D:\Archive\digested" `--keywords` 15

## LOG FILES

Every run automatically writes a timestamped log file to your OUTPUT_DIR, named:

```
_pipeline_YYYYMMDD_HHMMSS.log
```

The leading underscore sorts it to the top of the directory in Explorer. Each run creates a new log file, so run history is preserved -- delete old ones manually if they accumulate.

The log captures the complete console output verbatim:

- Every per-file processing line, with kind and relative path
- All [error] and [warn] messages from the orchestrator and from individual converters
- The full conversion summary
- The metadata pass result

When the pipeline reports errors, the log file is the first place to look. Open it in Notepad and search (Ctrl+F) for "[error]" to find the specific files that failed and the exception messages. The orchestrator continues past errors, so a single bad file does not stop the rest of the run -- but the count is reflected in the summary's `errors:` line.

To skip log writing entirely, pass `--no-log`. To direct the log to a separate folder (useful if you want to keep run history outside the digested archive), pass `--log-dir` "C:\path\to\logs".

## CORPUS INDEX  (formerly "manifest")

Every run also writes a `_index.json` file at the root of your OUTPUT_DIR. (Prior runs named this `_manifest.json`; that legacy name means the SAME file and stays valid until a re-digest replaces it. The rename ends a naming collision: this content index is NOT the Claude-export PROJECT-GROUPING manifest, which is a separate `<PROJECT_UUID>_manifest.json` file used only to group conversations by project.) It contains:

- generated_at:   timestamp of the run
- output_root:    absolute path of OUTPUT_DIR
- file_count:     number of .md files in the index
- stats:          conversion summary counts (docx, xlsx, pdf, etc.)
- files:          a list of every .md file with its size and full parsed frontmatter

It is metadata-only and written PRE-PUSH, so it intentionally contains NO Drive file IDs (the Drive objects do not exist when it is written). That is by design: consumers resolve IDs at search time, not from this file. Do not "fix" this by adding IDs.

Use cases:

- Auditing. To check whether a specific conversation made it into the archive, search _index.json (it's plain JSON) for the conversation_id rather than crawling the folder tree.
- Reconciliation. The index lets external tools verify what was processed without scanning every file.
- History. Keep a copy of an old _index.json before a re-run if you want to diff what changed.

The index is regenerated on every run. Move it elsewhere first if you want to preserve a pre-run snapshot.

## KEYWORD EXTRACTION

Each .md file gets a `keywords` field in its frontmatter, populated by the metadata pass at the end of the run. The keywords are also shown in the auto-index block in the body.

How keywords are picked:

- For corpora of 5+ files, TF-IDF ranking is used. Each candidate term is scored by how often it appears in this document (weighted sublinearly so a single repeated word doesn't dominate) divided by how often it appears across the whole corpus. The result favors terms that are DISTINCTIVE to a document, not just frequent.
- For smaller corpora or single-file invocations, raw frequency ranking is used as a fallback.

What gets filtered out before scoring:

- Code blocks and inline code
- Stop words (common English words, plus structural words from ChatGPT's export schema like "user", "assistant", "content", "audio", "asset", "pointer")
- Voice-mode and multimodal stub strings ("[audio_asset_pointer content omitted]" etc.) so a voice chat's keywords reflect what was discussed, not the placeholder text

The number of keywords per file is configurable via `--keywords` N (default 10).

## NOTEBOOKLM SIDECARS

Google's NotebookLM treats YAML frontmatter as literal text rather than as metadata, which clutters its responses and confuses its ingestion. To work around this without losing frontmatter for tools that DO understand it (Obsidian, Drive search, the corpus index), the pipeline writes a frontmatter-stripped sibling for every .md file:

notes/

- **`drama-dice.md`** — <- canonical, with YAML frontmatter
- **`drama-dice.nlm.md`** — <- stripped copy for NotebookLM upload

The `.nlm.md` sidecars contain:

- The full body content of the source .md
- All headings, lists, tables, links, images, code blocks
- Footnote markers and footnote definitions where present

The `.nlm.md` sidecars do NOT contain:

- YAML frontmatter (the --- block at the top)
- The auto-generated index block (keywords, outline summary that the metadata pass adds inside HTML comments)

Workflow for NotebookLM:

- **1.** Run the pipeline as usual.
- **2.** When uploading to NotebookLM, select the .nlm.md files rather than the .md files. NotebookLM ingests them cleanly with no YAML noise in responses.
- **3.** Continue using .md files in Obsidian for property-based search, Drive connector queries, etc.

Sidecar maintenance:

- The pipeline regenerates sidecars on every run, but only re-writes a sidecar if its content has actually changed. This keeps Drive sync churn minimal.
- Sidecars are excluded from the metadata pass (they don't get keywords or auto-index blocks of their own).
- Sidecars are excluded from the corpus index (they're derivative, not canonical content).
- To skip sidecar generation for a single run, pass --no-nlm.
- To delete all existing sidecars, run: del /s "C:\path\to\digested\*.nlm.md" or use the Explorer search "ext:.nlm.md" and delete results.

## PROJECT NAME MAP

ChatGPT exports include project membership only as opaque IDs (e.g. g-p-67f8deab3a0c819189bcc16e697ccd67), not as the human- readable names you see in the ChatGPT UI. By default the pipeline creates folders like:

```
conversations/project_g-p-67f8deab3a0c819189bcc16e697ccd67/
```

These are correct but unreadable. The project name map lets you turn them into:

```
conversations/My Project Name/
```

Setup:

- **1.** Create a file named project_names.tsv next to the orchestrator scripts (same folder as process_folder.py).

- **2.** For each ChatGPT Project or Custom GPT you want renamed, add a line with the project ID, then a TAB character, then the human name you want:

- **`g-p-67f8deab3a0c819189bcc16e697ccd67`** — My Project Name
- **`g-p-67f8f4b93e648191bfa46a3845719182`** — Theory Project
- **`g-p-686b8b9a278881918dce1b0212a53bd0`** — Philosophy

The separator MUST be a real tab character, not spaces. Lines starting with # are comments. Blank lines are ignored.

- **3.** To find a project's ID, visit chatgpt.com, open the project, and copy the part of the URL between /g/ and the first / or ? after it. The full ID looks like g-p- followed by 32 hex characters. (Slug suffixes after the ID in the URL are for readability and should NOT be included in the TSV.)

- **4.** Forbidden Windows folder characters (< > : " / \ | ? *) in names get replaced with underscores automatically. Names with "My: Project" become folders like "My_ Project".

Behavior:

- The rename runs automatically as part of every pipeline pass, AFTER conversion but BEFORE the metadata pass and corpus index. This means keywords, the auto-index, and the corpus index all reflect the final renamed paths.
- The rename is idempotent. Running the pipeline against an already-renamed archive is a no-op for those folders -- the "already named: N" line in the summary tells you how many were already correct.
- The rename is "sticky." Once renamed, the folder stays renamed across re-runs even when new conversations are added to that project. The pipeline re-identifies the correct folder by reading conversation_template_id from the frontmatter inside.
- To skip the rename for a single run, pass --no-rename.
- To use a different TSV for one run, pass --rename-tsv FILE.

If `project_names.tsv` does not exist next to the orchestrator, the rename step silently skips. Users who don't want this feature don't need to do anything; the pipeline still works.

Standalone use:

`rename_chatgpt_projects.py` can be run by itself to rename folders in any directory tree:

```
python rename_chatgpt_projects.py project_names.tsv \
    "C:\path\to\digested" --dry-run
```

The `--dry-run` flag previews changes without making them.

## WHAT GETS PRESERVED, BY FORMAT

.DOCX

- Headings (1-6, plus Title and Subtitle)
- Bold, italic, inline code, hyperlinks
- Bullet and numbered lists with nesting
- Tables, block quotes
- Images: extracted to <name>_media/, inlined with alt text
- Footnotes and endnotes: rendered as [^fn1] / [^en1] at their original anchor, full text in "## Footnotes" / "## Endnotes"
- Comments: rendered as [^c0], full text with author and date in "## Comments"
- Tracked changes: insertions render as plain text; deletions render as ~~strikethrough~~ with author/date in an HTML comment
- Document properties (title, author, dates) in YAML frontmatter

.XLSX

- All sheets in original order, including hidden sheets (which are rendered with a "(hidden)" label and listed in frontmatter)
- Cell values: numbers, strings (resolved from shared strings), booleans, dates (serial numbers converted to YYYY-MM-DD when the cell's number format identifies it as a date)
- Formulas: cached value appears in the table; formula source listed in a per-sheet "Formulas" appendix
- Comments: per-sheet "Comments" appendix with author and text
- Hyperlinks: rendered inline in the table as Markdown links
- Merged cells: value duplicated across the merged range (matching Excel's visual behavior); ranges listed in appendix
- Defined names listed at the top
- Output preserves positional info: column letters as the first row, row numbers as the first column

.PDF

- Document metadata: title, author, subject, keywords, dates
- Outline / bookmarks: rendered as "## Outline" with page targets
- Per-page text: each page becomes "## Page N"
- Images: extracted from each page, saved to <name>_media/, listed under each page's "Images on this page" subsection
- Annotations (comments, sticky notes, highlights, link annotations): per-page list with author, date, type, contents
- Form fields: AcroForm field names and values in "## Form fields"
- Embedded files / attachments: extracted to <name>_media/, listed in "## Attachments"
- Scanned PDFs are detected (pages exist but no extractable text) and flagged with "likely_scanned: true" in frontmatter

.HTML / .HTM

- Headings (h1-h6), bold, italic, underline (rendered as bold since Markdown has no underline), strikethrough, inline code
- Code blocks (<pre>)
- Bullet and numbered lists, with nesting
- Tables (rendered as Markdown pipe tables)
- Block quotes
- Hyperlinks
- Document metadata from <title> and <meta> tags surfaces into YAML frontmatter (author, created, modified, keywords, etc.)
- Inline images:
- data: URLs (base64-encoded inline images, common in Evernote exports) are extracted to <name>_media/ and inlined as ![alt](relative/path)
- http(s) URLs stay as remote links in the Markdown
- Relative paths pass through unchanged
- Embedded video/audio/iframe tags are noted as "[embedded video: src]" rather than rendered, since Markdown has no embed syntax
- LIMITATIONS: CSS styling (color, font, alignment) is not preserved. Forms render their structure but inputs are not interactive in Markdown. Deeply nested lists may flatten slightly when re-flowed -- this is a cosmetic issue, all content is preserved.

USE CASE: Evernote notes exported as HTML. Drop the .html files anywhere in your source tree and the pipeline converts them alongside everything else.

.RTF

- Plain paragraph text and line breaks
- Bold, italic, underline (rendered as <u>...</u>), strikethrough
- Bullet and numbered lists (best-effort; nested lists may flatten one level)
- Headings (paragraphs with large \fs sizes are mapped to H1/H2/H3 by point size: >=24pt -> H1, >=18pt -> H2, >=14pt -> H3)
- Hyperlinks via {\field {\fldinst HYPERLINK "url"} {\fldrslt text}}
- Smart quotes, em/en dashes, non-breaking spaces, bullets
- Unicode characters (\uNNNN escapes and \'XX hex bytes, decoded using the active codepage)
- LIMITATIONS: page layout, margins, headers/footers, font families, colors, exact sizes, embedded images, OLE objects, drawing primitives, and complex tables are not preserved. The renderer is tuned for plain document content (notes, design documents, prose with simple formatting), which is what RTF is most often used for in practice.

USE CASE: Evernote notes saved as RTF, TextEdit/WordPad documents, RTF copies of Word docs.

CONVERSATIONS.JSON  (ChatGPT exports)

- One Markdown file per conversation, named YYYY-MM-DD__title-slug.md
- Active conversation branch (root -> current_node) renders first
- Inactive branches (regenerations, abandoned forks) preserved in a labeled "Inactive branches" section
- System stubs with no content are dropped silently
- Multimodal parts get a placeholder so message structure stays intact even when the original content can't be rendered as text
- Thinking-model reasoning steps (empty assistant nodes whose chain-of-thought OpenAI does not include in exports) are collapsed into a single italic marker like "*[3 reasoning steps]*" rather than rendered as confusing empty headers.
- Frontmatter fields specific to ChatGPT conversations:

- **`conversation_id`** — Stable id from the export
- **`created`** — When the conversation was started
- **`updated`** — When the conversation record was last touched (rename, archive, share, move). Can be later than the actual last message; do not use this to answer "when was this conversation last used?" -- use last_message_time below.
- **`last_message_time`** — Timestamp of the actual most recent message body. This is what you want for "when was this last active?"
- **`active_message_count`** — Visible messages on the active branch
- **`total_node_count`** — Total nodes in the conversation tree
- **`model_slug`** — Model used. "<unknown>" for older conversations where the export does not record a model. Always present.
- **`conversation_template_id`** — Project / Custom GPT membership
- **`gizmo_id`** — Custom GPT ID, if applicable
- **`has_reasoning_steps`** — True if any reasoning-step markers were collapsed
- **`reasoning_step_count`** — Total number of empty reasoning steps
- **`is_voice`** — True if any voice-mode stubs appeared in the conversation

- PROJECT AND CUSTOM GPT GROUPING: Conversations that belong to a ChatGPT Project or a Custom GPT are placed into a subdirectory inside the export folder:

- **`project_<id>/`** — - for ChatGPT Projects (template ID g-p-...)
- **`gpt_<id>/`** — - for Custom GPTs / other templates Regular conversations (no project, no custom GPT) sit directly in the export folder with no extra nesting. NOTE: ChatGPT exports include only the project/GPT IDs, not the human-readable names. The folders are named after the IDs (e.g. project_g-p-abc123). Open one of the conversations inside to see what the project is, then rename the folder to whatever you like -- the conversations themselves still carry the original `conversation_template_id` in their frontmatter, so re-runs will keep grouping them correctly even if you rename later.

CLAUDE DATA EXPORTS A Claude export is a folder containing `conversations.json`, `users.json`, `memories.json`, and a projects/ subfolder. The pipeline detects these automatically and converts them as a unit (skipping the individual files during the per-file walk).

Output structure mirrors the source path. Inside the converted export folder you get:

conversations/

- **`YYYY-MM-DD__title-slug.md`** — (one per conversation, flat)

projects/

- **`<short-uuid>__name-slug.md`** — (one per project; metadata only)

memories/

- **`conversations_memory.md`** — (cross-conversation memory)
- **`project_<short-uuid>__name-slug.md`** — (per-project memories)

- **`users.md`** — (account info)

Conversation rendering:

- Active branch (root -> latest message at every fork) renders first, with branch points resolved by recency.
- Inactive branches (regenerations, abandoned forks) preserved in a labeled "Inactive branches" section at the bottom.
- Thinking blocks rendered as collapsible <details> / <summary> so the main flow stays readable. Both the summary lines and full thinking text are preserved.
- Tool use and tool result blocks rendered as labeled named sections with the tool's input as JSON and the result text inline.
- Attachments: the export embeds the extracted text content of file uploads. This is rendered inline in a fenced code block with the file name, type, and size as a label.
- Files: the export records file names and UUIDs but does NOT include file bytes. Each is listed by name with a note that the bytes are not in the export.
- Frontmatter fields specific to Claude conversations:

- **`conversation_id`** — uuid from the export
- **`created`** — conversation create time
- **`updated`** — conversation update time
- **`last_message_time`** — timestamp of the latest message
- **`active_message_count`** — messages on the active branch
- **`total_message_count`** — total messages including branches
- **`has_thinking_blocks`** — True if any thinking blocks
- **`thinking_block_count`** — Total thinking blocks
- **`has_tool_use`** — True if any tool was invoked
- **`tool_use_count`** — Total tool invocations
- **`has_attachments`** — True if any message had attachments
- **`has_files`** — True if any message had file uploads

IMPORTANT LIMITATION: Claude's export does NOT preserve the conversation -> project mapping. Conversations are flat under conversations/, not grouped by project. The project/ folder contains the project metadata (name, description, prompt template, doc count) and the memories/ folder contains the per-project memory text, but you cannot determine from the export which conversations belonged to which project. This is a limitation of Claude's export format, not of this converter.

WORKAROUND: PROJECT MANIFESTS You can recover project grouping by generating manifest files yourself. A manifest is a JSON file describing which conversations belong to a given project, in this format:

```
{
  "project_uuid": "<uuid>",
  "conversation_count": <int>,
  "conversations": [
    {"uuid": "<conversation-uuid>", "title": "<title>"},
    ...
  ]
}
```

To generate one, open Claude inside the project (incognito chat works fine) and run a prompt like:

Generate a JSON manifest of every conversation in this project. Steps:

- **1.** Use the recent_chats tool to retrieve all conversations. Paginate with the `before` parameter (set to the earliest `updated_at` from the previous batch) until no more results. Use n=20 per call.
- **2.** Extract each conversation's UUID and title.
- **3.** Create a JSON file at /mnt/user-data/outputs/<PROJECT_UUID>_manifest.json (replacing <PROJECT_UUID> with the actual UUID below) using the structure above. Order oldest to newest. Escape quotes in titles. Then call present_files. Project UUID: <PASTE PROJECT UUID HERE>

Save the resulting JSON files into the export's projects/ folder (alongside the project metadata files) before running the pipeline. The converter detects them by content (top-level project_uuid + conversations keys), not filename.

```
With manifests present, conversations route into per-project
subfolders inside conversations/:
  project_<short-uuid>__<name-slug>/
Frontmatter on each grouped conversation gains project_id and
project_name fields.
```

Folder names are sticky across re-runs: rename a project folder by hand and the converter will keep using your renamed folder rather than recreating the default name.

The converter validates manifests at conversion time. After each run, the summary reports:

- manifests loaded
- conversations grouped vs ungrouped
- stale manifest entries (UUIDs not in the export -- usually from conversations deleted between manifest generation and export download)
- title mismatches (conversation renamed in Claude after manifest was generated)
- UUID conflicts (same conversation claimed by two project manifests -- a bug in the manifests, please regenerate)

Workflow tip: generate manifests AFTER downloading the export, not before. That eliminates the drift window where new chats happen between manifest generation and export.

Recent_chats has a known pagination bug that may cause it to skip exactly one conversation at the boundary between batches (timestamps shared across the boundary get dropped). After generating each manifest, glance at the count vs what you see in the sidebar; if off-by-one, manually patch the missing conversation's UUID and title into the JSON.

LEGACY CONVERSATIONS: very old Claude conversations may have null parent_message_uuid on every message (threading wasn't tracked yet). The converter detects this and falls back to a flat chronological sequence with no inactive branches, so the content is still preserved correctly.

.MD Copied through unchanged. Lets you keep hand-authored canon in the source tree and have it flow into the digested archive alongside the converted files.

.TXT Wrapped with minimal YAML frontmatter so the metadata pass can index it like everything else. Body is preserved as-is.

```
IMAGES, AUDIO, VIDEO, GRAPHIC SOURCES
  (.png .jpg .jpeg .gif .webp .svg .bmp .tiff
   .wav .mp3 .m4a .ogg .flac .aac .opus
   .mp4 .mov .webm .avi .mkv .m4v
   .xcf .psd .ai .sketch .afdesign .afphoto)
  Copied through unchanged with their original filenames, mirroring
  the source folder structure. The pipeline does not transcribe
  audio, describe images, or render graphic-editor source files,
  but it preserves them so they remain searchable by filename and
  accessible alongside the digested text. The graphic-source
  formats (GIMP .xcf, Photoshop .psd, Illustrator .ai, Sketch,
  Affinity Designer/Photo) are preserved as the byte-for-byte
  source for any rendered images sitting next to them in the
  source tree.
```

CHATGPT EXPORT EXTRAS ChatGPT export folders (folders containing `user.json` + at least one conversations*.json) are detected automatically. Inside an export folder, EVERY file is preserved.

Auxiliary JSON files are RENDERED to Markdown rather than copied:

- user.json, user_settings.json, shared_conversations.json, message_feedback.json, model_comparisons.json, export_manifest.json Each becomes a .md file with top-level fields as ## headings, nested structures as bullet lists, and the original JSON preserved verbatim in a code block at the end. This makes them searchable through the Drive connector while staying lossless. Notably: your ChatGPT custom instructions live in user_settings.json, so they end up as a readable section of user_settings.md.

Other aux content is copied through unchanged:

- chat.html (an alternate HTML view of the conversations, redundant with the converted .md files)
- file-XXXXXXXX (no extension): user-uploaded content that ChatGPT stored without a recognizable extension
- audio/ subfolders containing voice messages

ANYTHING ELSE (outside ChatGPT exports) Files that aren't a recognized format and aren't media files are marked "unsupported" in the summary. They are not copied to the output. If you want them preserved too, either move them into a folder structure the pipeline understands, or use a tool outside this pipeline to back them up.

## GOOGLE DRIVE TRANSFER (rclone)

This section explains the three .bat files that move libraries between local disk and Google Drive. None of this is required to use the pipeline. It exists for two specific situations:

- **1.** You want a Google Drive copy of a local library kept current, as a backup -- but you have been burned by sync tools deleting your data and you do not trust them.

- **2.** A collaborator hands you documents via a shared Drive folder, and those documents are native Google Docs that the pipeline cannot read directly.

WHY NOT JUST USE GOOGLE DRIVE DESKTOP?

Drive Desktop is a SYNC tool. Sync means changes propagate in both directions, including deletions. The classic failure: a local disk fault makes files appear missing, Drive Desktop faithfully mirrors "missing" up to the cloud, and the cloud copy -- your backup -- is deleted to match. The backup destroys itself precisely when you need it.

The tool used here, rclone, has a COPY mode that is one-directional and non-destructive. `rclone copy A B` means: bring B up to date with A by uploading new and changed files. It NEVER deletes anything in B. If the source vanishes, the destination simply stops receiving updates -- it does not get wiped. This is the property that makes it safe as a backup mechanism. (rclone also has a `sync` mode that DOES delete; these scripts deliberately never use it.)

The trade-off: rclone is a separate tool with a one-time setup, and it does not run silently in the background the way Drive Desktop does. You run these .bat files on demand. That is intentional. A backup you trigger deliberately cannot delete your data because of a sync event you did not see coming.

ONE-TIME RCLONE SETUP

- **1.** Download rclone from https://rclone.org/downloads/ (Windows, 64-bit). It is a single rclone.exe. Put it on your PATH, or in the same folder as these .bat files.

Verify: open a command prompt, run `rclone version`. A version number means it is installed.

- **2.** Run `rclone config` and create a Google Drive remote. The wizard is interactive; answer roughly:
- n              (new remote)
- name: drive    (lowercase -- the .bat files expect exactly this name)
- storage: drive (Google Drive -- pick by name; the number varies between rclone versions)
- client_id / client_secret: see note below
- scope: 1       (full access)
- auto config: y (opens a browser to authorize)
- Shared Drive:  n  (a folder shared WITH you is not the same as a Drive-wide Shared Drive)

Verify: `rclone lsd drive:` should list your Drive's top-level folders.

- **3.** About client_id: leaving it blank uses rclone's shared internal key, which Google rate-limits aggressively. For a one-time small transfer this is tolerable; for the initial bulk merge of a large library it can be very slow. Creating your own client_id in Google Cloud Console (free, ~10 minutes, one time) removes the throttling. The rclone docs walk through it with screenshots: https://rclone.org/drive/#making-your-own-client-id You can start with the blank key and swap in your own later by re-running `rclone config` -- the authorization is not lost.

- **4.** The remote's authorization token is stored at %APPDATA%\rclone\rclone.conf Treat it like a password. Back it up alongside your other config; without it rclone cannot authenticate (though you can always re-run `rclone config` to regenerate it).

THE THREE SCRIPTS

- **`merge_corpus_local_to_drive.bat`** — Run ONCE, the first time, when a local corpus and its Drive copy have drifted apart and you want them merged with local winning. It runs three passes and pauses between each:

```
Pass 1  Dry run, default comparison
        (file size + modification
        time). Shows what WOULD be
        uploaded. Nothing is written.
Pass 2  Dry run, content-hash
        comparison (--checksum). If
        this list is noticeably
        bigger than Pass 1, some
        files match in size+time but
        differ in content -- worth
        knowing before committing.
Pass 3  The real upload.
```

```
Passes 1 and 2 print to the CONSOLE
so you can read them live; the script
prompts between each. Pass 3 is
silent on the console; rclone's own
`--log-file` flag captures its output
to a dated log next to the .bat
(loom_merge_YYYY-MM-DD.log). The two
dry-run passes are diagnostic by
design and not recorded; the real run
is what gets the file record.
```

```
"Merge" here means: every file local
has is pushed up; anything Drive already
had that local lacks is LEFT ALONE;
identical files are skipped. The
--update flag means a file that is
newer in Drive than locally is NOT
overwritten -- this matters if anyone
edits through the Drive web UI. Nothing
in Drive is ever deleted.
```

- **`push_gdrive_corpus.bat`** — Run REPEATEDLY, for ongoing backup, after the one-time merge is done. Same non-destructive logic as Pass 3 of `merge_corpus_local_to_drive.bat`, but with no prompts. A good habit is to run it after a pipeline session so the Drive copy stays current, which is what the per-corpus wrapper's `--push` does. Safe to run as often as you like; identical files cost nothing. Two-pass structure: a `--dry-run` pass prints what it WOULD copy to the console, then the real pass writes its output to a dated log (`push_<corpus>_YYYY-MM-DD.log`). Same-day re-runs append to the same file.

- **`pull_gdrive_folder.bat`** — Run before digesting when a collaborator has new content. This goes the OTHER direction: Drive -> local. It copies a shared Drive folder down into the raw tree, and -- crucially -- uses --drive-export-formats docx so that native Google Docs are exported as .docx during the copy. Without that flag a native Google Doc comes down as a useless pointer stub; with it, you get a real .docx the pipeline reads normally. Real files already in the folder (PDF, xlsx, an already-exported .docx) are copied through untouched. This is also rclone copy, so it is non-destructive in the same way: a file the collaborator deletes from Drive remains in your raw tree until you remove it by hand.

```
The shared folder is addressed by its
immutable Drive ID (MATT_FOLDER_ID) via
--drive-root-folder-id, not by name.
See the .bat's header comments for why
(name-based addressing fails for
"Shared with me" folders, and the
obvious --drive-shared-with-me flag
does the WRONG thing -- it would scope
the remote to every folder ever shared
with you).
```

```
Drive shortcuts inside the folder
present two distinct problems that
both surface as "dangling shortcut"
errors. First, some shortcuts point
at targets you cannot read (private
My Drive content, or items the
collaborator has deleted or
unshared). Second, at least one
shortcut creates a cycle, pointing
back at its own ancestor folder; left
unchecked, rclone follows the cycle
and recurses forever, producing
paths nested dozens of levels deep.
The script handles both with
--ignore-errors (so the unreadable
shortcuts log as errors but do not
abort the run) and --max-depth 6
(so the cycle terminates well before
it can fill the disk). The durable
fix is upstream: ask the collaborator
to remove the self-referential
shortcut and replace the others with
real shared folders.
```

```
Two-pass structure, same as
push_gdrive_corpus.bat: a --dry-run
pass to the console showing what
WOULD be copied, then the real pass
written to a dated log
(pull_<dest>_YYYY-MM-DD.log).
```

SUPPLYING THE PATHS

There are no paths to edit. Each script takes them as arguments, and the
per-corpus wrapper supplies them.

`merge_corpus_local_to_drive.bat` / `push_gdrive_corpus.bat`

```
push_gdrive_corpus.bat <LOCAL_ROOT> <DRIVE_PATH> [LOG_DIR]
```

- **`LOCAL_ROOT`** — the corpus root to back up, the folder holding the four tiers
- **`DRIVE_PATH`** — the Drive destination. rclone path syntax uses forward slashes for nesting, e.g. drive:RPG/_Design/Loom-Nick for a folder nested under RPG and _Design in My Drive. Using just drive:Loom-Nick would resolve to a top-level folder in My Drive -- not the same place. If you push to the wrong path, the non-destructive nature of rclone copy means nothing is lost; delete the rogue folder on Drive and re-run with the right path.

`pull_gdrive_folder.bat`

```
pull_gdrive_folder.bat <DRIVE_FOLDER_ID> <LOCAL_DEST> [LOG_DIR]
```

- **`DRIVE_FOLDER_ID`** — the immutable Drive ID of the shared folder. Get this from the Drive web UI: open the folder, the URL ends in /folders/<ID>. The ID is used (rather than the folder name) because "Shared with me" folders are not addressable by name from rclone's drive: remote.
- **`LOCAL_DEST`** — where in the raw tree the files should land

A WORD ON THE COLLABORATOR-DOC PROBLEM

If your collaborator is willing to do File -> Download -> Microsoft Word in Google Docs before putting files in the shared folder, then the files arrive as real .docx and `pull_gdrive_folder.bat`'s export flag is simply redundant (harmless). If they are not, the export flag does the conversion for you automatically. Either way the pipeline only ever sees .docx. You can also skip the script entirely and do a manual "Download folder" from the Drive web UI, which auto-converts native Docs to .docx and arrives as a .zip you extract into the raw tree -- exactly the same end state, just manual. The script earns its keep only when the collaborator updates often enough that doing that by hand becomes a chore.

RCLONE LOG FILES

Each rclone .bat runs in two phases on purpose: a `--dry-run` pass that prints to the CONSOLE so you can see what is about to happen, then a real pass that uses rclone's own `--log-file` flag (with `--log-level INFO`) to write a dated log next to the .bat:

```
pull_gdrive_folder.bat            pull_<dest>_YYYY-MM-DD.log
push_gdrive_corpus.bat            push_<corpus>_YYYY-MM-DD.log
merge_corpus_local_to_drive.bat   merge_<corpus>_YYYY-MM-DD.log
```

For `merge_corpus_local_to_drive.bat` the same shape applies, just with three passes instead of two: Pass 1 (default dry-run) and Pass 2 (`--checksum` dry-run) both print to the console with a prompt between each; Pass 3 (the real upload) is the one whose output is captured via `--log-file`. The two prior passes are diagnostic and intentionally NOT recorded -- you read them live before deciding to proceed.

Note on why `--log-file` rather than a shell redirect: in principle, `rclone copy ... >> `file.log` 2>&1` should capture rclone's stderr output to a file. In practice on Windows cmd this came up empty -- rclone appears to bypass stderr for progress output when no log file is specified. Using rclone's own `--log-file` flag works reliably. The visible-vs-recorded trade-off is the same either way.

Why split it this way:

- The dry-run pass is what you watch. rclone prints every file it would copy or skip, every error (dangling shortcuts and so on), and the stats line every 5 seconds. If something looks wrong, Ctrl-C before Pass 2 starts -- no changes have been made yet.
- The real pass is silent on the console because `--log-file` redirects rclone's normal output to the file. Windows `cmd` cannot cleanly tee a single command to both the console and a file without PowerShell or a third-party tool, so we use the simpler trade: console for the preview, file for the record. This is by design, not a regression.
- The log captures rclone's INFO-level output: per-file copy lines, errors, and the periodic stats line. INFO is verbose enough to confirm what happened; if logs become unwieldy, change `--log-level INFO` to `--log-level NOTICE` in the .bat and only problems will be recorded.

Behavior worth knowing rather than discovering:

- rclone's `--log-file` opens the file in append mode by default, so same-day re-runs add to the existing log rather than overwriting. That gives you the day's history in one file; it also means an unwatched log can grow indefinitely. Trim or delete old logs as housekeeping when convenient.
- The dry-run takes nearly as long as the real run on the API side (rclone has to enumerate the same tree both times). For small folders this is invisible; for a full corpus push it can add 30 seconds or so. The visibility is paid for.
- Logs are created only when rclone is actually invoked. If a .bat exits early because a sanity check fails (no rclone.exe, no remote configured, no local path) no log is written -- those errors are loud on console and there is nothing rclone has done to log.
- The log path is shown in each .bat's opening banner and in the success / error completion messages, so you always know where to look afterward.

## STALE FILE CLEANUP

`clean_stale.py` finds digested .md files whose source has gone away, so the digested tree does not silently accumulate orphans after you delete or move things in the raw tree.

It classifies every .md in the digested tree into:

- **`ok`** — Source verified present in the raw tree.
- **`skip`** — A non-conversation export object (Claude project memory, account info, ChatGPT auxiliary file). Not analyzed; never deleted.
- **`retired`** — Frontmatter carries `source_retired: true`. The owner has recorded that this source was removed deliberately. Never reported, never deleted.
- **`absent-file`** — Frontmatter names a source_file that cannot be found anywhere in the raw tree.
- **`absent-conv`** — Frontmatter has a conversation_id that appears in no conversations.json under the raw tree.
- **`orphan`** — Has frontmatter but no source_file and no conversation_id -- nothing checkable. This is the signature of files written by very old pipeline versions.
- **`no-fm`** — No frontmatter at all (possibly a hand-written note you dropped into the digested tree yourself).

DEFAULT IS REPORT-ONLY. Run it with just the two paths and it lists what it found and changes nothing:

```
python clean_stale.py <raw_dir> <digested_dir>
```

It exits 0 if everything is clean, 1 if anything was found (useful for scripting).

**An absent source is not evidence that the output is stale.** From the digested side, "the source was deleted upstream" and "the source was removed on purpose" look identical, and only you know which happened. Bulky AI exports get cleared to reclaim disk after digestion; deleting the digested output in that case destroys the only remaining copy. A source may also simply have been renamed.

So before reporting anything absent, the script looks for it by content. A digested file recording `source_sha256` whose bytes turn up in the raw tree under another name is reported as a RENAME, with both names, and is never deletable. Size is matched first, so only genuine size-matches are hashed rather than the whole tree.

To delete:

- `--delete` — Enters delete mode. On its own it now removes NOTHING; the categories below need their own flags.
- `--delete-source-absent` — Remove files whose source cannot be found. Only when you know the sources are gone for good.
- `--delete-orphans` — Remove orphan and no-fm files. Use with care: a legitimate hand-written note in the digested tree looks exactly like an orphan.
- `--max-delete-fraction N` — Refuse to delete more than this share of the analyzed files (default 0.10). A deletion that large is usually a mis-pointed raw directory, not a cleanup.
- `--force` — Override that guardrail. Requires `--yes` as well, so a large deletion can never be a single typo.
- `--yes` — Skip the confirmation prompt (for scripting).
- `--verbose` — Print every file's classification.

When a file is deleted, its paired NotebookLM sidecar (the `.nlm.md` next to it) is removed too, so the two never drift apart.

To stop a deliberately retired source being reported at all, add `source_retired: true` to the digested file's frontmatter. That records the intent in the file itself rather than depending on which flag someone remembers to pass.

## DIGESTING MULTIPLE LIBRARIES

Each corpus has its own copy of `corpus_wrapper.template.bat` in its `_Tools/` folder. The wrapper runs the pipeline against that corpus, catalogues `4-Canon`, runs `clean_stale.py` and the self-check, and optionally pushes to Drive. It exists so you do not have to launch each step by hand.

This replaced `digest_all.bat`, which digested several libraries in one run with their paths written into it. One wrapper per corpus means each corpus carries its own configuration — its selection list, its glossaries, its subject name — instead of all of them being baked into one shared file. To digest several corpora, run each wrapper.

Open your copy in Notepad and edit the CONFIGURATION block at the top: where the pipeline lives, this corpus's root, its Drive path, the subject name, and optionally a glossaries folder. Nothing below that block needs changing.

The command-line argument selects how much it does:

(no argument)        Digest, catalogue `4-Canon`, stale-check, self-check. Nothing deleted. This is the safe default.

- `--sync` — Also mirror the selected AI conversations in first.
- `--push` — Also push the result to Drive.
- `--all` — Everything.
- `--audit` — Also write a rejected-keyword report, for judging the keyword artifact filter against this corpus.
- `--dry-run` — Show what would happen; change nothing.

**The wrapper never deletes.** The stale check and the self-check report only. Removing anything means running `clean_stale.py` yourself, deliberately, with the flags above. That is a change from the old `digest_all.bat`, whose `--delete-stale` would have removed digested output whose source had merely been renamed or cleared to save space.

## TWO CORPORA, TWO DIGEST RUNS

The thing that is easy to get wrong, so it is stated before the mechanics: **an export archive is itself a corpus, and it must be digested by its own run before any other corpus can select from it.**

There is no pre-processing step, and no "partial digestion". You unzip the export straight into the archive corpus's `1-Raw` -- conversations.json, users.json, projects/, exactly as the provider wrote them. One run of `process_folder.py` then does everything in a single pass: conversion, project grouping, project renaming, metadata, NotebookLM sidecars, and the index. Project structure and readable names are produced INSIDE that one pass, not before it.

```
Claude export .zip
   |
   v  unzip, no processing
I:\AI\Backups\Claude\Exported\1-Raw\           <- the archive corpus
   |
   v  process_folder.py   (one pass: convert, group, rename, index)
I:\AI\Backups\Claude\Exported\2-Digested\
       conversations\
           project_abc12345__rpg-the-loom\
           project_def67890__rpg-theory\
   |
   v  sync_subset.py --list <this corpus's list>
I:\RPG\_Design\Loom-Nick\1-Raw\...\Exported\   <- the project corpus
   |
   v  process_folder.py   (second run, different corpus)
I:\RPG\_Design\Loom-Nick\2-Digested\
```

### The archive run should be a short one

The archive is never uploaded and never searched, so three of the passes in a full run produce nothing anyone will read:

| Pass | Cost per file | Why it is waste here |
|---|---|---|
| Metadata / keywords | two full reads and a rewrite | The most expensive pass in the pipeline. It scans every file to build TF-IDF document frequencies, then rewrites every file. The keywords are then **thrown away**, because TF-IDF is corpus-relative and the receiving corpus recomputes its own. |
| NotebookLM sidecars | one read and one write | Doubles the file count of the archive. Every sidecar is re-derived downstream. |
| `_index.json` | one full read | Reads every output file in full. Only search reads the index, and nothing searches the archive. |

Use `--archive-only`, which is shorthand for `--no-metadata --no-nlm --no-index`:

```
python process_folder.py "...\Exported\1-Raw" "...\Exported\2-Digested" --archive-only
```

What survives is what selection actually needs: conversion, project grouping, and the project name map. Roughly four reads and two writes per file come off the run.

In the wrapper, set `ARCHIVE_ONLY=1`. That also skips the `4-Canon` catalogue (an archive has no authored tiers) and the self-check, which would otherwise report missing frontmatter and a missing index as faults when they are the intended state.

**Two digest runs, in two different corpora** -- not two levels of digestion within one. The second run re-reads Markdown the first run wrote. With `--archive-only` on the first, this is the only run that does the expensive work, and it does it once. It is safe to re-read: existing `date` and `title` frontmatter are preserved, `.nlm.md` sidecars are skipped by both the metadata and sidecar passes, and keywords are recomputed against the receiving corpus. That last is the point. TF-IDF is corpus-relative, so a term's distinctiveness in Loom is a different measurement from its distinctiveness in the whole archive, and the receiving corpus should carry its own.

The archive corpus is a corpus in the ordinary sense: it has a `_Tools` folder, a wrapper, a configuration, and its own digest run. It simply has no project producing into it.

## WHAT IS THERE TO SELECT (subset_inventory.py)

`sync_subset.py` mirrors folders you name. `subset_inventory.py` tells you what the names are.

```
python subset_inventory.py SOURCE --list Loom=...\subset_claude.txt --report inv.md
```

SOURCE is the tree whose immediate subfolders are selectable -- `2-Digested\conversations` for a Claude archive, the folder holding the `project_*` folders for ChatGPT. It reports every selectable folder with file counts, size and the span of dates it covers; which of the given lists names each one; **folders no list names**; and list entries naming a folder that is not there.

The unselected list is the reason the script exists. A project nobody selected is not an error anywhere in the pipeline: it simply never reaches a corpus, and the only symptom is a search finding nothing and being unable to say why. Everything else here is convenience; that part is a real gap closed.

It reads and writes nothing but its report. Exit 1 means something is unselected or unmatched, exit 0 means everything is claimed and every entry resolved.

## SUBSET MIRROR (sync_subset.py)

The problem: some exports are topic-blind at the source. A Claude or ChatGPT data export is one undifferentiated blob covering every subject. The project/topic structure only becomes legible AFTER digestion, because digestion is the step that resolves it into named folders. If you want only a SUBSET of those folders in a downstream corpus, you cannot filter before digesting -- the thing you would filter on does not exist yet. You must digest the whole export, then select.

Doing that selection by hand-copying digested folders creates divergent trees with no provenance and no idempotency: re-digest later and you have two forests with no record of which is authoritative and no way to tell what went stale. `sync_subset.py` replaces the hand-copy with a mechanical, directional, idempotent mirror.

`sync_subset.py` is GENERIC. It contains no knowledge of any particular corpus, project, or folder name. It takes a source digested tree, a destination, and a selection list:

```
python sync_subset.py SOURCE DEST --list SELECTION.txt
```

It mirrors each listed immediate-subfolder of SOURCE into DEST: copies new and changed files, removes destination files that are no longer in the source (so the copy stays a true mirror, not an ever-growing union), reports selection entries not found and destination folders no longer selected, and removes the latter only with `--prune`. It is idempotent: same inputs, same result, safe to re-run any number of times. `--dry-run` shows what would happen without writing.

IMPORTANT: within a selected folder, destination-only files are deleted so the mirror stays exact. Do NOT point this at a destination holding hand-edited files you care about; the destination is by design a projection of the source, not a place for independent edits.

All site-specific knowledge lives in DATA, never in the engine:

- The selection list (one folder name per line; # comments and blank lines ignored) is corpus configuration. It lives WITH THE CORPUS, not in this tooling folder -- the same way project_names.tsv is data the pipeline reads but does not contain.
- ONE LIST PER SOURCE. The two exports name their project folders differently: Claude's are `project_<short-uuid>__<slug>`, produced from the manifest during conversion, while ChatGPT's are whatever `project_names.tsv` renamed them to. A list shared between both sources would report each source's entries as missing from the other on every run. The wrapper takes `SELLIST_CLAUDE` and `SELLIST_CHATGPT` separately, and skips a source whose list is empty or absent.
- A thin per-corpus wrapper holds the paths and calls the generic engine. See `corpus_wrapper.template.bat` for the worked example.

This generic-engine / site-launcher / site-data split is the same separation the rest of the pipeline already uses, and it means the same engine serves any future subset need (a different topic, a collaborator's folders, an Evernote notebook set) with only a new data list and a new thin launcher -- no code change.

`sync_gdrive_corpus.bat` is the generic launcher. It takes a selection list, one source export tree and one destination, so a corpus drawing on both Claude and ChatGPT calls it twice — which is what the per-corpus wrapper does, mirroring into FromNick\Notes\AI\Claude\Conversations\Exported\ and FromNick\Notes\AI\ChatGPT\Conversations\Exported\ respectively. The "Exported" subfolder distinguishes auto-mirrored files from hand-curated sibling folders (Copied\, Output\).

It auto-discovers the newest dated export folder under the source root by filesystem date (NOT by name -- the export folder names are not zero-padded, so a name sort would be wrong), and echoes the resolved paths at the top of each run so you can confirm it picked the right export. Flags (`--prune`, `--dry-run`, `--verbose`) pass through to sync_subset.py. To add another export source, add another call; nothing in the script changes.

## GOOGLE SHEETS

Google Sheets are not stored as real local files. The Drive desktop sync app creates .gsheet shortcut files that link back to the cloud, not the actual spreadsheet content.

To include Google Sheets in your digested archive:

- **1.** In Drive, multi-select the sheets you want.
- **2.** Right-click -> Download. Drive bundles them as a .zip of .xlsx files.
- **3.** Extract the .zip into your INPUT_DIR (or wherever in the source tree you want them to land).
- **4.** Run the pipeline. They will be processed as .xlsx files.

If you find yourself doing this regularly with a large number of sheets, rclone (see "GOOGLE DRIVE TRANSFER" above) can pull and convert them in one command: the same `--drive-export-formats` mechanism that turns native Google Docs into .docx will turn native Google Sheets into .xlsx (use xlsx instead of, or alongside, docx in the export-formats list). The manual right-click -> Download is still faster if you only do it occasionally; the rclone route pays off once it becomes routine.

## HOW THE OUTPUT IS STRUCTURED

```
Source:                              Output:
```
```
source/                              digested/
  notes/                               notes/
    meeting.docx                         meeting.md
                                         meeting_media/
                                           diagram.png
    journal.md                           journal.md
    scratch.txt                          scratch.md
  sheets/                              sheets/
    tracking.xlsx                        tracking.md
  papers/                              papers/
    2026/                                2026/
      draft.pdf                          draft.md
                                         draft_media/
                                           p0001_img1.png
  exports/                             exports/
    conversations.json                   conversations/
                                           2024-03-15__topic-a.md
                                           2024-03-22__topic-b.md
                                           ...
```

Notes:

- Image and attachment folders sit beside the .md they belong to, named <md-stem>_media/. Markdown image links inside the .md use relative paths so the bundle stays portable when synced or copied.
- ChatGPT exports always expand into a subdirectory named after the JSON's stem, even if there is only one conversation.
- Empty source directories are not created in the output.
- Lock files (~$foo.docx) and dotfiles (.DS_Store) are skipped.

## RE-RUNNING / INCREMENTAL UPDATES

The output directory is NOT wiped between runs by default. Re-running the pipeline overwrites existing converted files in place: an updated source produces an updated output, replacing the old version. The filenames are deterministic, so re-runs do not accumulate duplicates.

What stays behind:

- If a source file is DELETED between runs, its converted output stays in place. The pipeline does not currently track source-side deletions.
- If an image was REMOVED from inside a .docx or .pdf between runs, the old image file may stay in the _media/ folder.
- Old log files from previous runs accumulate in OUTPUT_DIR until you delete them manually.

What gets overwritten cleanly:

- .md files derived from a still-present source.
- Image files inside _media/ folders that still appear in the current source (content-aware: same content is left untouched, different content is replaced).

For a guaranteed-fresh rebuild, pass `--clean`. This deletes the contents of OUTPUT_DIR before processing, ensuring no stale files survive. WARNING: `--clean` removes everything in OUTPUT_DIR, including hand-edited .md files and old log files. Only use it on directories that are 100% pipeline-managed.

When two source files in the same folder would produce the same output name (e.g. notes.docx and notes.pdf both wanting `notes.md`), the second one processed gets a -2 suffix: `notes-2.md` and notes-2_media/. The .md filename and its _media folder name stay paired so cross-references remain valid.

The metadata pass (keywords, indexed_at, the auto-index block in each .md body) is idempotent. Re-running it updates fields in place rather than appending duplicates.

## TROUBLESHOOTING

"Python is not installed or not on PATH" Install Python from python.org and re-tick "Add Python to PATH" during installation. Restart the command prompt after installing.

"pypdf not found. Installing..." then "could not install" You may not have network access, or pip might be blocked. Run manually:    python -m pip install pypdf PDFs will be skipped without pypdf; other formats still work.

A specific file fails with an error Open the log file in OUTPUT_DIR (named `_pipeline_YYYYMMDD_HHMMSS.log`) and search for "[error]" to see which files failed and the exception message for each. For deeper debugging, re-run with `--debug` to get full Python tracebacks alongside the error messages. Common causes:

- Encrypted PDF that needs a real password (the pipeline tries empty-password decryption only)
- Corrupted .docx or .xlsx (try opening in Word/Excel and re-saving to recover)
- .json files that aren't actually ChatGPT exports
- Files in use by another program (close Word/Excel and retry)

PDF text comes out garbled or in the wrong order PDF is a layout format, not a content format. Multi-column or heavily-styled PDFs can have imperfect reading order. The text is still all there, just possibly out of sequence within a page.

A scanned PDF produces an empty .md Frontmatter will say "likely_scanned: true". To recover the text, run the source PDF through OCR first: pip install ocrmypdf ocrmypdf input.pdf input.ocr.pdf Then re-run the pipeline on the OCR'd version.

The console window closes too fast to read the summary This shouldn't happen with the .bat (it has `pause` at the end). If it does, run the .bat from an already-open command prompt.

## RUNNING INDIVIDUAL CONVERTERS

Each converter can also run on its own without the orchestrator, useful for one-off conversions or scripting:

```
python docx_to_markdown.py    SOURCE [-o DEST] [-r]
python xlsx_to_markdown.py    SOURCE [-o DEST] [-r]
python pdf_to_markdown.py     SOURCE [-o DEST] [-r]
python chatgpt_to_markdown.py FILE   [-o DEST] [--limit N]
python add_metadata.py        DIR    [-r] [-k N] [--no-index]
```

The -r flag (recursive) is supported by docx, xlsx, and pdf. Standalone runs do NOT mirror folder structure; everything lands flat in the destination. Use `process_folder.py` for structure preservation.

## EXTENDING IT LATER

Adding a new source format Write a new <ext>`_to_markdown.py` that exposes:

- convert_<ext>(in_path, [out_dir, basename]) -> (fm_dict, body_str)
- to_yaml_frontmatter(d) -> str Then add a new branch in process_folder.py's process_file() function that dispatches files with the new extension.

Smarter keyword extraction `add_metadata.py` uses a stopword-filtered frequency count. Replace top_keywords() with a TF-IDF or RAKE / YAKE implementation if you want better results across a corpus. The interface is one function and a stopword set.

Detecting deletions / pruning stale outputs The pipeline does not currently track deletions in the source tree. A future addition could compare the set of expected output files (computed from the current source walk) against what's actually in OUTPUT_DIR and remove anything orphaned.

Versioning with Git The output tree is plain text plus binary media. Initialize a Git repo in OUTPUT_DIR and commit after each run to track changes over time. GitHub's full-text search is another way to query the digested archive.

## PRINCIPLES

This pipeline is designed around a few rules:

- **1.** No information loss. Every kind of source content is rendered, extracted, or anchored. Things the renderer cannot represent visually (images, attachments) are extracted as files. Things it cannot render in flow (footnotes, comments) are anchored in place and expanded in appendices. Nothing is silently dropped. Where extraction has known limits (PDF reading order, scanned PDFs without OCR), the limit is documented and surfaced in frontmatter.

- **2.** Mechanical, not interpretive. The converters do format translation, not summarization. "Digested" means converted to a common format for retrieval, not abstracted or compressed.

- **3.** Stable output. Re-running on the same input produces the same output. Filenames are deterministic. The metadata pass is idempotent. Hand-edited frontmatter fields are preserved across runs.

- **4.** Stdlib by default. docx, xlsx, and chatgpt converters need no dependencies. PDF needs pypdf because PDF parsing genuinely does. Auto-installed by the .bat on first run.

- **5.** Project-agnostic by design. The pipeline knows file formats and conversion; project-specific architecture (corpus tier models, retrieval rules, canon promotion criteria) lives in project documents, not here.
