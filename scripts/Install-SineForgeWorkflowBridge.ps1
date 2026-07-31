[CmdletBinding()]
param(
    [string]$CustomNodesPath = "C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourcePath = (Resolve-Path (
    Join-Path $repositoryRoot "ComfyUI\sineforge_workflow_bridge"
)).Path
$customNodesRoot = (Resolve-Path -LiteralPath $CustomNodesPath).Path
$targetPath = Join-Path $customNodesRoot "SineForge-Workflow-Bridge"

if (Test-Path -LiteralPath $targetPath) {
    $existing = Get-Item -LiteralPath $targetPath -Force
    $targets = @($existing.Target | ForEach-Object {
        if ($_ -is [string] -and $_) {
            [System.IO.Path]::GetFullPath($_)
        }
    })
    if (
        ($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -and
        ($targets -contains [System.IO.Path]::GetFullPath($sourcePath))
    ) {
        Write-Output "SineForge workflow bridge is already installed: $targetPath"
        exit 0
    }
    throw "Refusing to overwrite the existing custom-node path: $targetPath"
}

New-Item -ItemType Junction -Path $targetPath -Target $sourcePath | Out-Null
Write-Output "Installed SineForge workflow bridge: $targetPath -> $sourcePath"
Write-Output "Restart ComfyUI once so it can register the bridge."
