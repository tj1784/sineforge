# Headless ComfyUI API Plan

> Current unified-app note: Sineforge owns BlokeyUI on
> `http://127.0.0.1:8190` and uses `/api/*` for new integration code. Port 8188
> examples below describe generic ComfyUI conventions, not this workstation's
> active binding. The legacy external Runner is not part of this flow.

Evidence sources: ComfyUI server docs, message docs, server source, and official API examples listed in `Sources/SOURCE_REGISTER.md`.

## API Function Matrix

| API Function | Endpoint / Mechanism | Request Shape | Response Shape | Failure Signal | Backend Use |
|---|---|---|---|---|---|
| Submit workflow | `POST /prompt` | `{ "prompt": workflow_api_json, "client_id": uuid }` | `{ prompt_id, number, node_errors }` | HTTP 400, non-empty `node_errors`, WebSocket `execution_error` | Enqueue generation |
| Queue status | `GET /prompt` or `GET /queue` | None | queue metadata | HTTP error or stale queue | Health/visibility only; avoid aggressive polling |
| History list | `GET /history?max_items=N&offset=M` | Query params | history records | Empty/missing run | Audit/recovery |
| Prompt history | `GET /history/{prompt_id}` | Path param | `{ prompt_id: { outputs, status, prompt } }` | `{}` if not complete/missing | Output discovery |
| WebSocket progress | `ws://host:8188/ws?clientId=<uuid>` | client id | JSON events: `execution_start`, `executing`, `progress`, `executed`, `execution_error`, etc. | disconnect, error event | Primary completion/progress channel |
| View output | `GET /view?filename=...&subfolder=...&type=output` | Query params | binary file | 404/path error | Retrieve images/video files |
| Upload image | `POST /upload/image` | multipart `image`, optional `type`, `subfolder`, `overwrite` | `{ name, subfolder, type }` | HTTP error | I2V inputs, masks, references |
| Interrupt | `POST /interrupt` | `{ "prompt_id": id }` or empty/global | status response | No effect if wrong prompt | Stuck job recovery |
| Queue delete/clear | `POST /queue` | `{ "delete": [ids] }` or `{ "clear": true }` | status response | Queue unchanged | Remove pending jobs |
| Free memory | `POST /free` | `{ "unload_models": true, "free_memory": true }` | status response | VRAM remains high | Between risky jobs/restart policy |
| Object metadata | `GET /object_info` or `GET /object_info/{class}` | Optional class path | node input/output metadata | Missing class | Validate workflow against installed nodes |

Current ComfyUI source also adds `/api` aliases for routes. The unprefixed endpoints above are the native examples and are recommended for local automation unless the project standardizes on `/api`.

## Submission Flow

```python
client_id = uuid4()
workflow = load_json("workflow_api.json")
manifest = load_json("workflow_manifest.json")

patch(workflow, manifest["positive_prompt"], prompt)
patch(workflow, manifest["negative_prompt"], negative_prompt)
patch(workflow, manifest["seed"], seed)
patch(workflow, manifest["width"], width)
patch(workflow, manifest["height"], height)
patch(workflow, manifest["frames"], frames)
patch(workflow, manifest["steps"], steps)
patch(workflow, manifest["guidance"], guidance)
patch_model_nodes(workflow, model_selection)
patch_lora_nodes(workflow, lora_stack)
patch(workflow, manifest["output_prefix"], output_prefix)

validate_against_manifest(workflow, manifest)
validate_against_object_info(workflow, comfy_base_url)
snapshot_workflow(run_id, workflow)

ws = connect(f"ws://127.0.0.1:8188/ws?clientId={client_id}")
prompt_id = post_json("/prompt", {"prompt": workflow, "client_id": client_id})["prompt_id"]

for event in ws:
    persist_event(prompt_id, event)
    if event["type"] == "execution_error":
        mark_failed(prompt_id, event)
        break
    if event["type"] == "executing" and event["data"].get("node") is None:
        history = get_json(f"/history/{prompt_id}")
        outputs = extract_outputs(history[prompt_id])
        persist_outputs(outputs)
        mark_complete(prompt_id)
        break
```

## Error Handling Rules

- Treat `node_errors` on `/prompt` as a validation failure, not a runtime failure.
- Treat WebSocket `execution_error` as authoritative runtime failure.
- If WebSocket disconnects, poll `/history/{prompt_id}` with backoff before declaring failure.
- If history remains empty after timeout, inspect `/queue` and process health.
- If the current job is hung and GPU utilization is flat, use `/interrupt`; if VRAM does not recover, restart the ComfyUI worker process.

## Output Discovery

The backend must persist both:

1. ComfyUI history output metadata.
2. Actual file paths and SHA256 hashes after retrieval or local filesystem discovery.

Do not infer output names from prompt alone. Many save nodes add counters, subfolders, and extensions.

## API Stability Notes

- Workflow API JSON is not the same as the UI graph JSON.
- Node IDs are workflow-local and may change when a workflow is edited/exported.
- Custom nodes may change input field names across versions.
- Store exported API JSON snapshots per generation.
- Store ComfyUI commit, custom node commits, Python version, torch/CUDA stack, and model file hashes.
