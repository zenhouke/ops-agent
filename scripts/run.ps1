$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$srcPath = Join-Path $RepoRoot "src"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$env:PYTHONPATH;$srcPath" } else { $srcPath }
# SSLKEYLOGFILE can crash Python/OpenSSL on Windows with "no OPENSSL_Applink".
$env:SSLKEYLOGFILE = ""

$logsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$envPath = Join-Path $RepoRoot ".env"
if (Test-Path $envPath) {
    Write-Host "Loading environment from .env..."
    foreach ($rawLine in Get-Content $envPath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            continue
        }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($null -ne [Environment]::GetEnvironmentVariable($name, "Process")) {
            continue
        }
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

if (-not $env:OPS_AGENT_PORT) {
    $env:OPS_AGENT_PORT = "8000"
}
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$env:OPS_AGENT_PORT"

function Stop-ProcessTree {
    param([int]$ProcessId)
    if ($ProcessId -le 0) {
        return
    }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) {
        return
    }
    try {
        & taskkill.exe /T /F /PID $ProcessId 2>$null 1>$null
    } catch {
        # 进程可能在我们检查后、taskkill 执行前已退出，忽略此类错误
    }
}

function Stop-ListenersOnPort {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $ownerPid = [int]$connection.OwningProcess
        if ($ownerPid -gt 0) {
            Stop-ProcessTree -ProcessId $ownerPid
        }
    }
}

function Get-LiveListenersOnPort {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) { return @() }
    $live = @()
    foreach ($connection in $connections) {
        $ownerPid = [int]$connection.OwningProcess
        if ($ownerPid -le 0) { continue }
        if (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue) {
            $live += $connection
        }
    }
    return ,$live
}

function Wait-PortFree {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $connections = Get-LiveListenersOnPort -Port $Port
        if (-not $connections) {
            return
        }
        Start-Sleep -Milliseconds 250
    }

    $remaining = Get-LiveListenersOnPort -Port $Port
    if ($remaining) {
        $owners = ($remaining | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "Port $Port is still in use after cleanup. OwningProcess: $owners."
    }
}

Write-Host "Stopping processes on ports $env:OPS_AGENT_PORT and 5173..."
Stop-ListenersOnPort -Port ([int]$env:OPS_AGENT_PORT)
Stop-ListenersOnPort -Port 5173
Wait-PortFree -Port ([int]$env:OPS_AGENT_PORT)
Wait-PortFree -Port 5173

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python executable not found. Create .venv or add python to PATH."
    }
    $python = $pythonCommand.Source
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if ($null -eq $npmCommand) {
    throw "npm executable not found. Install Node.js/npm before running the frontend."
}

$backend = $null
$frontend = $null

try {
    Write-Host "Starting Ops Agent Backend..."
    $backend = Start-Process `
        -FilePath $python `
        -ArgumentList @("src\app\main.py") `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput (Join-Path $logsDir "backend.out.log") `
        -RedirectStandardError (Join-Path $logsDir "backend.err.log") `
        -PassThru `
        -WindowStyle Hidden

    Write-Host "Waiting for backend health on http://127.0.0.1:$env:OPS_AGENT_PORT/health..."
    $deadline = (Get-Date).AddSeconds(45)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        if ($backend.HasExited) {
            throw "Backend exited before becoming healthy. See logs\backend.err.log for details."
        }
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$env:OPS_AGENT_PORT/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $healthy) {
        throw "Backend did not become healthy. See logs\backend.err.log for details."
    }

    Write-Host "Starting Ops Agent Frontend..."
    Write-Host "Frontend API proxy target: $env:VITE_API_PROXY_TARGET"
    $frontend = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory (Join-Path $RepoRoot "web") `
        -PassThru `
        -NoNewWindow

    while (-not $frontend.HasExited) {
        Start-Sleep -Milliseconds 250
        $frontend.Refresh()
        if ($backend.HasExited) {
            throw "Backend exited while frontend was running. See logs\backend.err.log for details."
        }
    }
    exit $frontend.ExitCode
} finally {
    Write-Host "Stopping servers..."
    if ($frontend -and -not $frontend.HasExited) {
        Stop-ProcessTree -ProcessId $frontend.Id
    }
    if ($backend -and -not $backend.HasExited) {
        Stop-ProcessTree -ProcessId $backend.Id
    }
    Stop-ListenersOnPort -Port ([int]$env:OPS_AGENT_PORT)
    Stop-ListenersOnPort -Port 5173
}
