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
import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

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


# ---------------------------------------------------------------------------
# Provenance structure classification  (digester handoff v6.8, Decision 6)
# ---------------------------------------------------------------------------
#
# Documents reach the corpus in four shapes and only two can be tiered.
# Classification is by POSITIVE DETECTION ONLY: a file is turn-structured or
# speaker-labelled because a pattern matched, never because another pattern
# failed. Anything unmatched is `unknown`, which is not an error -- it means
# the file keeps unweighted keyword extraction and gets reported.
#
# Turns are never inferred from voice, topic shift, or style. A misattributed
# turn would put assistant prose at tier 0, wearing the owner's authority.

# Speaker-turn headings written by the export converters. Claude writes
# "## Human" / "## Assistant"; ChatGPT writes "## User" / "## Assistant" /
# "## System" / "## Tool", optionally with a parenthesised role qualifier.
TURN_HEADING_RE = re.compile(
    r"^##[ \t]+(Human|User|Assistant|System|Tool)\b[^\n]*$", re.MULTILINE
)

# Inline speaker labels: "**Nick:**" opening a line. Speaker names are an open
# set -- Nick, Matt, Claude, ChatGPT and others -- so we match the label SHAPE
# and treat the names found as data.
SPEAKER_LABEL_RE = re.compile(
    r"^[ \t]{0,3}\*\*([A-Z][A-Za-z0-9 .'\u2019-]{0,39}):\*\*", re.MULTILINE
)

BLOCKQUOTE_RE = re.compile(r"^[ \t]{0,3}>")

# Heading roles that speak for the subject, and roles that do not.
SUBJECT_ROLES = {"Human", "User"}
ASSISTANT_ROLES = {"Assistant", "System", "Tool"}

# Labels that name an AI rather than a person. Used ONLY to work out which
# labelled speaker is the subject -- never to classify a document.
AI_SPEAKER_NAMES = {
    "claude", "chatgpt", "gpt", "ai", "assistant", "bot", "copilot",
    "gemini", "bard", "llama", "model", "system", "tool",
}

# A frontmatter `source` naming an AI export. A document with no conversational
# markers is `single-voice` only when its source is NOT an AI.
AI_SOURCE_RE = re.compile(r"chatgpt|claude|gpt|openai|anthropic", re.I)

STRUCT_TURN      = "turn-structured"
STRUCT_LABELLED  = "speaker-labelled"
STRUCT_SINGLE    = "single-voice"
STRUCT_UNKNOWN   = "unknown"


def classifiable_text(body: str) -> str:
    """Body with the auto-index block and fenced code removed.

    The auto-index block emits `**Keywords:**` and `**Outline:**`, which match
    the speaker-label shape. Stripping it first keeps our own output from being
    mistaken for a speaker.
    """
    text = INDEX_BLOCK_RE.sub(" ", body)
    return CODE_FENCE_RE.sub(" ", text)


def find_turn_headings(text: str) -> list[tuple[int, int, str]]:
    """Return (heading_start, content_start, role) for each turn heading."""
    return [(m.start(), m.end(), m.group(1))
            for m in TURN_HEADING_RE.finditer(text)]


def find_speaker_labels(text: str) -> list[tuple[int, int, str]]:
    """Return (label_start, content_start, name) for each inline speaker label."""
    return [(m.start(), m.end(), m.group(1).strip())
            for m in SPEAKER_LABEL_RE.finditer(text)]


def classify_provenance_structure(body: str, fm: dict) -> tuple[str, list[str]]:
    """Classify a document's provenance structure. Returns (value, speakers).

    turn-structured  -- converted AI export: role headings for both sides
    speaker-labelled -- inline `**Name:**` labels, at least two recurring
    single-voice     -- no conversational markers and a non-AI source
    unknown          -- everything else
    """
    text = classifiable_text(body)

    roles = {role for _, _, role in find_turn_headings(text)}
    if (roles & SUBJECT_ROLES) and (roles & ASSISTANT_ROLES):
        return STRUCT_TURN, sorted(roles)

    # Require at least two distinct labels EACH occurring at least twice. A
    # real exchange alternates; a one-off bold lead-in such as "**Note:**"
    # does not. This is a structural test rather than a blocklist of words.
    seen: dict[str, int] = {}
    for _, _, name in find_speaker_labels(text):
        seen[name] = seen.get(name, 0) + 1
    recurring = sorted(n for n, c in seen.items() if c >= 2)
    if len(recurring) >= 2:
        return STRUCT_LABELLED, recurring

    source = str(fm.get("source", "") or "").strip()
    if source and not AI_SOURCE_RE.search(source):
        return STRUCT_SINGLE, []

    return STRUCT_UNKNOWN, []


