# Repository workflow library

This directory is the repository-backed shared workflow catalog used by
SineForge’s embedded native API Runner.

## Contents

- `catalog.json` is the deterministic inventory, provenance, category, and
  checksum manifest.
- `records/*.json` contains one complete library record per workflow. Each
  record includes the converted ComfyUI API graph, the original editor-format
  graph, a detailed description, operating instructions, model and node
  requirements, source archive/entry provenance, and stable hashes.
- `assets/` contains non-executable support data shipped with the workflow
  packs. Assets are never presented or queued as workflows.

The records are built from the Episode 02–25 and Episode 28 workflow packs.
Episode 12 contains custom-node source examples but no workflow graph, so it is
documented in `catalog.json` without fabricating a runnable entry.

Repository records are immutable and authoritative. The native Runner merges
them with the operator library under `storage/native_api_runner/`, but rejects
update and archive requests for repository ids. Use **Save as copy** to create
an editable operator-owned workflow. The original editor graph can be copied or
downloaded as raw JSON for archival or conversion, while all supported editing,
validation, and execution remains in the Sineforge Engine workspace.

## Rebuild

Run `scripts/import_repository_workflow_packs.py` with:

1. A safely extracted source-pack root.
2. The directory containing ComfyUI’s API-format exports using the stable
   `SFCatalog20260730A_<index>_<source-hash>.json` names.
3. This directory as `--output-root`.
4. The authoritative custom-node root as `--custom-node-root`.

The current authoritative LTX custom-node root is:

`C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes`

The importer is deterministic: stable ids, timestamps, ordering, descriptions,
instructions, provenance, and hashes do not depend on the machine clock.
