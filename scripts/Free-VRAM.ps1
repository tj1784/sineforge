$ErrorActionPreference = "Continue"

Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue

function Write-Status {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}

function Confirm-FreeVram {
    $message = @"
This will unload LM Studio models, ask ComfyUI to free cached models, and stop known GPU model-holder processes.

Continue?
"@

    try {
        $result = [System.Windows.MessageBox]::Show(
            $message,
            "Free VRAM?",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Warning
        )
        return $result -eq [System.Windows.MessageBoxResult]::Yes
    } catch {
        $answer = Read-Host "Free VRAM now? Type YES to continue"
        return $answer -eq "YES"
    }
}

function Invoke-ComfyFree {
    param([int[]]$Ports = @(8888, 8889, 8188))

    $payload = @{ unload_models = $true; free_memory = $true } | ConvertTo-Json -Compress
    foreach ($port in $Ports) {
        try {
            Invoke-RestMethod `
                -Uri "http://127.0.0.1:$port/free" `
                -Method Post `
                -Body $payload `
                -ContentType "application/json" `
                -TimeoutSec 6 `
                | Out-Null
            Write-Status "ComfyUI on port $port accepted /free."
        } catch {
            Write-Status "ComfyUI on port $port is not reachable or did not respond."
        }
    }
}

function Invoke-LmStudioUnload {
    $lms = Get-Command lms -ErrorAction SilentlyContinue
    if (-not $lms) {
        Write-Status "LM Studio CLI 'lms' was not found on PATH."
        return
    }

    try {
        & $lms.Source unload --all
        Write-Status "LM Studio unload --all completed."
    } catch {
        Write-Status "LM Studio unload --all failed: $($_.Exception.Message)"
    }
}

function Get-GpuComputePids {
    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidia) {
        return @()
    }

    $lines = & $nvidia.Source --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>$null
    $pids = @()
    foreach ($line in $lines) {
        if ($line -match "^\s*(\d+),") {
            $pids += [int]$Matches[1]
        }
    }
    return $pids | Select-Object -Unique
}

function Stop-KnownGpuModelHolders {
    $pids = Get-GpuComputePids
    foreach ($pid in $pids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction SilentlyContinue
        if (-not $proc) {
            continue
        }

        $name = [string]$proc.Name
        $commandLine = [string]$proc.CommandLine
        $exePath = [string]$proc.ExecutablePath

        $isLmStudioGpuHelper = $name -eq "LM Studio.exe" -and $commandLine -like "*--type=gpu-process*"
        $isLmStudioLlamaServer = $name -eq "llama-server.exe" -and $exePath -like "*\.lmstudio\extensions\backends\*"
        $isComfyPython =
            $name -in @("python.exe", "pythonw.exe") -and (
                $commandLine -like "*ComfyUI\main.py*" -or
                $commandLine -like "*main.py*--windows-standalone-build*" -or
                $exePath -like "*\ComfyUI\*"
            )

        if ($isLmStudioGpuHelper -or $isLmStudioLlamaServer -or $isComfyPython) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Status "Stopped GPU holder PID $pid ($name)."
            } catch {
                Write-Status "Could not stop PID $pid ($name): $($_.Exception.Message)"
            }
        } else {
            Write-Status "Left unrelated GPU process alone: PID $pid ($name)."
        }
    }
}

function Show-GpuSummary {
    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidia) {
        Write-Status "nvidia-smi was not found."
        return
    }

    Write-Status "GPU memory summary:"
    & $nvidia.Source --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
    $apps = & $nvidia.Source --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>$null
    if ($apps) {
        Write-Status "Remaining CUDA compute apps:"
        $apps
    } else {
        Write-Status "No CUDA compute apps are holding VRAM."
    }
}

if (-not (Confirm-FreeVram)) {
    Write-Status "Canceled by user. No models were unloaded."
    exit 0
}

Write-Status "Free VRAM started."
Invoke-LmStudioUnload
Invoke-ComfyFree
Start-Sleep -Seconds 2
Stop-KnownGpuModelHolders
Start-Sleep -Seconds 2
Show-GpuSummary
Write-Status "Free VRAM finished."