# ---------------------------------------------------------------------------
# Provenance weighting  (digester handoff v6.8, Decision 1)
# ---------------------------------------------------------------------------
#
# Each term is weighted by the acceptance tier of the assertion carrying it.
# Tier definitions live in the write-report skill's acceptance-rubric.md.
#
# Only the structurally detectable tiers are assigned here -- 0, 5, 6 and 7.
# Tiers 1-4 require one semantic judgment (endorsement versus objection after
# a reference) and are DEFERRED, as the handoff permits. A deferred tier is
# never guessed; the term simply falls to whichever structural tier applies.

TIER_WEIGHTS: dict[int, int] = {0: 128, 1: 64, 2: 32, 3: 16,
                                4: 8, 5: 4, 6: 2, 7: 1}

# Where a term was found. Used to resolve its tier.
_SUBJECT_PLAIN = "subject_plain"    # non-quoted text in a subject turn
_SUBJECT_QUOTE = "subject_quote"    # blockquoted text inside a subject turn
_ASSISTANT     = "assistant"        # any non-subject turn
_NEUTRAL       = "neutral"          # text before the first turn marker


def _split_quoted(segment: str) -> tuple[str, str]:
    """Split a subject turn into (non-quoted, quoted) text.

    Blockquoted text in a subject turn is quoted material, not the subject's
    own assertion -- quoting an assertion does not transfer it. The quote is
    kept and tiered separately rather than discarded.
    """
    plain: list[str] = []
    quoted: list[str] = []
    for line in segment.splitlines():
        (quoted if BLOCKQUOTE_RE.match(line) else plain).append(line)
    return "\n".join(plain), "\n".join(quoted)


def _turn_spans(text: str, structure: str,
                subject_names: set[str] | None) -> list[tuple[str, str]] | None:
    """Split a document into (kind, text) spans in document order.

    Returns None when the spans cannot be attributed safely -- for a
    speaker-labelled document whose subject cannot be identified.
    """
    spans: list[tuple[str, str]] = []

    if structure == STRUCT_TURN:
        marks = find_turn_headings(text)
        if not marks:
            return None
        if marks[0][0] > 0:
            spans.append((_NEUTRAL, text[:marks[0][0]]))
        for i, (_, content_start, role) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            kind = _SUBJECT_PLAIN if role in SUBJECT_ROLES else _ASSISTANT
            spans.append((kind, text[content_start:end]))

    elif structure == STRUCT_LABELLED:
        marks = find_speaker_labels(text)
        if not marks:
            return None
        names = {name for _, _, name in marks}
        if subject_names:
            subjects = {n for n in names if n.lower() in subject_names}
        else:
            # Exactly one non-AI speaker resolves the subject on its own.
            # Two or more human names (Nick and Matt, say) is ambiguous, and
            # guessing would put the wrong person's words at tier 0.
            human = {n for n in names if n.lower() not in AI_SPEAKER_NAMES}
            subjects = human if len(human) == 1 else set()
        if not subjects:
            return None
        if marks[0][0] > 0:
            spans.append((_NEUTRAL, text[:marks[0][0]]))
        for i, (_, content_start, name) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            # Unlabelled prose continues the last labelled speaker, so the
            # span simply runs to the next label.
            kind = _SUBJECT_PLAIN if name in subjects else _ASSISTANT
            spans.append((kind, text[content_start:end]))

    else:
        return None

    # Separate blockquotes out of subject spans.
    resolved: list[tuple[str, str]] = []
    for kind, seg in spans:
        if kind == _SUBJECT_PLAIN:
            plain, quoted = _split_quoted(seg)
            if plain.strip():
                resolved.append((_SUBJECT_PLAIN, plain))
            if quoted.strip():
                resolved.append((_SUBJECT_QUOTE, quoted))
        else:
            resolved.append((kind, seg))
    return resolved


def _tier_for(kinds: set[str], first_kind: str) -> int:
    """Resolve a term's acceptance tier from where it appears.

    tier 0 -- the subject's own words, unquoted
    tier 5 -- first used by the assistant, taken up by the subject unquoted
    tier 6 -- reaches the subject only inside a quotation
    tier 7 -- never leaves the assistant's turns
    """
    if _SUBJECT_PLAIN in kinds:
        if _ASSISTANT in kinds and first_kind == _ASSISTANT:
            return 5
        return 0
    if _SUBJECT_QUOTE in kinds:
        return 6
    return 7


