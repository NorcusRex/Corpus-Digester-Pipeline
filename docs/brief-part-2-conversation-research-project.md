# Research Project Brief — Part 2

**Topic:** The Conversation in TTRPGs — historical record across the corpus.
**Status:** Project framing complete. No drafting begun. Infrastructure ready (SearchLibrary, digestion pipeline, source archive).

---

## 1. The research question

A historical survey of how "The Conversation" — the conversational structure of TTRPG play — has been treated across the corpus, explicitly or implicitly, system by system, era by era.

User's framing: "TTRPGs have a core element we can call 'The Conversation'. Even solo mode games have it even if it is a monologue, a journal, or in one's head. The playstyle, systems, and theory discussions over the years have treated The Conversation differently, often only implicitly."

**Scope:** Scan all games and other content (e.g., Dragon Magazine) in the personal library, compose a historical record.

**Discipline:** Real scholarly work. Comparative analysis across thousands of documents, organized chronologically and thematically, with citations back to specific texts.

---

## 2. Why Blades in the Dark anchored the discussion

User pasted (subsequently discussed for removal due to length, see §7 below) the "Players / Game Master / Playing a Session / The Conversation / Judgment Calls" sections from *Blades in the Dark, Special Edition* (John Harper, 2017).

This passage is significant for the project because it represents one of the most **explicit** treatments of The Conversation as a named design concept in commercial RPG publishing:

1. **Names the thing.** Section heading "THE CONVERSATION" is rare in design-theory prose pre-2010s.
2. **Defines it concisely.** "A roleplaying game is a conversation between the GM and the players, punctuated by dice rolls to inject uncertainty and surprising turns."
3. **Pairs naming with structural argument.** The "Judgment Calls" section assigns final-say authority over specific categories between players and GM. This is a more nuanced position than either traditional GM-as-arbiter or vague everyone-collaborates framings.
4. **Connects to PbtA lineage.** "Play to find out what happens" language ties to Apocalypse World / Vincent Baker.

**Suggested entry for project notes:**

```
Harper, J. (2017). Blades in the Dark, Special Edition. Evil Hat Productions.

Treats The Conversation as named, foundational element of play.
Explicit section heading "THE CONVERSATION." Defines play as
"a conversation between the GM and the players, punctuated by
dice rolls." Pairs with explicit "Judgment Calls" section that
assigns final-say authority over specific categories of decision
between players and GM. Notable as one of the most explicit
treatments of conversation-structure in commercial RPG design
of the 2010s.

Related lineage: PbtA / Vincent Baker (Apocalypse World), Ron
Edwards's earlier theoretical work on shared imagined space and
group decision-making at The Forge.

Page reference: [pages from Special Edition core book]
```

---

## 3. Suggested research structure

### Survey terms to search for

**Explicit terms:**

- "conversation," "dialogue," "table talk," "roleplay" (in the verbal sense), "in-character"

**Implicit indicators:**

- "the GM describes," "the player declares," "the group decides," "narration," "fiction," "speak in voice"

**Theoretical framing:**

- "fiction-first," "moves," "say yes," "lonely fun," "shared imagined space," "diegetic"

**Style markers:**

- "freeform," "improvisational," "scripted," "structured"

### Eras to survey

1. Pre-D&D wargaming roots (Braunstein, Blackmoor)
2. Early D&D and AD&D family (1974-83): OD&D, Holmes, Moldvay, AD&D
3. First wave of alternatives (RuneQuest, T&T, C&S, etc.)
4. The storytelling wave (1991+): Vampire, Amber, Over the Edge
5. The Forge era and indie design theory (2001-2008)
6. PbtA and Story Games (2010+)
7. OSR revival
8. Current era (Quinns Quest, story-now design, solo journaling games)

### Where Claude fits

**Good uses:**

- Surveying chapters and reporting where conversation/dialogue/narration topics appear
- Comparing passages across multiple games
- Drafting analytical sections from user-provided notes

**Bad uses:**

