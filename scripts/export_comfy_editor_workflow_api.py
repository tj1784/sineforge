"""Export a ComfyUI editor graph to API-format JSON using live node definitions.

This is intentionally a static export: it never submits or queues the workflow.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}
INACTIVE_MODES = {2, 4}  # LiteGraph NEVER and BYPASS.
FRONTEND_ONLY_TYPES = {"MarkdownNote"}


def _node_definitions(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def _is_widget(spec: object) -> bool:
    if not isinstance(spec, list) or not spec:
        return False
    input_type = spec[0]
    options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if options.get("forceInput") is True:
        return False
    if isinstance(input_type, list):
        return True
    return bool(options.get("widgetType")) or input_type in WIDGET_TYPES


def _widget_names(node_definition: dict[str, Any]) -> list[str]:
    names: list[str] = []
    input_groups = node_definition.get("input") or {}
    for group in ("required", "optional"):
        for name, spec in (input_groups.get(group) or {}).items():
            if _is_widget(spec):
                names.append(name)
    return names


def convert(editor_graph: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in editor_graph.get("nodes", []) if isinstance(node, dict)]
    active_ids = {
        str(node["id"])
        for node in nodes
        if node.get("id") is not None and node.get("mode", 0) not in INACTIVE_MODES
    }
    links = {
        int(link[0]): link
        for link in editor_graph.get("links", [])
        if isinstance(link, list) and len(link) >= 6
    }
    output: dict[str, Any] = {}

    for node in nodes:
        node_id = str(node.get("id"))
        if node_id not in active_ids:
            continue
        class_type = str(node.get("type") or "")
        if class_type in FRONTEND_ONLY_TYPES:
            continue
        definition = definitions.get(class_type)
        if not isinstance(definition, dict):
            raise ValueError(f"Node {node_id} uses unavailable class {class_type!r}")

        inputs: dict[str, Any] = {}
        values = node.get("widgets_values") or []
        if isinstance(values, dict):
            inputs.update(values)
        elif isinstance(values, list):
            for name, value in zip(_widget_names(definition), values, strict=False):
                inputs[name] = value

        for input_slot in node.get("inputs") or []:
            if not isinstance(input_slot, dict) or input_slot.get("link") is None:
                continue
            link = links.get(int(input_slot["link"]))
            if link is None:
                raise ValueError(
                    f"Node {node_id} input {input_slot.get('name')!r} references a missing link"
                )
            origin_id = str(link[1])
            if origin_id not in active_ids:
                inputs.pop(str(input_slot.get("name")), None)
                continue
            inputs[str(input_slot["name"])] = [origin_id, int(link[2])]

        output[node_id] = {
            "inputs": inputs,
            "class_type": class_type,
            "_meta": {"title": str(node.get("title") or class_type)},
        }

    if not output:
        raise ValueError("The editor workflow contains no executable nodes")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--object-info-url",
        default="http://127.0.0.1:8190/object_info",
        help="Live ComfyUI object_info endpoint used to map widget names.",
    )
    args = parser.parse_args()

    editor_graph = json.loads(args.source.read_text(encoding="utf-8"))
    api_graph = convert(editor_graph, _node_definitions(args.object_info_url))
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(
        json.dumps(api_graph, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(api_graph)} executable nodes to {args.destination}")


if __name__ == "__main__":
    main()