def provenance_weighted_counts(
    body: str, structure: str,
    subject_names: set[str] | None = None,
) -> tuple[dict[str, float] | None, str]:
    """Term counts scaled by the acceptance tier of the assertion carrying them.

    Returns (counts, reason). `counts` is None when the document cannot be
    weighted, and `reason` says why. Nothing is discarded: every term that
    survives tokenisation keeps at least weight 1.
    """
    if structure not in (STRUCT_TURN, STRUCT_LABELLED):
        return None, f"structure is {structure}"

    text = classifiable_text(body)
    spans = _turn_spans(text, structure, subject_names)
    if spans is None:
        return None, "subject could not be identified from the speaker labels"

    counts: Counter = Counter()
    kinds: dict[str, set[str]] = {}
    first_kind: dict[str, str] = {}

    for kind, segment in spans:
        for term in _tokenize(segment):
            counts[term] += 1
            kinds.setdefault(term, set()).add(kind)
            first_kind.setdefault(term, kind)

    if not counts:
        return None, "no tokens survived filtering"

    weighted: dict[str, float] = {}
    for term, count in counts.items():
        tier = _tier_for(kinds[term], first_kind[term])
        weighted[term] = count * TIER_WEIGHTS[tier]
    return weighted, f"weighted over {len(spans)} spans"


def _tokenize(body: str) -> list[str]:
    """Lowercase tokens with stopwords and short words filtered out.
    Stub strings and code blocks are stripped first via strip_code."""
    cleaned = strip_code(body)
    tokens = (w.lower() for w in WORD_RE.findall(cleaned))
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 4]


def top_keywords(body: str, n: int = 10,
                 tf_counts: dict | None = None) -> list[str]:
    """Single-document fallback: rank by frequency.

    Used when no corpus-wide context is available. The corpus-aware caller
    in process_file() prefers top_keywords_tfidf which generally produces
    better topic words by penalizing terms that appear in many documents.

    `tf_counts`, when given, replaces the raw frequency count with
    provenance-weighted counts from provenance_weighted_counts().
    """
    if tf_counts is not None:
        counts = tf_counts
    else:
        filtered = _tokenize(body)
        if not filtered:
            return []
        counts = Counter(filtered)
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:n]]


def top_keywords_tfidf(body: str, doc_freq: dict, total_docs: int,
                       n: int = 10, tf_counts: dict | None = None) -> list[str]:
    """Corpus-aware ranking: TF-IDF score with sublinear TF.

    For each candidate term:
        score = (1 + log(tf)) * log((total_docs + 1) / (df + 1))

    `doc_freq` maps term -> number of documents containing it.
    `total_docs` is the corpus size used to build doc_freq.

    The +1 smoothing prevents division-by-zero and handles unseen terms.
    Terms appearing in MANY documents (generic words like "edge", "roll")
    get penalized; terms distinctive to this document are surfaced. Sublinear
    TF dampens the effect of a single keyword being repeated 80 times.
    When `tf_counts` is supplied, it replaces the raw term frequency with
    provenance-weighted counts -- each term's count scaled by the acceptance
    tier of the assertion carrying it. IDF is unchanged: document frequency
    is a property of the corpus, not of who spoke. Because TF is sublinear,
    a 128x weight becomes a +log(128) = +4.85 bonus rather than a 128x one,
    which is what keeps the tier ladder from swamping the ranking.
    """
    import math
    if tf_counts is not None:
        tf = tf_counts
    else:
        filtered = _tokenize(body)
        if not filtered:
            return []
        tf = Counter(filtered)
    if not tf:
        return []
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

# ---------------------------------------------------------------------------
# Extraction artifacts  (digester handoff v6.8, Decision 8)
# ---------------------------------------------------------------------------
#
# Keyword lists carry strings such as `erlyjewxq`, `jauuimuv-wmcjrfg`, `kxwoj`
# and `lz-pirirgptx`. They are conversion debris, not words, and the existing
# filters miss them: a token need only start with a letter and reach four
# characters.
#
# Rejection is deliberately conservative. A missed artifact is a minor cost; a
# wrongly rejected real term is worse, because it removes a word the corpus is
# actually about. So the tests are arranged in two tiers:
#
#   HARD    -- shapes no English word takes. Always applied.
#   SOFT    -- statistical suspicion, which real words do sometimes trigger.
#              "strengths" has a one-in-nine vowel ratio. These only reject
#              when a dictionary is available to veto, or when the term appears
#              in a single document and never capitalised.
#
# The dictionary's job is mostly to PREVENT rejections, not to cause them.

VOWELS = set("aeiouy")

# For "has no vowel at all", `w` counts. Welsh writes it as one -- crwth, cwm --
# and this corpus is full of Celtic vocabulary.
VOWELS_LOOSE = set("aeiouyw")

