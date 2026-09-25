# Project Manifest Format

**Version 1.1**

The format contract for a project manifest. Written by the
`update-project-manifest` skill and read by whatever consumes it.

**One worked consumer, as an example.** A local digestion pipeline reads the
manifest to group exported conversations into project folders. Nothing in the
format assumes that consumer; any tool organizing an export can use it.

This file is the contract, not the procedure. How a manifest is generated is in
the skill; what a manifest must contain is here. Copy this file wherever a
consumer of manifests lives.

## Filename

```
<PROJECT_UUID>_manifest.json
```

**This does not follow the corpus filename convention**, and must not be
changed to it. A manifest is a machine-read pipeline input keyed by project
UUID, not a corpus document. Renaming it to a timestamped, versioned form
breaks the pipeline's ability to find it.

## Structure

```json
{
  "manifest_format_version": "1.0",
  "project_uuid": "0f9e2c31-9c7a-4a11-b6a1-7f2c1d5e8a90",
  "project_name": "AI Methods",
  "generated_at": "2026-09-17T09:42-07:00",
  "conversation_count": 3,
  "conversations": [
    {
      "uuid": "3578b852-6bae-46e7-9268-393fbe0f2b55",
      "title": "Reconstructing the digestion pipeline",
      "updated_at": "2026-05-21T18:03:11Z"
    }
  ]
}
```

## Fields

**`manifest_format_version`** — first key in the file, so it is visible without
parsing. States which revision of this document the manifest conforms to. A
manifest is a handoff artifact that crosses a boundary; a file that says what
format it is in is better than one that does not.

**`project_uuid`** — the project's UUID, matching the filename. Never invented;
it comes from the user or from the project URL.

**`project_name`** — the project's display name, for human readers.

**`generated_at`** — local timestamp with offset, in the corpus owner's zone.

**`conversation_count`** — the number of entries in `conversations`. A
redundant field that makes truncation detectable.

**`conversations`** — every conversation in the project, each with `uuid`,
`title`, and `updated_at` as returned by the enumeration.

## Ordering

**Oldest to newest by `updated_at`.** A manifest regenerated after new
conversations appear then differs from its predecessor only by appended
entries, so diffs stay readable and stable. Any other ordering reshuffles the
file on every run and makes real changes hard to see.

## Encoding

UTF-8, two-space indentation, no BOM. Titles are written as they appear,
including punctuation and non-ASCII characters; do not escape or normalize
them.

## Versioning

The version in this document and the value of `manifest_format_version` move
together: this document at v1.0 describes `"manifest_format_version": "1.0"`.

The pipeline is **not** versioned in step with the format. It declares which
format versions it accepts; the two enumerations are independent, and coupling
them would mean bumping the format every time the pipeline changes.

An unrecognized or absent version is simply an unusable manifest, and falls to
whatever the consumer already does with a missing or malformed one. No special
rule is needed.

## What is not versioned

`_index.json` is written and read by the same code in the same run, so skew is
not possible and a version would be ceremony. `project_names.tsv` is a
hand-maintained lookup that fails visibly when malformed. Neither crosses a
boundary, which is the only thing this version field is for.