- Discovery (use grep/Obsidian/reading instead — Claude won't find what you don't point it at)
- Authoritative historical claims about obscure RPG history (Claude's training data is unreliable on niche TTRPG history; trust primary sources)

### Where the work lives

```
I:\RPG\_Conversation Project\
    1-Sources\          ← excerpts, notes, links to specific pages
    2-Drafts\           ← analysis as it emerges
    3-Output\           ← the historical record itself
```

Books stay in `_SearchLibrary\`. Project folder accumulates the work *about* the books.

---

## 4. Suggested workflow phases

**Phase 1: Working definition.** Before searching, articulate what "The Conversation" actually means in user's framing. ~200 words. This becomes the analytical lens.

**Phase 2: Era-by-era survey.** Pick an era. Survey library holdings from that era. Search relevant terms in those books. Take notes.

**Phase 3: Thematic synthesis.** Across eras, what patterns emerge? Where was The Conversation discussed explicitly? Where assumed? What changed and when?

**Phase 4: Write.** The historical record itself, with citations.

**Start small.** Pick one era (the Forge era is a good candidate; user already has familiarity from prior Claude conversations). Survey just that. See what the output feels like before scaling to 50 years of history.

**Let structure emerge from texts.** Don't outline the whole record on day one. The real organizing axis may turn out to be different from initial expectations (e.g., "performance vs procedure" rather than "explicit vs implicit").

**Citation discipline from the start.** Every claim about a game's treatment of The Conversation tied to a specific page in a specific edition. APA-style with footnotes works. Whatever the system, be consistent throughout.

---

## 5. Copyright and fair use — extensive discussion

### The fair use four-factor framework (US, 17 U.S.C. § 107)

**Factor 1: Purpose and character.** Transformative use favored. Scholarship, criticism, commentary explicitly favored by statute. A historical record is squarely in the criticism/scholarship zone.

**Factor 2: Nature of the work.** Game design text is mixed: mechanical procedures barely protectable (mechanics can't be copyrighted); creative writing, settings, art highly protected. Design-theory prose falls between.

**Factor 3: Amount and substantiality.** Where most disputes turn. Three considerations:

- *Quantitative:* sentence safer than paragraph, paragraph safer than page
- *Qualitative:* taking the "heart" of a work is worse than random middle pages
- *Proportionality:* 50 words from 200,000-word novel different from 50 words from a haiku

**Factor 4: Market effect.** Does your use substitute for buying the original? Critical analysis doesn't substitute; review-and-summary reproducing playable rules does.

### Practical thresholds

**Almost certainly fine without permission:**

- Short quoted passages (1-3 sentences) for analysis, with attribution
- Paraphrasing with citation
- Discussing what a book covers
- Comparing approaches across books
- Reproducing factual information
- Critique, positive or negative

**Probably needs permission:**

- More than ~10% of a chapter verbatim
- Complete rules subsystems or stat blocks
- Illustrations, maps, art
- Character sheets or other usable forms
- Reproductions that could substitute for buying

### The longer-quote question (revisited)

User correctly pushed back on "1-3 sentences feels too short" for a project whose purpose is partial preservation. **The corrected standard:**

- **Block quotes (50-300 words)** for passages whose specific language is being analyzed in depth: routine in scholarly publishing per Chicago Manual of Style, MLA Handbook, university press guidelines
- **Full quotation of short discrete sections** (a sidebar, a paragraph-length design note): generally fine when analyzing that specific element
- **Not fine:** quoting so much that the reader can substitute the work for the original

**Critical principle:** Quote what you analyze and only what you analyze. The mistake isn't "long quote"; it's "quote that sits there unanalyzed."

### The mixed-practice approach

**For analytical text:**

1. Direct quotation for the specific words being analyzed (when exact words matter)
2. Paraphrase for surrounding context and connective tissue
3. Citation specific enough that readers can verify

**For preservation (separate function):**
Consider a primary-source appendix layer that preserves longer excerpts with explicit framing about preservation purpose. This is recognized scholarly practice for ephemeral/inaccessible material.

### User's distilled rule

> "Only quote sentences you analyze. No more than 300 words. Paraphrase the rest. Cite all."

**Refinements:**

- 300 words isn't a hard ceiling, it's a threshold for thinking harder about necessity. 400 words for a paragraph-by-paragraph analyzed passage is fine. 200 words you don't engage with isn't.
- "Cite all" — but citation as enabling verification, not as decoration. Be specific about edition and page.

### The cherry-picking and citation-laundering problem

User correctly identified: the practice can be done in a misleading way. Citation discipline doesn't prevent misuse; it makes misuse more detectable.

**Mitigations (not solutions):**

- Quote enough context that the reader can judge whether the quoted sentence means what you say
- Acknowledge complexity in the source when it exists
- When analysis depends on contested interpretation, signal that
- Cite enough that a determined reader can falsify your claims

**The honest position:** None of this prevents bad-faith use of citation. But it makes good-faith use possible and gives readers tools to evaluate the work rather than blindly trust it.

---

## 6. The access problem — substantial scholarly point

User raised: "Very few people in the hobby or outside it have access to all the original works. I have spent many years collecting and scanning them. The quotations serve as a record and citations don't do as much good when almost no one can use them to confirm what I am saying."

**This is correct, and it changes the scholarly calculus.**

The standard citation model assumes accessible sources (libraries, ILL, JSTOR, etc.). The TTRPG corpus violates this assumption badly — pre-2000 material, out-of-print zines, defunct publishers, Dragon Magazine back issues. A citation to *Different Worlds* issue 23 page 14 points at something almost no reader can verify.

**Documentary scholarship traditions** allow longer quotation when sources are inaccessible. When you're preserving the record because no one else has it, scholarly convention treats preservation function as part of the work's value. Comics scholars, zine historians, early-internet researchers face the same problem.

**Archival appendices** are a recognized form. Scholarly books on obscure topics sometimes include substantial primary-source appendices: full or partial reproductions of key documents, organized by theme, that the analytical text references. Permission typically sought for these in commercial publishing, but the function (preservation) is exactly what user described.

**Acknowledging the access problem in your text strengthens your position.** Phrasing like "Issue 47 of [obscure zine] is held in only a handful of private collections; the full text of the relevant passage is reproduced here for readers who cannot otherwise consult it" moves the work from "I'm quoting a lot" to "I'm preserving a record." Both courts and publishers treat these differently.

### Suggested two-layer structure

**Layer 1: The analytical text.** Argument about how The Conversation has been treated. Tightly quoted, carefully analyzed, scholarly tone. Synthesis is the contribution; quotations serve analysis; citations point to Layer 2.

**Layer 2: A primary-source archive.** Appendix or companion document with fuller excerpts. Bibliographic information, brief contextualization. Where readers turn to verify or read originals for themselves.

This lets you preserve more without weakening the analytical text. Changes the permission conversation: "include in archival appendix" reads differently to publishers than "quote in chapter body."

### Internet Archive and Drivethru caveat

Some books unfindable in 2010 are now available (Drivethru PDF rereleases, OSR community archival work). Cite available access paths where they exist: "available from DriveThruRPG as of 2024" or "reproduced in [later anthology]." Not every source will have this, but where it does, it strengthens the citation.

---

## 7. Why the Harper quote is being removed from this conversation

User pasted approximately 800-900 words from *Blades in the Dark* (the Players / GM / Playing a Session / Conversation / Judgment Calls sections). After discussion, user decided to remove this from the conversation history before deleting this chat.

**Reasons addressed:**

- For personal research notes: fine to keep longer excerpts in private archive
- For Claude conversations: accumulating verbatim copyrighted text across many conversations creates exposure and noise
- For published work: longer passage needs scholarly fair use treatment or permission; shouldn't sit verbatim in chat history

**User's instinct to request permission before publishing — affirmed.** Not crazy. Putting permission ahead of fair-use defense is the conservative, professional path. Fair use is a defense (i.e., for after a lawsuit); permission is avoidance of lawsuit. The latter is preferable for a project intended for publication.

---

## 8. The realistic legwork question

User correctly anticipated: doing this properly involves considerable administrative work. For 100-300 distinct sources, at 30-60 minutes per source for rights determination/permission/orphan-work documentation: 50-300 hours over the project's life. Real cost.

### Three honest paths

**Option 1: Full systematic permissions.** Suitable for scholarly or commercial publication aimed at reaching broad audience and being cite-able by future scholars. Slow but produces publication-ready manuscript with strong legal footing.

**Option 2: Tier by source importance.** The 20-30 books your argument actually depends on get rigorous permission work. The 200 books you mention in passing get short quotes with citation on fair-use grounds. Concentrates effort where it matters. Probably the realistic path for serious individual project.

**Option 3: Reframe the deliverable.** Blog series, website, Patreon longform, personal scholarly document within the hobby community. Different artifact, lower legal exposure, lighter permission requirements, more generous fair-use latitude. Downside: less reach, less authority, less likely to be cited.

### Pragmatic staging suggested

- **Year 1:** Build research archive (already done — SearchLibrary, pipeline, note practice). Draft sections for eras you know best. Test format. Publish small pieces (essays, blog posts) using fair-use quotation. Gather response.
- **Year 2:** If work is taking shape and finding readers, start permission groundwork. Opportunistically as you write each section, not all upfront.
- **Year 3+:** If publisher emerges or you decide to self-publish definitive version, systematic legal review. By then you know which works are central, so permission work is targeted.

This matches how most serious independent scholarship gets done. The legal infrastructure builds as the project matures, not before it starts.

### Orphan works guidance

For older defunct-publisher material, document good-faith efforts to locate rights-holders:

- Search state corporate records for publisher
- Search for designer (LinkedIn, professional registries, hobby contacts)
- Search reversionary chains (indie publishers transferred rights back to designers when folding)
- Search for successor publishers
- Document each search with date and outcome
- After reasonable effort fails, you have documented orphan-work record

TTRPG community resources help: RPG Geek bibliographic data, OSR community archival work, Drivethru's catalog of revived games, designer-active forums.

---

## 9. User's final decision

> "It is just a really fascinating research question. I will at least try to answer it for myself."

**Implicit framing:** The project's primary purpose is curiosity-driven inquiry. Publication is secondary. Doing the work well — including caring about the source material legally and intellectually — is the discipline that gives the work value, regardless of eventual distribution.

### Notes offered for proceeding

- **Write as if for an audience even if there isn't one.** Notes-to-self diverge from publishable prose quickly. Writing in shareable form preserves option without committing.

- **Keep private notes private.** Research archive can be messy with longer excerpts; published-output layer carries the discipline.

- **Find interlocutors.** Even if eventual artifact is for self, a few people who care about the same questions accelerate everything. Communities mentioned: Story Games forum (defunct but archived), various designer Discords, RPG.net design subforum, Forge archives, podcasts like *The Indie Hack* or *Design Doc*.

- **Notice when you change your mind.** A real historical record will shift your views. Keep notes on the shifts — when you stopped thinking X and started thinking Y, what source moved you. Often the most interesting parts of eventual writing.

- **Let the question stay open.** Research questions of this kind don't resolve cleanly. May end with a richer understanding rather than a definitive answer. Not failure; the actual shape of intellectual work on complex topics.

---

## 10. State of play

**Infrastructure ready:**

- SearchLibrary structure agreed and being populated
- Batch OCR tooling identified (ocrmypdf + Tesseract)
- Digestion pipeline tested and working
- Two-library archive structure migrated successfully
- Phase A1 keyword improvements applied

**Project not yet started:**

- No drafting begun
- No working definition committed to writing
- No era survey initiated
- No permissions sought

**Next concrete action (when user resumes):**
The smallest meaningful first step: write the ~200-word working definition of "The Conversation" in user's framing. That single deliverable gives the project a stable foundation and tests whether the question is as well-formed as it currently feels.

**Practical first survey suggestion:** Forge era (2001-2008), since the user has prior Claude conversations on this material that can seed initial reading lists. Or, alternatively, the explicit naming moment in the early-2010s PbtA family, working backward from Blades' explicit treatment to find where naming The Conversation became a design tool.

---

## 11. Closing reference notes

**The Conversation as a concept** has at least these distinct treatments in the TTRPG design literature:

1. **Implicit procedural** — most pre-1990 games. The GM does X, players do Y, dice resolve Z. The conversational structure is the medium but not discussed.
2. **Performance-oriented** — early storytelling games (Vampire 1991+). Emphasis on dramatic narration, in-character speech, atmospheric description.
3. **Theoretical-analytical** — The Forge era. Ron Edwards's work on "shared imagined space," GNS theory, the principle/agenda design of Apocalypse World.
4. **Procedural-with-naming** — Blades in the Dark and contemporaries. Names the thing, structures judgment calls explicitly, codifies authority distribution.
5. **Solo/journaled** — recent solo journaling games. The conversation as monologue, prompts as substitutes for table dynamics.

These are working categories, not definitive ones. The historical record's job is to find the actual structure, not impose a preconceived one.

---

*End of brief.*