# Letter pairs that effectively do not occur inside English words. This is the
# test that actually separates debris from vocabulary: `kxwoj` and `clock` have
# the same vowel ratio, so counting vowels cannot tell them apart, but `kx`
# never occurs and `cl` is everywhere.
#
# Deliberately short and certain. Pairs that look odd but are real are absent:
# `nx` (sphinx, lynx), `tz` (waltz, blitz), `hw` (schwa), `gt` (strengths),
# `hs` (twelfths), `mn` (autumn), `pt` (crypts).
IMPOSSIBLE_BIGRAMS = frozenset("""
bq bx bz cj cv cx cz dx fq fv fx fz gq gv gx gz hx hz
jb jc jd jf jg jh jk jl jm jn jq jr js jt jv jw jx jz
kq kx kz lq lx lz mx mz pq pv px pz
qb qc qd qf qg qh qj qk ql qm qn qp qq qr qs qt qv qw qx qy qz
sx tq tx vb vc vd vf vg vh vj vk vl vm vn vp vq vr vs vt vw vx vz
wq wv wx wz xj xk xq xr xz yq zj zq zr zx
""".split())

# A term seen in at least this many documents is real, whatever it looks like.
# Debris is random, so it does not recur across independently converted files.
ARTIFACT_DF_FLOOR = 3

CONSONANT_RUN_HARD = 7   # no English word reaches this
CONSONANT_RUN_SOFT = 6   # "strengths" and "twelfths" reach 5, so 5 is unsafe


def _longest_consonant_run(term: str) -> int:
    longest = run = 0
    for ch in term:
        if ch.isalpha() and ch not in VOWELS:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest


def hard_artifact_reason(term: str) -> str:
    """Why this is a shape no English word takes, or "" if it is not.

    A reason rather than a boolean, so the audit report can say what fired.
    A filter nobody can inspect is a filter nobody should trust.
    """
    letters = [c for c in term if c.isalpha()]
    if not letters:
        return "no letters"
    if any(c.isdigit() for c in term) and any(c.isalpha() for c in term):
        return "letters mixed with digits"
    if len(letters) >= 4 and not any(c in VOWELS_LOOSE for c in letters):
        return "no vowel (counting w)"
    for i, c in enumerate(term):
        if c == "q" and (i + 1 >= len(term) or term[i + 1] != "u"):
            return "q not followed by u"
    for i in range(len(term) - 2):
        if term[i] == term[i + 1] == term[i + 2] and term[i].isalpha():
            return f"{term[i]!r} three times running"
    run = _longest_consonant_run(term)
    if run >= CONSONANT_RUN_HARD:
        return f"{run}-consonant run"
    return ""


def is_hard_artifact(term: str) -> bool:
    """Shapes no English word takes. Safe to reject with no other evidence."""
    return bool(hard_artifact_reason(term))


def soft_artifact_reason(term: str) -> str:
    """Why this looks implausible, or "" if it does not."""
    letters = "".join(c for c in term if c.isalpha())
    if len(letters) < 4:
        return ""
    for i in range(len(letters) - 1):
        pair = letters[i:i + 2]
        if pair in IMPOSSIBLE_BIGRAMS:
            return f"implausible letter pair {pair!r}"
    run = _longest_consonant_run(term)
    if run >= CONSONANT_RUN_SOFT:
        return f"{run}-consonant run"
    return ""


def is_soft_artifact(term: str) -> bool:
    """Implausible letter sequences, vetoable by other evidence.

    Kept soft rather than hard because a loanword or an unusual name could in
    principle contain one of these pairs, and losing a real term costs more
    than keeping an artifact.
    """
    return bool(soft_artifact_reason(term))


