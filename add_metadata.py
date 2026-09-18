#!/usr/bin/env python3
"""
add_metadata.py

Walk a directory of Markdown files and ensure each one carries useful
metadata for search and retrieval — both in YAML frontmatter (which Claude
sees first when reading the file) and in an auto-generated index block in
the body (which Drive's full-text search indexes).

Non-destructive by design
-------------------------
* If a file has no frontmatter, one is added.
* If frontmatter exists, only computed fields (`word_count`, `keywords`,
  `indexed_at`) are overwritten. Any hand-authored fields are preserved.
* The auto-index block is delimited by HTML comment markers so re-running
  the script updates it in place rather than appending duplicates.
* Original prose is never modified.

Keywords use a simple frequency-based extractor (stopword-filtered, length-
filtered, deterministic). It's not as accurate as TF-IDF over a corpus, but
it has zero dependencies and gives stable output — which is what you want
for a digested search layer that re-runs on a schedule.

Usage
-----
    python add_metadata.py path/to/markdown_dir/
    python add_metadata.py path/to/markdown_dir/ --recursive --keywords 15
    python add_metadata.py path/to/markdown_dir/ --no-index   # frontmatter only
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

FRONTMATTER_RE  = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
HEADING_RE      = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
WORD_RE         = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
CODE_FENCE_RE   = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE  = re.compile(r"`[^`]+`")

INDEX_BEGIN     = "<!-- BEGIN AUTO INDEX -->"
INDEX_END       = "<!-- END AUTO INDEX -->"
INDEX_BLOCK_RE  = re.compile(
    re.escape(INDEX_BEGIN) + r".*?" + re.escape(INDEX_END) + r"\n*",
    re.DOTALL,
)

# Patterns that mark non-content stubs in ChatGPT-export-derived Markdown.
# We strip these before keyword extraction so they don't dominate keyword
# counts on voice / multimodal conversations. Output text keeps the stubs
# (they're meaningful: "voice content was here") but the keyword view doesn't.
STUB_STRIP_RES: list[re.Pattern] = [
    re.compile(r"\[real_time_user_audio_video_asset_pointer content omitted\]"),
    re.compile(r"\[audio_asset_pointer content omitted\]"),
    re.compile(r"\[audio_transcription content omitted\]"),
    re.compile(r"\[image_asset_pointer content omitted\]"),
    re.compile(r"\[video_container_asset_pointer content omitted\]"),
    # Generic catch-all for any future "*_asset_pointer content omitted" stub.
    re.compile(r"\[[a-z_]*asset_pointer content omitted\]"),
    # The reasoning-step marker we emit ourselves.
    re.compile(r"\*\[\d+ reasoning steps?\]\*"),
]

# Compact stopword list. Extend as you find noise in your own corpus.
STOPWORDS: set[str] = {
    "the", "and", "for", "that", "with", "this", "from", "have", "has", "had",
    "you", "your", "are", "was", "were", "but", "not", "they", "them", "their",
    "there", "what", "which", "when", "where", "will", "would", "could",
    "should", "its", "into", "than", "then", "about", "just", "like", "over",
    "also", "some", "more", "most", "such", "other", "any", "all", "one",
    "two", "because", "been", "being", "does", "did", "out", "off", "yes",
    "get", "got", "make", "made", "use", "used", "using", "uses", "say",
    "said", "really", "very", "much", "many", "each", "every", "only", "even",
    "still", "while", "upon", "onto", "able", "after", "again", "against",
    "along", "among", "around", "back", "both", "down", "else", "ever",
    "here", "hers", "him", "his", "himself", "however", "may", "might",
    "must", "neither", "never", "nor", "once", "ones", "ours", "ourselves",
    "perhaps", "quite", "rather", "same", "seem", "since", "theirs",
    "themselves", "therefore", "these", "those", "though", "through", "thus",
    "under", "until", "versus", "via", "well", "whether", "whose", "within",
    "without", "yet", "wont", "cant", "dont", "ive", "weve", "theyre",
    "thats", "whats", "lets", "now", "new", "way", "ways", "look", "looks",
    "looking", "going", "want", "need", "think", "know", "see", "seen",
    "give", "given", "right", "good", "best", "better", "first", "last",
    "next", "thing", "things",
    # Structural words from the ChatGPT export render pipeline. These appear
    # in role headings ("## User", "## Assistant"), in voice/image stub
    # strings, and in our reasoning-step marker. Without excluding them they
    # dominate keyword counts on conversation-shaped documents.
    "user", "assistant", "tool", "system",
    "content", "omitted", "pointer", "asset", "real",
    "audio", "video", "image", "transcription", "container",
    "reasoning", "step", "steps",
    # AI-conversation framing language and connective tissue. These appear
    # heavily in AI-generated text but carry no topical meaning. Filtering
    # them out reduces TF-IDF noise for the personal-knowledge-base use case.
    # Hedge words & qualifiers
    "actually", "basically", "essentially", "fundamentally", "generally",
    "specifically", "particularly", "especially", "obviously", "certainly",
    "probably", "possibly", "likely", "definitely", "absolutely", "totally",
    "exactly", "precisely", "clearly", "simply", "merely", "purely",
    # Conversational connectives
    "approach", "approaches", "consider", "considering", "context",
    "perspective", "perspectives", "particular", "specific", "framework",
    "frameworks", "interesting", "important", "notable", "worth", "noting",
    "regarding", "concerning", "case", "cases", "instance", "instances",
    "example", "examples", "sense", "kind", "kinds", "sort", "sorts",
    "type", "types", "level", "levels", "side", "term", "terms",
    # AI assistant phrases broken into stems
    "here", "heres", "lets", "okay", "sure", "yeah", "actually", "indeed",
    "however", "moreover", "furthermore", "additionally", "essentially",
    "though", "although", "regardless", "anyway", "anyhow", "meanwhile",
    "therefore", "hence", "accordingly", "consequently", "ultimately",
    # Discussion verbs (low signal)
    "discuss", "discussing", "discussed", "discussion", "discussions",
    "mentioned", "mentioning", "mention", "noted", "stated", "states",
    "explain", "explains", "explained", "explanation", "describe",
    "describes", "described", "description", "suggest", "suggests",
    "suggested", "suggestion", "indicate", "indicates", "indicated",
    # Generic process/work nouns
    "work", "working", "works", "task", "tasks", "issue", "issues",
    "problem", "problems", "question", "questions", "answer", "answers",
    "point", "points", "part", "parts", "piece", "pieces", "section",
    "sections", "area", "areas", "place", "places", "time", "times",
    "moment", "moments", "period", "periods", "stage", "stages",
    # Demonstratives & general pronouns
    "this", "that", "these", "those", "such", "ones", "another", "others",
    "anything", "something", "nothing", "everything", "everyone", "anyone",
    "someone", "nobody", "everybody", "anybody", "somebody",
    # Generic adjectives
    "different", "similar", "various", "several", "certain", "actual",
    "real", "true", "false", "correct", "wrong", "right", "left", "high",
    "low", "big", "small", "large", "great", "little", "main", "key",
    "major", "minor", "simple", "complex", "easy", "hard", "difficult",
    "common", "rare", "unique", "general", "specific", "broad", "narrow",
    # Conversation-meta words
    "conversation", "conversations", "chat", "chats", "thread", "threads",
    "message", "messages", "response", "responses", "reply", "replies",
}


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def strip_code(text: str) -> str:
    """Remove fenced and inline code, plus non-content stub strings, so none
    of them dominate keyword counts."""
    text = CODE_FENCE_RE.sub(" ", text)
    text = INLINE_CODE_RE.sub(" ", text)
    for pat in STUB_STRIP_RES:
        text = pat.sub(" ", text)
    return text


def word_count(body: str) -> int:
    return len(WORD_RE.findall(strip_code(body)))


def heading_outline(body: str, max_items: int = 25) -> list[str]:
    """Return Markdown-bullet-formatted heading list, indented by depth."""
    items: list[str] = []
    for m in HEADING_RE.finditer(body):
        depth = len(m.group(1))
        text = m.group(2).strip()
        items.append(f"{'  ' * (depth - 1)}- {text}")
        if len(items) >= max_items:
            break
    return items


def keyword_count_for(word_count: int, base: int = 10, ceiling: int = 40) -> int:
    """Scale keyword count with document length.

    Short conversations don't have enough distinct topics to merit many
    keywords; long ones span more concepts and benefit from more coverage.
    The scaling function is conservative on short content and aggressive
    on long content:

        word_count < 500   -> 8 keywords (short, narrow)
        word_count < 2000  -> 12 keywords
        word_count < 5000  -> 18 keywords
        word_count < 15000 -> 25 keywords
        word_count >= 15000 -> 35-40 keywords (long, multi-topic)

    The CLI's --keywords flag still works as an override: pass an explicit
    count and it's used regardless of document length.
    """
    if word_count < 500:
        return 8
    if word_count < 2000:
        return 12
    if word_count < 5000:
        return 18
    if word_count < 15000:
        return 25
    return min(ceiling, base + word_count // 500)


def _tokenize(body: str) -> list[str]:
    """Lowercase tokens with stopwords and short words filtered out.
    Stub strings and code blocks are stripped first via strip_code."""
    cleaned = strip_code(body)
    tokens = (w.lower() for w in WORD_RE.findall(cleaned))
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 4]


def top_keywords(body: str, n: int = 10) -> list[str]:
    """Single-document fallback: rank by raw frequency.

    Used when no corpus-wide context is available. The corpus-aware caller
    in process_file() prefers top_keywords_tfidf which generally produces
    better topic words by penalizing terms that appear in many documents.
    """
    filtered = _tokenize(body)
    if not filtered:
        return []
    counts = Counter(filtered)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:n]]


def top_keywords_tfidf(body: str, doc_freq: dict, total_docs: int,
                       n: int = 10) -> list[str]:
    """Corpus-aware ranking: TF-IDF score with sublinear TF.

    For each candidate term:
        score = (1 + log(tf)) * log((total_docs + 1) / (df + 1))

    `doc_freq` maps term -> number of documents containing it.
    `total_docs` is the corpus size used to build doc_freq.

    The +1 smoothing prevents division-by-zero and handles unseen terms.
    Terms appearing in MANY documents (generic words like "edge", "roll")
    get penalized; terms distinctive to this document are surfaced. Sublinear
    TF dampens the effect of a single keyword being repeated 80 times.
    """
    import math
    filtered = _tokenize(body)
    if not filtered:
        return []
    tf = Counter(filtered)
    scored: list[tuple[float, str]] = []
    for term, count in tf.items():
        df = doc_freq.get(term, 0)
        idf = math.log((total_docs + 1) / (df + 1)) + 1.0
        score = (1.0 + math.log(count)) * idf
        scored.append((score, term))
    # Score desc, then term asc for determinism.
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [term for _, term in scored[:n]]


def build_corpus_doc_freq(md_files: list) -> tuple[dict, int]:
    """Walk every .md file once and return (doc_freq, total_docs).

    For each unique term in a document we increment doc_freq by 1. This is
    the IDF input for top_keywords_tfidf.
    """
    doc_freq: dict[str, int] = {}
    total = 0
    for f in md_files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        # Skip the frontmatter for purposes of corpus statistics.
        _, body = parse_frontmatter(text)
        unique_terms = set(_tokenize(body))
        if not unique_terms:
            continue
        total += 1
        for t in unique_terms:
            doc_freq[t] = doc_freq.get(t, 0) + 1
    return doc_freq, total


# ---------------------------------------------------------------------------
# Frontmatter parse / emit
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (existing_dict, body_without_frontmatter). Minimal YAML subset."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm: dict = {}
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [i.strip().strip('"').strip("'") for i in inner.split(",")]
            val = [i for i in items if i]
        elif val in {"true", "false"}:
            val = (val == "true")
        else:
            # Try numeric coercion so integer/float frontmatter survives a round-trip.
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass  # leave as string
        fm[key] = val
    return fm, body


def emit_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            quoted = ", ".join(f'"{str(i)}"' for i in v)
            lines.append(f"{k}: [{quoted}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            s = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}: "{s}"')
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Auto-index block in body
# ---------------------------------------------------------------------------

def build_index_block(keywords: list[str], outline: list[str]) -> str:
    lines = [INDEX_BEGIN, "## Document index", ""]
    if keywords:
        lines.append(f"**Keywords:** {', '.join(keywords)}")
        lines.append("")
    if outline:
        lines.append("**Outline:**")
        lines.append("")
        lines.extend(outline)
        lines.append("")
    lines.append(INDEX_END)
    return "\n".join(lines)


def update_body_with_index(body: str, index_block: str) -> str:
    """Replace existing AUTO INDEX block, or insert it after the first H1."""
    if INDEX_BEGIN in body:
        return INDEX_BLOCK_RE.sub(index_block + "\n\n", body, count=1)
    h1 = re.search(r"^#\s+.+?\n", body, re.MULTILINE)
    if h1:
        return body[: h1.end()] + "\n" + index_block + "\n\n" + body[h1.end():]
    return index_block + "\n\n" + body


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(path: Path, n_keywords: int | None, write_index: bool,
                 doc_freq: dict | None = None,
                 total_docs: int = 0) -> bool:
    """Update the file in place. Return True if anything changed.

    When `doc_freq` and `total_docs` are provided (the corpus-aware mode used
    by the orchestrator and by main() once it has scanned the corpus),
    keywords are ranked by TF-IDF — distinctive terms surface, generic terms
    are penalized. Without corpus stats, falls back to raw frequency.

    `n_keywords` of None means "scale by document length" -- the typical mode
    when called from the orchestrator. An explicit integer overrides scaling.
    """
    text = path.read_text(encoding="utf-8")
    existing, body = parse_frontmatter(text)

    # Compute body word count once. Used both for the frontmatter field and
    # for deciding how many keywords to extract.
    wc = word_count(body)
    actual_n = n_keywords if n_keywords is not None else keyword_count_for(wc)

    if doc_freq is not None and total_docs > 0:
        kw = top_keywords_tfidf(body, doc_freq, total_docs, n=actual_n)
    else:
        kw = top_keywords(body, n=actual_n)
    # Sort alphabetically for stable diffs across re-runs and easier
    # visual scanning. The ranking is preserved by score during extraction;
    # alphabetical output is only the storage order.
    kw = sorted(kw)
    outline = heading_outline(body)

    # Backfill missing fields without overwriting human-authored ones.
    if "modified" not in existing:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        existing["modified"] = mtime.isoformat(timespec="seconds")
    if "title" not in existing:
        m = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
        existing["title"] = m.group(1) if m else path.stem.replace("_", " ").replace("-", " ")

    # Always-overwrite computed fields.
    existing["word_count"] = wc
    existing["keywords"] = kw
    existing["indexed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if write_index:
        body = update_body_with_index(body, build_index_block(kw, outline))

    new_text = emit_frontmatter(existing) + "\n\n" + body.lstrip("\n")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Add/refresh search metadata in Markdown files."
    )
    ap.add_argument("path", help="Directory containing .md files (or a single .md file)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Recurse into subdirectories")
    ap.add_argument("-k", "--keywords", type=int, default=None,
                    help="Override keyword count per file. Default: scale "
                         "by document length (8 for short, up to 40 for "
                         "very long).")
    ap.add_argument("--no-index", action="store_true",
                    help="Skip the in-body auto-index block; only update frontmatter")
    args = ap.parse_args()

    root = Path(args.path)
    if root.is_file():
        files = [root] if root.suffix.lower() == ".md" else []
    else:
        pattern = "**/*.md" if args.recursive else "*.md"
        files = sorted(root.glob(pattern))

    if not files:
        print(f"No markdown files found under {root}")
        return 1

    # First pass: build corpus document-frequency stats so keyword extraction
    # can use TF-IDF rather than raw frequency. Only worth the extra read for
    # corpora of more than a handful of files.
    doc_freq: dict | None = None
    total_docs = 0
    if len(files) >= 5:
        print(f"Scanning {len(files)} files to build corpus stats for TF-IDF...")
        doc_freq, total_docs = build_corpus_doc_freq(files)
        print(f"  vocabulary: {len(doc_freq)} unique terms across {total_docs} files")

    changed = 0
    for f in files:
        if process_file(f, n_keywords=args.keywords,
                        write_index=not args.no_index,
                        doc_freq=doc_freq, total_docs=total_docs):
            changed += 1

    print(f"Processed {len(files)} file(s); updated {changed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
