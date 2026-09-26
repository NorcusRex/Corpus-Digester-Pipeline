# Designer Response — version mismatch defect

*Received from the AI Methods conversation as the cover note to
`project-manifest-format.md` 1.4. Reproduced verbatim. Verified on receipt: the
diff against 1.3 is two hunks, the header and the Versioning section's first
line, and nothing else in the file moved.*

| File | Was | Now |
|---|---|---|
| `project-manifest-format.md` | 1.3 | **1.4** |

**Defect confirmed and fixed.** Header said 1.3, the *Versioning* section's
first line said 1.2. The body line was stale, as diagnosed — it was written when
the file was 1.2 and was not updated when the header moved.

**Fixed by removing the duplicate rather than correcting it.** The section now
reads "This document describes `manifest_format_version` **1.0**. Its own
version is in the header above." A document that states its own version twice
will drift; one that states it once cannot.

The wire format is unchanged. `manifest_format_version` is still `"1.0"`.

Nothing else in the file changed. `repository-structure.md` v2.3 is unaffected.