def load_dictionary(path) -> set[str]:
    """Load a plain word list: one word per line. Empty set if unreadable."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {line.strip().lower() for line in text.splitlines() if line.strip()}


# Lexicon files. A `.txt` is one term per line; a `.tsv` takes the term from
# the first column and ignores the rest, so metadata columns (source, kind,
# note) can be carried without the loader needing to understand them.
LEXICON_SUFFIXES = (".txt", ".tsv", ".lst")


def load_lexicon_dir(directory) -> tuple[set[str], list[str]]:
    """Merge every word list in a directory. Returns (terms, files_read).

    Two kinds of file belong here and are treated identically:

      * language lexicons -- general vocabulary, shipped with the pipeline
      * project glossaries -- a corpus's own invented terms and names, kept
        beside its wrapper

    The second kind is the one that matters most. `Erlking`, `Cernunnos`,
    `crwth` and `Brigit` are exactly the terms most at risk from any filter and
    least likely to appear in a general word list. Merging both into one set
    means the filter cannot tell them apart, which is the point: both are real
    words as far as this corpus is concerned.
    """
    directory = Path(directory)
    terms: set[str] = set()
    read: list[str] = []
    if not directory.is_dir():
        return terms, read
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in LEXICON_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        before = len(terms)
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # First column only; anything after a tab is metadata.
            term = line.split("\t", 1)[0].strip().lower()
            if term:
                terms.add(term)
        read.append(f"{path.name} (+{len(terms) - before:,})")
    return terms, read


def load_lexicons(dirs, dictionary_file=None) -> tuple[set[str], list[str]]:
    """Merge every lexicon directory, plus one optional standalone word list."""
    terms: set[str] = set()
    read: list[str] = []
    for d in dirs or []:
        found, files = load_lexicon_dir(d)
        terms |= found
        read.extend(files)
    if dictionary_file:
        found = load_dictionary(dictionary_file)
        if found:
            terms |= found
            read.append(f"{Path(dictionary_file).name} (+{len(found):,})")
    return terms, read


def write_artifact_report(path, entries: list, root=None) -> None:
    """Write every rejected keyword, with the test that rejected it.

    The report exists so the filter can be judged against real data rather than
    against the fixtures it was built with. Terms are grouped so a term dropped
    across many documents reads as one decision, not as many.
    """
    from collections import defaultdict
    grouped: dict[tuple[str, str, str], list] = defaultdict(list)
    for term, tier, reason, src in entries:
        grouped[(term.lower(), tier, reason)].append(src)

    hard = sorted(k for k in grouped if k[1] == "hard")
    soft = sorted(k for k in grouped if k[1] == "soft")

    lines = ["# Rejected keywords", "",
             f"{len(grouped):,} distinct term(s) rejected across "
             f"{len({e[3] for e in entries}):,} file(s).", "",
             "Every term below was dropped from a keyword list. Read it as a",
             "proposal, not a result: anything here that is a real word is a",
             "false positive, and the test that caught it should be tightened",
             "or removed.", ""]

    def section(title: str, keys: list, note: str) -> None:
        lines.append(f"## {title} ({len(keys):,})")
        lines.append("")
        lines.append(note)
        lines.append("")
        if not keys:
            lines.append("None.")
            lines.append("")
            return
        lines.append("| Term | Why | Files |")
        lines.append("|---|---|---|")
        for key in keys:
            term, _tier, reason = key
            srcs = grouped[key]
            shown = srcs[0]
            try:
                shown = Path(shown).relative_to(root) if root else Path(shown).name
            except (ValueError, TypeError):
                shown = Path(str(shown)).name
            extra = f" +{len(srcs) - 1} more" if len(srcs) > 1 else ""
            lines.append(f"| `{term}` | {reason} | {shown}{extra} |")
        lines.append("")

    section("Hard rejections", hard,
            "Shapes no English word takes. These should all be debris. A real "
            "word here is a bug in the hard tests.")
    section("Soft rejections", soft,
            "Implausible letter sequences, rejected because no dictionary, "
            "capitalisation or corpus frequency vetoed them. **This is the "
            "tier to judge.** If real words appear here, supply a lexicon or "
            "drop the soft tier.")

    try:
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"  [warn] could not write artifact report: {e}")


def find_system_dictionary() -> Path | None:
    """A word list in one of the usual places, if there is one."""
    for candidate in ("/usr/share/dict/words", "/usr/dict/words",
                      "/usr/share/dict/american-english"):
        path = Path(candidate)
        if path.is_file():
            return path
    local = SCRIPT_DIR / "words.txt"
    return local if local.is_file() else None


# Characters that can precede a capital without the capital meaning anything:
# sentence terminators, list and heading markers, table cells, quote marks.
_SENTENCE_START_BEFORE = set(".!?:;\n\r#-*>|\"\u201c\u2018([")


def capitalized_terms(body: str) -> set[str]:
    """Lowercased forms of words that appear capitalised MID-SENTENCE.

    A capitalised term is probably a name -- Loom, Cernunnos, Brigit -- and the
    corpus is full of them. They will not be in any general word list, so they
    must never be rejected for being absent from one.

    Sentence-initial capitals are excluded, because every sentence has one and
    they say nothing about the word. Counting them made `the` look like a
    proper noun and protected a piece of conversion debris that happened to
    open a sentence.
    """
    out: set[str] = set()
    for match in WORD_RE.finditer(body):
        word = match.group(0)
        if not word[:1].isupper():
            continue
        # Walk back over whitespace to the previous meaningful character.
        i = match.start() - 1
        while i >= 0 and body[i] in " \t":
            i -= 1
        if i < 0 or body[i] in _SENTENCE_START_BEFORE:
            continue          # sentence-initial: carries no information
        out.add(word.lower())
    return out


def reject_artifacts(terms, body: str = "", dictionary: set[str] | None = None,
                     doc_freq: dict | None = None
                     ) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Split candidate keywords into (kept, rejected).

    Each rejection carries (term, tier, reason) so the audit report can show
    exactly why a term was dropped and which test did it.
    """
    names = capitalized_terms(body) if body else set()
    kept: list[str] = []
    rejected: list[tuple[str, str, str]] = []
    for term in terms:
        base = term.lower()

        hard = hard_artifact_reason(base)
        if hard:
            rejected.append((term, "hard", hard))
            continue

        soft = soft_artifact_reason(base)
        if not soft:
            kept.append(term)
            continue

        # Soft suspicion. Any of these vetoes the rejection.
        if dictionary and (base in dictionary
                           or base.replace("-", "") in dictionary):
            kept.append(term)
            continue
        if base in names:
            kept.append(term)
            continue
        if doc_freq and doc_freq.get(base, 0) >= ARTIFACT_DF_FLOOR:
            kept.append(term)
            continue
        rejected.append((term, "soft", soft))
    return kept, rejected


