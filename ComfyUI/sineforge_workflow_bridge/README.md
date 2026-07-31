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

That node resolves the selected value to one exact LM Studio catalog key,
requires a strict JSON-Schema response, releases cached ComfyUI models before
planning, and uses an outer cleanup guard to unload every LM Studio model
instance before returning anything to an LTX render node. If the complete
loaded-instance set cannot be verified empty, the node fails closed. It never
accepts a cloud URL or API key.

The bundled podcast JSON contract also whitelists the exact planner package
and required GGUF/mmproj files beneath
`C:\Users\Blokey\.lmstudio\models`. Files outside that trusted root are not
accepted for this workflow.

Install it with:

```powershell
.\scripts\Install-SineForgeWorkflowBridge.ps1
```

Restart ComfyUI once after the first installation.
