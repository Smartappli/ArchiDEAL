[CmdletBinding()]
param(
    [ValidateSet("all", "core", "gps", "sensor")]
    [string]$Layer = "all",
    [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found at $python. Create .venv first."
}

function Invoke-ValidationCommand {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Validation command failed: $python $($Arguments -join ' ')"
    }
}

$layers = @(
    @{ Name = "core"; Directory = "core_layer"; Settings = "core.settings" },
    @{ Name = "gps"; Directory = "gps_layer"; Settings = "gps.settings" },
    @{ Name = "sensor"; Directory = "sensor_layer"; Settings = "sensor.settings" }
)

if ($Layer -ne "all") {
    $layers = $layers | Where-Object { $_.Name -eq $Layer }
}

Push-Location $repositoryRoot
try {
    if (-not $SkipCompile) {
        $compileTargets = @($layers | ForEach-Object { $_.Directory })
        Invoke-ValidationCommand -Arguments (
            @("-m", "compileall", "-q") + $compileTargets
        )
    }

    foreach ($service in $layers) {
        Push-Location (Join-Path $repositoryRoot $service.Directory)
        try {
            Invoke-ValidationCommand -Arguments @("manage.py", "check")
            Invoke-ValidationCommand -Arguments @(
                "manage.py",
                "makemigrations",
                "--check",
                "--dry-run"
            )
            Invoke-ValidationCommand -Arguments @(
                "-m",
                "pytest",
                ".",
                "--ds=$($service.Settings)",
                "-q"
            )
        }
        finally {
            Pop-Location
        }
    }
}
finally {
    Pop-Location
}

Write-Host "Validation completed for: $Layer"