# ---------------------------------------------------------------------------
# Document date
# ---------------------------------------------------------------------------
#
# `date` carries the DOCUMENT's own local timestamp with offset, matching its
# filename: 2026-09-15T17:47-07:00. It is not `modified` (when the file was
# last touched on disk) and not `indexed_at` (when we last ran). Three sources
# are tried in order, best first, and the one used is recorded in `date_source`
# so a reader can tell a real document date from a filesystem fallback.

# Fields a converter may already have filled from the source itself.
DATE_SOURCE_FIELDS = ("created", "create_time", "created_at", "date")

# The corpus filename convention: YYYY-MM-DD-HHMM__slug. The timestamp is
# local time in the corpus owner's zone, so it is read as naive local.
FILENAME_TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})__")

# PDF dates look like D:20260917095500-07'00', with an optional trailing
# offset that must be honoured rather than dropped -- a PDF written in another
# zone would otherwise land hours out.
PDF_DATE_RE = re.compile(
    r"^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?"
    r"(?:(Z)|([+-])(\d{2})'?(\d{2})?)?")


def _as_local_iso(dt: datetime) -> str:
    """Format a datetime as local time with offset, to the minute."""
    if dt.tzinfo is None:
        dt = dt.astimezone()          # naive is local by definition
    else:
        dt = dt.astimezone()          # convert to the local zone
    return dt.isoformat(timespec="minutes")


def parse_any_date(value) -> datetime | None:
    """Parse the date formats the converters actually produce. None if unusable."""
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    m = PDF_DATE_RE.match(text)
    if m:
        y, mo, d, hh, mi, ss, zulu, sign, off_h, off_m = m.groups()
        tz = None
        if zulu:
            tz = timezone.utc
        elif sign:
            delta = timedelta(hours=int(off_h), minutes=int(off_m or 0))
            tz = timezone(-delta if sign == "-" else delta)
        try:
            return datetime(int(y), int(mo), int(d),
                            int(hh or 0), int(mi or 0), int(ss or 0), tzinfo=tz)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def resolve_date(fm: dict, path: Path) -> tuple[str, str]:
    """Return (iso_date, which_source). Empty date only if the file is unreadable.

    1. A date the converter already knows, from the source document itself.
    2. The timestamp in the filename, where the name follows the convention.
    3. The file's modification time.
    """
    for field in DATE_SOURCE_FIELDS:
        if field not in fm:
            continue
        dt = parse_any_date(fm.get(field))
        if dt is not None:
            return _as_local_iso(dt), f"document ({field})"

    m = FILENAME_TS_RE.match(path.name)
    if m:
        y, mo, d, hh, mi = (int(g) for g in m.groups())
        try:
            return _as_local_iso(datetime(y, mo, d, hh, mi)), "filename"
        except ValueError:
            pass

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return "", "unavailable"
    return _as_local_iso(mtime), "file mtime"


# Identity of a converted file's source, recorded at digestion time.
#
# Matching a digested file to its source by FILENAME breaks the moment the
# source is renamed: the digested output then looks orphaned, when in fact
# nothing was lost. Recording the source's size and content hash lets a rename
# be reported as a rename. Size is stored alongside the hash so a search can
# filter on it first and hash only the few candidates that could match, rather
# than hashing a whole raw tree.

