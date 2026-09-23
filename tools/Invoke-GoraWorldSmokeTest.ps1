<#
.SYNOPSIS
Loads the latest Victoria 3 save with an isolated loose-mod profile.

.DESCRIPTION
Preserves content_load.json byte-for-byte, launches Victoria 3 with
-continuelastsave, captures logs, stops only the process it launched, and
restores the original playset in a finally block.
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory = $true)]
	[string] $ProfileName,

	[Parameter(Mandatory = $true)]
	[string[]] $ModRoots,

	[string] $ContinueTitle = '',

	[int] $RunSeconds = 360,

	[string] $GameExe = 'C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\binaries\victoria3.exe',

	[string] $UserDataRoot = 'C:\Users\AvAhm\OneDrive\Belgeler\Paradox Interactive\Victoria 3'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (Get-Process -Name victoria3 -ErrorAction SilentlyContinue) {
	throw 'Victoria 3 is already running.'
}
if ($RunSeconds -lt 40 -or $RunSeconds -gt 600) {
	throw 'RunSeconds must be between 40 and 600.'
}
foreach ($modRoot in $ModRoots) {
	if (-not (Test-Path -LiteralPath $modRoot -PathType Container)) {
		throw "Mod root was not found: $modRoot"
	}
}

$contentLoadPath = Join-Path $UserDataRoot 'content_load.json'
$continueGamePath = Join-Path $UserDataRoot 'continue_game.json'
$logsRoot = Join-Path $UserDataRoot 'logs'
$safeProfile = $ProfileName -replace '[^A-Za-z0-9_.-]', '_'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDirectory = Join-Path $PSScriptRoot "world-smoke-logs\$timestamp-$safeProfile"
$statusPath = Join-Path $PSScriptRoot 'world-smoke-status.json'
$originalContentBytes = [System.IO.File]::ReadAllBytes($contentLoadPath)
$originalContinueBytes = $null
$launchedProcess = $null

function Write-WorldSmokeStatus {
	param(
		[Parameter(Mandatory = $true)][string] $State,
		[string] $Message = ''
	)
	$payload = [ordered]@{
		state = $State
		profile = $ProfileName
		message = $Message
		run_directory = $runDirectory
		updated_at = (Get-Date).ToString('o')
	} | ConvertTo-Json -Depth 3
	[System.IO.File]::WriteAllText(
		$statusPath,
		$payload,
		[System.Text.UTF8Encoding]::new($false)
	)
}

New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
Write-WorldSmokeStatus -State 'preparing' -Message 'Writing isolated mod profile.'

try {
	$enabledMods = foreach ($modRoot in $ModRoots) {
		[ordered]@{ path = $modRoot }
	}
	$isolatedContent = [ordered]@{
		enabledMods = @($enabledMods)
		disabledDLC = @()
		enabledUGC = @()
	} | ConvertTo-Json -Depth 5 -Compress
	[System.IO.File]::WriteAllText(
		$contentLoadPath,
		$isolatedContent,
		[System.Text.UTF8Encoding]::new($false)
	)

	if (-not [string]::IsNullOrWhiteSpace($ContinueTitle)) {
		$originalContinueBytes = [System.IO.File]::ReadAllBytes($continueGamePath)
		$continueData = Get-Content -LiteralPath $continueGamePath -Raw | ConvertFrom-Json
		$continueData.title = $ContinueTitle
		$continueJson = $continueData | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText(
			$continueGamePath,
			$continueJson,
			[System.Text.UTF8Encoding]::new($false)
		)
	}

	Write-WorldSmokeStatus -State 'launching' -Message 'Launching Victoria 3 with Steam ownership context.'
	$env:SteamAppId = '529340'
	$env:SteamGameId = '529340'
	$launchedProcess = Start-Process -FilePath $GameExe `
		-ArgumentList @('-continuelastsave') `
		-WorkingDirectory (Split-Path -Parent $GameExe) `
		-WindowStyle Hidden `
		-PassThru

	Write-WorldSmokeStatus -State 'running' -Message 'Victoria 3 is loading the latest save.'
	$deadline = (Get-Date).AddSeconds($RunSeconds)
	while ((Get-Date) -lt $deadline -and -not $launchedProcess.HasExited) {
		Start-Sleep -Seconds 2
		$launchedProcess.Refresh()
	}

	if (-not $launchedProcess.HasExited) {
		Stop-Process -Id $launchedProcess.Id -Force
		$launchedProcess.WaitForExit(10000) | Out-Null
	}
	Start-Sleep -Seconds 2

	foreach ($logName in @('error.log', 'game.log', 'gui.log', 'system.log', 'setup.log', 'debug.log')) {
		$source = Join-Path $logsRoot $logName
		if (Test-Path -LiteralPath $source -PathType Leaf) {
			Copy-Item -LiteralPath $source -Destination (Join-Path $runDirectory $logName)
		}
	}

	$findings = [System.Collections.Generic.List[string]]::new()
	foreach ($logName in @('error.log', 'game.log', 'gui.log', 'debug.log')) {
		$logPath = Join-Path $runDirectory $logName
		if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
			continue
		}
		foreach ($line in [System.IO.File]::ReadLines($logPath)) {
			if ($line -match 'Invalid owner for scope type|Malformed formatting tag.*tooltip') {
				$findings.Add("[$logName] $line")
			}
		}
	}
	[System.IO.File]::WriteAllLines(
		(Join-Path $runDirectory 'world-runtime-findings.txt'),
		@($findings),
		[System.Text.UTF8Encoding]::new($false)
	)

	Write-Output ([pscustomobject]@{
		Profile = $ProfileName
		RunDirectory = $runDirectory
		RelevantFindings = $findings.Count
	})
	Write-WorldSmokeStatus -State 'completed' -Message "Captured $($findings.Count) relevant finding(s)."
}
catch {
	Write-WorldSmokeStatus -State 'failed' -Message $_.Exception.Message
	throw
}
finally {
	if ($null -ne $launchedProcess) {
		try {
			$launchedProcess.Refresh()
			if (-not $launchedProcess.HasExited) {
				Stop-Process -Id $launchedProcess.Id -Force -ErrorAction SilentlyContinue
			}
		}
		catch {
			# The launched process may already have exited.
		}
	}
	[System.IO.File]::WriteAllBytes($contentLoadPath, $originalContentBytes)
	if ($null -ne $originalContinueBytes) {
		[System.IO.File]::WriteAllBytes($continueGamePath, $originalContinueBytes)
	}
}
