# SineForge workflow bridge

This loopback-only ComfyUI extension lets SineForge open a repository workflow
on the ComfyUI canvas. The transfer bridge never queues a prompt.

The bridge accepts editor-format workflow JSON only from loopback clients,
stores at most 32 one-time transfers in memory, expires them after five
minutes, and consumes each token the first time the ComfyUI browser requests
it.

It also registers one local planning node:

```text
SineForge · Local Qwen Podcast JSON
```

That node calls the exact local LM Studio model selected in the workflow,
requires a strict JSON-Schema response, releases cached ComfyUI models before
planning, and confirms that LM Studio unloaded Qwen before returning anything
to an LTX render node. It never accepts a cloud URL or API key.

Install it with:

```powershell
.\scripts\Install-SineForgeWorkflowBridge.ps1
```

Restart ComfyUI once after the first installation.
