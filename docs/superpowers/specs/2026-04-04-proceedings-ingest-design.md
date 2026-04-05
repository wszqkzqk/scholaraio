# Proceedings Ingest Design

Date: 2026-04-04
Branch: `issue-46`
Related issue: `#46`

## Summary

Add first-class support for single-file proceedings ingestion.

The system should recognize that a very large PDF may be a proceedings volume rather than a single paper, route it through a dedicated proceedings pipeline, store the results in a new `data/proceedings/` hierarchy, and keep proceedings content out of default main-library search. Federated search should gain a `proceedings` scope so users can opt in when they want cross-library retrieval.

## Goals

- Support a dedicated manual inbox for proceedings volumes.
- Support proceedings ingest from the dedicated `data/inbox-proceedings/` inbox only.
- Store proceedings data in a filesystem hierarchy separate from `data/papers/`.
- Split a proceedings volume into per-paper records under its own collection directory.
- Keep default `search`, `usearch`, and `vsearch` behavior unchanged.
- Allow `fsearch`-style federated retrieval to include proceedings via an explicit `proceedings` scope.

## Non-Goals For V1

- Mixing proceedings papers into the main paper registry.
- Making proceedings content searchable by default in main-library commands.
- Perfect paper-boundary extraction for every proceedings format.
- Solving every anthology, edited book, or scanned archive edge case in the first release.

## User Experience

### Ingestion

Users can ingest proceedings in one way:

1. Manual routing: place a proceedings PDF in `data/inbox-proceedings/`.

### Storage

Proceedings data should live under a new tree:

```text
data/proceedings/
└── <Proceeding-Dir>/
    ├── meta.json
    ├── proceeding.md
    ├── papers/
    │   └── <Paper-Dir>/
    │       ├── meta.json
    │       ├── paper.md
    │       └── images/
```

`<Proceeding-Dir>` represents the volume. Each child under `papers/` represents one extracted paper from that volume.

Global proceedings indexes live alongside the proceedings root rather than inside each volume directory:

```text
data/proceedings/
├── proceedings.db
├── faiss.index
├── faiss_ids.json
└── <Proceeding-Dir>/
```

### Search

- Default main search commands continue to search only `data/papers/`.
- Federated search gains a `proceedings` scope.
- Federated results from proceedings must visibly indicate that they come from proceedings data and show the source volume title.

## Approaches Considered

### Approach A: Separate proceedings library and separate index

Store proceedings outside the main paper library and give them their own indexing path. Federated search merges results at query time.

Pros:

- Cleanest conceptual boundary.
- Lowest regression risk for existing paper workflows.
- Easy to reason about scope-specific behavior.

Cons:

- Requires some new indexing and retrieval glue.

### Approach B: Separate files but shared SQLite database

Keep proceedings on disk separately but register them inside the main search database as a second content family.

Pros:

- Fewer physical index files.

Cons:

- Higher coupling with existing paper search assumptions.
- Harder to keep boundaries clean over time.

### Approach C: Ingest-only V1

Only add proceedings import and filesystem structure now; defer search support.

Pros:

- Fastest implementation.

Cons:

- Incomplete workflow for users.

## Recommendation

Use Approach A.

It matches the desired product boundary: proceedings are distinct from ordinary papers, default search remains stable, and federated search becomes the single intentional place where the two libraries meet.

## Architecture

### 1. Routing Layer

Proceedings routing is explicit rather than heuristic.

Routing input:

- User-selected inbox (`data/inbox-proceedings/`) forces proceedings mode.

Regular `data/inbox/` items stay on the normal paper/document path even if they contain proceedings-like cues.

### 2. Proceedings Pipeline

Proceedings ingest should become a separate pipeline path rather than an overload of the single-paper path.

High-level stages:

1. Convert source PDF to Markdown.
2. Extract proceedings-level metadata.
3. Segment the Markdown into candidate per-paper chunks.
4. Extract metadata per chunk.
5. Write proceedings and child-paper artifacts under `data/proceedings/`.
6. Build or refresh proceedings-local indexes.

### 3. Segmentation Model

V1 should use heuristic segmentation, not a perfect document-structure parser.

