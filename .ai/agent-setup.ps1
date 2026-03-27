<#
================================================================================
 Agent Configuration Script (Agent-Agnostic, Declarative Architecture)
================================================================================

This script configures AI agent folders (e.g., .claude, .copilot, .openai)
based on a shared `.ai` directory at the project root.

PROJECT STRUCTURE EXPECTED:
    <project_root>/
        .ai/
            rules/
            workflows/
        .claude/          <- agent folder (must exist to be configured)
        configure.ps1     <- this script

DESIGN PRINCIPLES:
--------------------------------------------------------------------------------
1. Agent behavior is defined declaratively in $AgentConfigs.
   No agent-specific logic is hard-coded in functions.

2. Each agent config defines:
   - Which folders to create
   - Whether each folder should be cleared on each run
   - Whether the agent needs a rules junction
   - Whether the agent needs a symlink from AGENTS.md to <AgentName>.md

3. RULES SETUP:
   - If <agent>/rules does not exist, create a directory junction:
         <agent>/rules -> <project_root>/.ai/rules

4. WORKFLOW SETUP:
   - For each workflow in .ai/workflows/*.md:
         <agent>/commands/<workflow>.md        (flat file, enables /name shorthand)
     Created as symbolic links.

5. AGENT DOC SETUP:
   - If configured, create:
         CLAUDE.md -> AGENTS.md

6. Adding a new agent requires ONLY adding a new entry to $AgentConfigs.
================================================================================
#>

# -----------------------------
# Agent Configuration (Declarative)
# -----------------------------
$AgentConfigs = @{
    ".claude" = @{
        Folders = @(
            @{ Name = "commands"; Clear = $true }
        )
        NeedsRulesLink    = $true
        NeedsAgentMdLink  = $true
    }
}

# -----------------------------
# Utility: Create Directory Junction
# -----------------------------
function New-DirectoryJunction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    if (-not (Test-Path $LinkPath)) {
        Write-Host "Creating directory junction: $LinkPath -> $TargetPath" -ForegroundColor Cyan
        cmd /c "mklink /J `"$LinkPath`" `"$TargetPath`""
    }
}

# -----------------------------
# Utility: Create Symbolic Link to File
# -----------------------------
function New-FileSymlink {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )

    Write-Host "Creating symlink: $LinkPath -> $TargetPath" -ForegroundColor DarkGray
    cmd /c "mklink `"$LinkPath`" `"$TargetPath`""
}

# -----------------------------
# Prepare Agent Folders (Declarative)
# -----------------------------
function Prepare-AgentFolders {
    param(
        [string]$AgentRoot,
        [array]$FolderConfig
    )

    $result = @{}

    foreach ($folder in $FolderConfig) {
        $path = Join-Path $AgentRoot $folder.Name

        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Force -Path $path | Out-Null
        }
        elseif ($folder.Clear) {
            Get-ChildItem $path | Remove-Item -Recurse -Force
        }

        $result[$folder.Name] = $path
    }

    return $result
}

# -----------------------------
# Sync Workflows into Agent
# -----------------------------
function Sync-Workflows {
    param(
        [string]$DestinationDir,
        [string]$WorkflowSourceDir
    )

    $workflows = Get-ChildItem -Path $WorkflowSourceDir -Filter "*.md"

    foreach ($file in $workflows) {
        $name = $file.BaseName

        $commandFile = Join-Path $DestinationDir "$name.md"
        New-FileSymlink -LinkPath $commandFile -TargetPath $file.FullName

        Write-Host "Synced workflow: $name" -ForegroundColor Green
    }
}

# -----------------------------
# Ensure Rules Junction Exists
# -----------------------------
function Ensure-RulesLink {
    param(
        [string]$AgentRoot,
        [string]$ProjectRoot
    )

    $agentRules  = Join-Path $AgentRoot "rules"
    $sourceRules = Join-Path $ProjectRoot ".ai\rules"

    if (-not (Test-Path $agentRules)) {
        New-DirectoryJunction -LinkPath $agentRules -TargetPath $sourceRules
    }
}

# -----------------------------
# Ensure Agent Markdown Symlink Exists
# -----------------------------
function Ensure-AgentMdLink {
    param(
        [string]$ProjectRoot,
        [string]$AgentFolderName
    )

    $agentName = $AgentFolderName.TrimStart(".")
    $linkPath = Join-Path $ProjectRoot "$($agentName.ToUpper()).md"
    $target    = Join-Path $ProjectRoot "AGENTS.md"

    if (-not (Test-Path $linkPath)) {
        Write-Host "Creating agent doc symlink: $linkPath -> $target" -ForegroundColor Cyan
        cmd /c "mklink `"$linkPath`" `"$target`""
    }
}

# -----------------------------
# MAIN ENTRY FUNCTION
# -----------------------------
function ConfigureAgent {
    param(
        [string]$AgentFolderName
    )

    if (-not $AgentConfigs.ContainsKey($AgentFolderName)) {
        Write-Host "No configuration found for $AgentFolderName -- skipping." -ForegroundColor Yellow
        return
    }

    $ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    $AgentRoot   = Join-Path $ProjectRoot $AgentFolderName
    $WorkflowSourceDir = Join-Path $ProjectRoot ".ai\workflows"
    $config = $AgentConfigs[$AgentFolderName]

    if (-not (Test-Path $AgentRoot)) {
        Write-Host "Skipping $AgentFolderName (folder does not exist)." -ForegroundColor Yellow
        return
    }

    Write-Host "`nConfiguring agent: $AgentFolderName" -ForegroundColor Cyan

    if ($config.NeedsRulesLink) {
        Ensure-RulesLink -AgentRoot $AgentRoot -ProjectRoot $ProjectRoot
    }

    if ($config.NeedsAgentMdLink) {
        Ensure-AgentMdLink -ProjectRoot $ProjectRoot -AgentFolderName $AgentFolderName
    }

    $folders = Prepare-AgentFolders -AgentRoot $AgentRoot -FolderConfig $config.Folders

    Sync-Workflows `
        -DestinationDir $folders["commands"] `
        -WorkflowSourceDir $WorkflowSourceDir

    Write-Host "Completed configuration for $AgentFolderName" -ForegroundColor Cyan
}

# -----------------------------
# DEFAULT CALLS (edit as needed)
# -----------------------------
ConfigureAgent ".claude"
