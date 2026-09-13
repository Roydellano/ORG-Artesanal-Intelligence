$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$vite = Join-Path $projectRoot 'web\node_modules\vite\bin\vite.js'
$logDir = Join-Path $projectRoot 'tmp\servers'

try {
    if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $vite)) {
        throw 'Dependencies are missing. Follow the Python and npm setup in README.md first.'
    }
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    & $python -c 'import uvicorn; import forensic_auditor.api' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Backend import failed. Check the Python setup in README.md.' }

    # Validate both listeners before stopping either service. Never kill all Python/Node processes.
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -in @(8000, 5173) })
    $serverIds = @()
    foreach ($listener in $listeners) {
        $server = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        $command = $server.CommandLine
        # Windows venv Python launches a base-runtime child that owns the socket.
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($server.ParentProcessId)"
        $parentIsBackend = $parent -and $parent.CreationDate -le $server.CreationDate -and
            $parent.CommandLine -match 'uvicorn\s+forensic_auditor\.api:app' -and
            $parent.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
        $isBackend = $listener.LocalPort -eq 8000 -and
            $command -match 'uvicorn\s+forensic_auditor\.api:app' -and
            ($command.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $parentIsBackend)
        $isFrontend = $listener.LocalPort -eq 5173 -and
            $command -match 'vite' -and $command -like "*$projectRoot*"
        if (!$isBackend -and !$isFrontend) {
            throw "Port $($listener.LocalPort) belongs to PID $($listener.OwningProcess), which cannot be verified as this project's server. Stop it manually and retry."
        }
        $serverIds += $listener.OwningProcess
        if ($isBackend -and $parentIsBackend) { $serverIds += $parent.ProcessId }
    }
    foreach ($serverId in ($serverIds | Select-Object -Unique)) {
        Write-Host "Stopping server PID $serverId..."
        # The venv wrapper may exit by itself when its child stops.
        $running = Get-Process -Id $serverId -ErrorAction SilentlyContinue
        if ($running) { $running | Stop-Process -Force }
    }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $busy = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -in @(8000, 5173) })
        if (!$busy.Count) { break }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    if ($busy.Count) { throw 'Server ports did not become free. Check for a running reload supervisor.' }

    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    Write-Host 'Starting backend and frontend...'
    $backend = Start-Process -FilePath $python -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -ArgumentList '-m uvicorn forensic_auditor.api:app --host 127.0.0.1 --port 8000' `
        -RedirectStandardOutput (Join-Path $logDir 'backend.log') -RedirectStandardError (Join-Path $logDir 'backend-error.log')
    $frontend = Start-Process -FilePath $node -WorkingDirectory (Join-Path $projectRoot 'web') -WindowStyle Hidden -PassThru `
        -ArgumentList "`"$vite`" --host 127.0.0.1 --port 5173 --strictPort" `
        -RedirectStandardOutput (Join-Path $logDir 'frontend.log') -RedirectStandardError (Join-Path $logDir 'frontend-error.log')

    $deadline = (Get-Date).AddSeconds(30)
    do {
        if ($backend.HasExited -or $frontend.HasExited) { throw "A server exited. See logs in $logDir" }
        try {
            $null = Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2
            $null = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2
            # HTTP readiness alone could belong to an older server after a bind failure.
            $readyListeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
                Where-Object { $_.LocalPort -in @(8000, 5173) })
            foreach ($port in @(8000, 5173)) {
                $launched = if ($port -eq 8000) { $backend } else { $frontend }
                $owned = @($readyListeners | Where-Object {
                    if ($_.LocalPort -ne $port) { return $false }
                    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" -ErrorAction Stop
                    $owner -and ($owner.ProcessId -eq $launched.Id -or
                        ($owner.ParentProcessId -eq $launched.Id -and $owner.CreationDate -ge $launched.StartTime))
                })
                if (!$owned.Count) { throw "Port $port is not owned by the newly launched server." }
            }
            $backend.Refresh()
            $frontend.Refresh()
            if ($backend.HasExited -or $frontend.HasExited) { throw 'A newly launched server exited.' }
            Write-Host 'Ready: http://127.0.0.1:5173'
            Write-Host 'API:   http://127.0.0.1:8000/docs'
            Write-Host "Logs:  $logDir"
            exit 0
        } catch { Start-Sleep -Milliseconds 500 }
    } while ((Get-Date) -lt $deadline)
    throw "Servers did not become ready within 30 seconds. See logs in $logDir"
} catch {
    Write-Host "Restart failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
