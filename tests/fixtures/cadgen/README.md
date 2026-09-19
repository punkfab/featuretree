# cadgen fixtures (real output, not synthetic)

Genuine artifacts written by cadgen (text-to-cad "CAD Skills", MIT — github.com/earthtojake/text-to-cad)
for its planetary-gear hero model, used to test `cadgen_ingest.py` against the *real* schema:

- `planetary_gear_assembly.step.json` — the kinematics **sidecar** (schemaVersion 9): typed mates with
  `parentId`/`childId` occurrence refs AND `#label` refs, a gear coupling, named poses.
- `planetary_assembly.json` — the **materialized tree** package descriptor: the `o1.N` occurrence
  tree, part names, placements, component ids. (Its `components/*.surf` geometry blobs are not
  included; structure/mate-join tests need only the descriptor.)

Neither file is modified. Together they exercise the sidecar↔occurrence join on real data.
