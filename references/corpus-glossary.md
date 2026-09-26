# Corpus Glossary

**Version 1.1**

The corpus data model, shared by the skills that search it and by the digestion
pipeline that builds it. Where any document disagrees with this file, this file
is what reconciles them.

## Corpus and its parts

**Corpus** — all of a project's material, in four places: the current
conversation, the project's past conversations, its Evernote notes, and the
Drive repository. A search of "the corpus" covers all four.

**Repository** — the Drive folder tree alone: the four tiers and what sits
beneath them. Part of the corpus, not a synonym for it.

**Production corpus** — the home of a project. Carries all four tiers, because
the project's derived writing and released artifacts accumulate there.

**Reference corpus** — a corpus no project produces into. Carries `1-Raw` and
`2-Digested` only, because nothing is accumulating in the authored tiers.

The distinction is **whether a project produces into the corpus**; the tier
structure follows from that. Both kinds are read-only to a searcher. A Reference
corpus can be promoted to Production if a project starts on it — nothing about
the classification is one-way.

**Primary and secondary corpora** — a different axis, and independent of the
first. Production versus Reference is a fact about a corpus. Primary versus
secondary is a fact about one agent's relationship to it in one search: the
corpus an agent belongs to is primary, the others it reaches into are secondary.
A Production corpus owned by one project can be secondary for another project's
agent.

**Project** — a Claude project. One project, one **Production** corpus, and
zero or more Reference corpora. Conversation search is
scoped to a project, which is why nothing outside a project can enumerate its
conversations.

**Tier** — one of the four folders directly beneath the repository root. Only
these four names are fixed; everything below them is enumerated, never assumed.

- **`1-Raw`** — incoming material in any format, by any path.
- **`2-Digested`** — pipeline output: converted, classified, indexed. Complete
  with respect to `1-Raw`, because the pipeline copies through or sidecars
  whatever it cannot convert.
- **`3-Reporting`** — derived writing: reports, transcripts, commentary.
  Derived rather than new, whatever produced it.
- **`4-Canon`** — released artifacts. What the project produces.

**Utility siblings** — folders and files at the repository root that are not
corpus content: tooling, editor configuration, generated listings, audit
output. Not searched.

## Live sources

**Live source** — a connector reaching material as it stands now, without
waiting for export and digestion. Evernote is one. Live sources exist because
the repository lags its sources by an export cycle; that lag is a standing
condition, not a gap awaiting closure.

**Archive stack** — an Evernote stack, `_Archive` by default, holding notebooks
named `<notebook> -- Archive`. A note moved there has been exported and filed;
corpus searches exclude the stack so a live hit always means *not yet filed*.

**More authoritative** — of two copies of the same item, the fresher one. Not
*canon*, which is a tier of the repository meaning released material and says
nothing about freshness.

## Pipeline

**Pipeline**, or **digester** — the local Python that converts `1-Raw` into
`2-Digested`, writes frontmatter, and maintains the index. Runs offline; is not
an agent.

**Index** — `_index.json` in `2-Digested`, written by the pipeline. The
authored tiers carry no index by design, and its absence there is expected.

**Manifest** — `<PROJECT_UUID>_manifest.json`, listing every conversation in a
project by UUID and title. A pipeline input, used to group exported
conversations by project. Does not follow the corpus filename convention.

**Sidecar** — a small Markdown stub in `2-Digested` standing for a file in
`1-Raw` that could not be converted, recording its name, type and source path.
Makes the original findable without duplicating it.

**Push** — local to Drive. **Pull** — Drive to local. **Mirror** — the Drive
copy, which follows local; local is authoritative.

## Shared reference files

A **shared reference file** is bundled in more than one skill, or also used by
the pipeline: this file, `reporting-glossary.md`, `repository-structure.md`,
`project-manifest-format.md`. **A shared file carries its own version,
independent of every skill that bundles it.** Every copy shows the same
version, and it changes only when the content does. Stamping a shared file with
its host skill's version makes identical copies look different and different
copies look alike, which defeats the reason for versioning it.