Candidate boundaries can come from:

- Repeated H1-style title patterns.
- Pages with distinct DOI + title + author clusters.
- Major heading resets that look like new papers.
- TOC guidance when available.

The segmentation layer should produce a list of child paper payloads, each with:

- title candidate
- author candidate block
- DOI candidate
- markdown slice
- page or chunk provenance when available

### 4. Storage Model

Proceedings-level `meta.json` should include:

- id
- title
- year
- editors if available
- source venue / series if available
- source_file
- detected_via (`manual_inbox` or `auto_detect`)
- child_paper_count

Child-paper `meta.json` should stay close to current paper metadata fields and additionally include:

- proceeding_id
- proceeding_title
- proceeding_dir

This keeps downstream reuse easy without polluting the main paper registry.

### 5. Retrieval Model

Proceedings search should be opt-in through federated search scope expansion.

Expected behavior:

- `main` searches current paper library.
- `proceedings` searches `data/proceedings/`.
- `fsearch` can combine them, normalize result shape, and label origin.

V1 can prioritize keyword search first if needed, with semantic retrieval added using the same pattern as the main library once the data path is stable.

## Module Changes

### `config.py`

- Add `data/inbox-proceedings/` and `data/proceedings/` to ensured directories.
- Add config knobs only if clearly needed for segmentation thresholds.

### `ingest/pipeline.py`

- Add proceedings inbox processing.
- Do not auto-route regular inbox items into proceedings; require explicit placement in `data/inbox-proceedings/`.
- Keep thesis detection and proceedings inbox routing independent and ordered clearly.

### `ingest/extractor.py`

- Avoid forcing single-paper assumptions once a file is explicitly classified as proceedings.

### New proceedings module(s)

Suggested additions:

- `scholaraio/proceedings.py` for path helpers and metadata I/O.
- `scholaraio/ingest/proceedings.py` for segmentation and writeout orchestration.

### `index.py` or new proceedings indexing module

- Add proceedings-specific index build/read helpers, or a dedicated module if that keeps boundaries cleaner.

### `cli.py`

- Extend pipeline entry points to process the new inbox.
- Extend federated search scopes to include `proceedings`.
- Ensure user-facing messages make the library boundary explicit.

### Docs

- Update AGENTS and user docs once implementation is complete.

## Error Handling

- If a proceedings volume is manually routed but segmentation produces no viable child papers, move it to a proceedings-specific pending/review state rather than silently ingesting it as one paper.
- Partial segmentation success is acceptable in V1 if the volume-level record is preserved and failed child chunks are surfaced clearly.

## Testing Strategy

### Detection tests

- Manual proceedings inbox forces proceedings mode.
- Regular inbox items stay on the normal paper flow unless the user explicitly places them in `data/inbox-proceedings/`.
- Typical single papers do not get misclassified as proceedings.

### Storage tests

- Proceedings volume writes to `data/proceedings/`, not `data/papers/`.
- Child papers land under the proceeding directory with expected metadata links.

### Search tests

- Default search excludes proceedings.
- Federated search with `proceedings` scope includes proceedings child papers.
- Mixed federated results carry origin labels.

### Regression tests

- Existing paper and thesis ingest behavior remains unchanged.
- Existing main search behavior remains unchanged.

## Implementation Plan Shape

Recommended implementation order:

1. Add directory/config scaffolding.
2. Add proceedings detection entry points.
3. Add proceedings filesystem model and writer helpers.
4. Add segmentation with tests using the sample proceedings PDF when practical.
5. Add federated search scope support.
6. Update docs and examples.

## Open Questions Deferred

- Whether proceedings should have a dedicated `show` path in V1.
- Whether child papers should get notes support immediately.
- Whether proceedings search should reuse the exact same DB schema as the main library or a narrower schema first.

## Acceptance Criteria

- A proceedings PDF can be ingested through a dedicated inbox.
- Proceedings processing starts only from the dedicated `data/inbox-proceedings/` inbox.
- Extracted child papers are stored under `data/proceedings/`.
- Default search commands do not return proceedings content.
- Federated search can include proceedings content via explicit scope selection.