SOURCE_HASH_FIELD = "source_sha256"
SOURCE_SIZE_FIELD = "source_bytes"


def file_sha256(path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed. Empty string if unreadable."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
    except OSError:
        return ""
    return h.hexdigest()


def stamp_source_identity(fm: dict, src) -> dict:
    """Record `source_bytes` and `source_sha256` for a converted file."""
    try:
        fm[SOURCE_SIZE_FIELD] = src.stat().st_size
    except OSError:
        pass
    digest = file_sha256(src)
    if digest:
        fm[SOURCE_HASH_FIELD] = digest
    return fm


# Sidecars stand in for a file the pipeline cannot convert. Their body is
# boilerplate, so keywords come from the original's name and path instead --
# that is what makes the sidecar findable, and it is the whole reason the
# sidecar exists.
SIDECAR_SOURCE = "unconverted file (sidecar)"


def sidecar_keywords(fm: dict, n: int = 10) -> list[str]:
    """Keywords for a sidecar, drawn from the original's name and path."""
    parts: list[str] = []
    for field in ("source_file", "source_path"):
        raw = str(fm.get(field, "") or "")
        parts.extend(re.split(r"[\\/._\-\s]+", raw))
    seen: list[str] = []
    for token in parts:
        t = token.strip().lower()
        if len(t) < 3 or t in STOPWORDS or t in seen:
            continue
        seen.append(t)
    return seen[:n]


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
                 total_docs: int = 0,
                 subject_names: set[str] | None = None,
                 stats: Counter | None = None,
                 dictionary: set[str] | None = None,
                 artifact_log: list | None = None) -> bool:
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

    # Classify provenance structure before any weighting is applied, and
    # record it so downstream tools can see why a file was or was not
    # weighted. `unknown` is a safe default, not an error.
    structure, speakers = classify_provenance_structure(body, existing)

    tf_counts = None
    weight_note = ""
    if structure in (STRUCT_TURN, STRUCT_LABELLED):
        tf_counts, weight_note = provenance_weighted_counts(
            body, structure, subject_names)

    if str(existing.get("source", "")) == SIDECAR_SOURCE:
        kw = sidecar_keywords(existing, n=actual_n)
    else:
        # Over-fetch, then drop conversion debris, so rejecting an artifact
        # does not leave the list short.
        headroom = actual_n + 10
        if doc_freq is not None and total_docs > 0:
            candidates = top_keywords_tfidf(body, doc_freq, total_docs,
                                            n=headroom, tf_counts=tf_counts)
        else:
            candidates = top_keywords(body, n=headroom, tf_counts=tf_counts)
        kw, dropped = reject_artifacts(candidates, body=body,
                                       dictionary=dictionary,
                                       doc_freq=doc_freq)
        kw = kw[:actual_n]
        if dropped:
            if stats is not None:
                stats["artifacts_rejected"] += len(dropped)
                for _term, tier, _reason in dropped:
                    stats[f"artifacts_{tier}"] += 1
            if artifact_log is not None:
                for term, tier, reason in dropped:
                    artifact_log.append((term, tier, reason, path))

    if stats is not None:
        stats[f"structure_{structure}"] += 1
        stats["keywords_weighted" if tf_counts is not None
              else "keywords_unweighted"] += 1
        if structure in (STRUCT_TURN, STRUCT_LABELLED) and tf_counts is None:
            stats["weighting_blocked"] += 1
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
    # `date` is one of the four fields search relies on. Backfill it from the
    # best source available, and say which one was used.
    if not str(existing.get("date", "") or "").strip():
        date_value, date_source = resolve_date(existing, path)
        if date_value:
            existing["date"] = date_value
            existing["date_source"] = date_source

    # Always-overwrite computed fields.
    existing["word_count"] = wc
    existing["keywords"] = kw
    existing["provenance_structure"] = structure
    # Keywords that could not be provenance-weighted are marked as such, so a
    # reader never mistakes unweighted output for weighted output.
    existing["keywords_weighted"] = tf_counts is not None
    if structure == STRUCT_LABELLED and speakers:
        existing["provenance_speakers"] = speakers
    elif "provenance_speakers" in existing and structure != STRUCT_LABELLED:
        del existing["provenance_speakers"]
    if structure in (STRUCT_TURN, STRUCT_LABELLED) and tf_counts is None:
        existing["weighting_skipped"] = weight_note
    elif "weighting_skipped" in existing:
        del existing["weighting_skipped"]
    existing["indexed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if write_index:
        body = update_body_with_index(body, build_index_block(kw, outline))

    new_text = emit_frontmatter(existing) + "\n\n" + body.lstrip("\n")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_structure_stats(stats: Counter, unknown_files: list,
                           root: Path | None = None,
                           max_listed: int = 40) -> None:
    """Print the provenance-structure tally and list every `unknown` file.

    Every `unknown` file is reported: they are candidates for an AI pass to
    recover turns, or for the owner to locate the source conversation. The
    report is the deliverable -- no recovery is attempted here.
    """
    total = sum(stats[f"structure_{k}"] for k in
                (STRUCT_TURN, STRUCT_LABELLED, STRUCT_SINGLE, STRUCT_UNKNOWN))
    if not total:
        return
    print()
    print("Provenance structure:")
    for label in (STRUCT_TURN, STRUCT_LABELLED, STRUCT_SINGLE, STRUCT_UNKNOWN):
        print(f"  {label:<17}: {stats[f'structure_{label}']:>6,}")
    print(f"  keywords weighted: {stats['keywords_weighted']:>6,}")
    print(f"  keywords plain   : {stats['keywords_unweighted']:>6,}")
    if stats["artifacts_rejected"]:
        print(f"  artifacts dropped: {stats['artifacts_rejected']:>6,} "
              f"({stats['artifacts_hard']:,} hard, {stats['artifacts_soft']:,} soft)")
    if stats["weighting_blocked"]:
        print(f"  [info] {stats['weighting_blocked']} conversational file(s) "
              f"could not be weighted; pass --subject to name the subject.")
    if unknown_files:
        print(f"  [report] {len(unknown_files)} file(s) classified unknown:")
        for f in unknown_files[:max_listed]:
            try:
                shown = f.relative_to(root) if root else f
            except (ValueError, TypeError):
                shown = f
            print(f"    - {shown}")
        if len(unknown_files) > max_listed:
            print(f"    ... and {len(unknown_files) - max_listed} more")


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
    ap.add_argument("--dictionary", default=None,
                    help="Word list (one word per line) used to VETO keyword "
                         "rejections. Without one, a statistically odd term is "
                         "kept when it recurs across documents or appears "
                         "capitalised. A system word list is used if found.")
    ap.add_argument("--lexicon", action="append", default=None,
                    help="Directory of word lists and glossaries (repeatable). "
                         "Every .txt/.tsv/.lst under it is merged. A .tsv takes "
                         "its term from the first column.")
    ap.add_argument("--report-artifacts", default=None,
                    help="Write every rejected keyword, and the test that "
                         "rejected it, to this Markdown file. Changes nothing.")
    ap.add_argument("--no-dictionary", action="store_true",
                    help="Do not look for a system word list.")
    ap.add_argument("--subject", action="append", default=None,
                    help="Speaker label naming the subject in speaker-labelled "
                         "documents (repeatable). Without it, a document with "
                         "exactly one non-AI speaker resolves on its own and "
                         "any other stays unweighted.")
    args = ap.parse_args()

    subject_names = ({s.lower() for s in args.subject}
                     if args.subject else None)

    lexicon_dirs = list(args.lexicon or [])
    if not lexicon_dirs and (SCRIPT_DIR / "lexicon").is_dir():
        lexicon_dirs.append(SCRIPT_DIR / "lexicon")
    dict_file = args.dictionary
    if dict_file is None and not args.no_dictionary:
        found = find_system_dictionary()
        dict_file = str(found) if found else None

    dictionary, lex_files = load_lexicons(lexicon_dirs, dict_file)
    dictionary = dictionary or None
    if lex_files:
        print(f"Lexicon: {len(dictionary):,} terms from {len(lex_files)} file(s)")
        for entry in lex_files[:10]:
            print(f"  {entry}")
        if len(lex_files) > 10:
            print(f"  ... and {len(lex_files) - 10} more")

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
    stats: Counter = Counter()
    unknown_files: list[Path] = []
    artifact_log: list = [] if args.report_artifacts else None
    for f in files:
        before = stats["structure_unknown"]
        if process_file(f, n_keywords=args.keywords,
                        write_index=not args.no_index,
                        doc_freq=doc_freq, total_docs=total_docs,
                        subject_names=subject_names, stats=stats,
                        dictionary=dictionary, artifact_log=artifact_log):
            changed += 1
        if stats["structure_unknown"] > before:
            unknown_files.append(f)

    print(f"Processed {len(files)} file(s); updated {changed}.")
    report_structure_stats(stats, unknown_files, root)
    if args.report_artifacts and artifact_log is not None:
        write_artifact_report(args.report_artifacts, artifact_log, root)
        print(f"Rejected-keyword report written to {args.report_artifacts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
