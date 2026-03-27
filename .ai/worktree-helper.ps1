# Worktree Helper
# Usage: worktree-helper <command> [name] [options]
#
# Commands:
#   worktree-helper new <n>               Create a worktree and cd into it
#   worktree-helper new <n> -Launch       Create a worktree and start Claude Code
#   worktree-helper new <n> -From dev     Branch from 'dev' instead of 'main'
#   worktree-helper done <n> -m "msg"     Commit, merge to main & clean up
#   worktree-helper list                  List all worktrees
#   worktree-helper remove <n>            Remove a specific worktree
#   worktree-helper clean                 Remove all worktrees
#
# Examples:
#   worktree-helper new move-to-vitest
#   worktree-helper new fix-auth -Launch
#   worktree-helper done move-to-vitest -m "feat: migrate to vitest"
#   worktree-helper list

param(
    [Parameter(Position=0)]
    [ValidateSet("new", "list", "remove", "clean", "done", "help")]
    [string]$Command = "help",

    [Parameter(Position=1)]
    [string]$Name,

    [switch]$Launch,

    [Alias("m")]
    [string]$Message,

    [string]$From = "main"
)

$worktreeDir = "..\worktrees"

switch ($Command) {

    "help" {
        Write-Host ""
        Write-Host "Worktree Helper" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Commands:" -ForegroundColor White
        Write-Host "  worktree-helper new <n>               Create worktree & cd into it"
        Write-Host "  worktree-helper new <n> -Launch       Create worktree & start Claude"
        Write-Host "  worktree-helper new <n> -From dev     Branch from dev instead of main"
        Write-Host "  worktree-helper list                  List all worktrees"
        Write-Host "  worktree-helper remove <n>            Remove a worktree"
        Write-Host "  worktree-helper clean                 Remove all worktrees"
        Write-Host ""
        Write-Host '  worktree-helper done <n> -m "msg"     Commit, merge to main & clean up'
        Write-Host ""
        Write-Host "  The done command does the following:" -ForegroundColor DarkGray
        Write-Host "    1. git add . && git commit    in the worktree" -ForegroundColor DarkGray
        Write-Host "    2. git checkout main          in the main repo" -ForegroundColor DarkGray
        Write-Host "    3. git merge <n>              merge branch into main" -ForegroundColor DarkGray
        Write-Host "    4. git worktree remove        delete the worktree directory" -ForegroundColor DarkGray
        Write-Host "    5. git branch -d <n>          delete the local branch" -ForegroundColor DarkGray
        Write-Host "  Run from the main repo dir, not from inside the worktree." -ForegroundColor DarkGray
        Write-Host "  Stops if commit fails or merge has conflicts." -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  <n> = name you choose, e.g. fix-auth, add-tests, move-to-vitest" -ForegroundColor DarkGray
    }

    "list" {
        git worktree list
    }

    "new" {
        if (-not $Name) {
            Write-Host "Missing name. Usage: worktree-helper new <n>" -ForegroundColor Red
            Write-Host "Example: worktree-helper new fix-auth" -ForegroundColor DarkGray
            return
        }

        $path = Join-Path $worktreeDir $Name

        if (Test-Path $path) {
            Write-Host "Worktree $Name already exists. Entering it." -ForegroundColor Cyan
        } else {
            if (-not (Test-Path $worktreeDir)) {
                New-Item -ItemType Directory -Path $worktreeDir | Out-Null
            }
            git worktree add -b $Name $path $From
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Failed to create worktree." -ForegroundColor Red
                return
            }
            Write-Host "Created worktree $Name from $From" -ForegroundColor Green
        }

        if ($Launch) {
            Push-Location $path
            Write-Host "Launching Claude Code..." -ForegroundColor Cyan
            claude
            Pop-Location
        } else {
            Set-Location $path
            Write-Host "Now in worktree $Name. Run claude to start." -ForegroundColor Cyan
        }
    }

    "remove" {
        if (-not $Name) {
            Write-Host "Missing name. Usage: worktree-helper remove <n>" -ForegroundColor Red
            Write-Host "Tip: run worktree-helper list to see worktree names" -ForegroundColor DarkGray
            return
        }
        $path = Join-Path $worktreeDir $Name
        if (Test-Path $path) {
            git worktree remove $path
            Write-Host "Removed worktree $Name" -ForegroundColor Yellow
        } else {
            Write-Host "Worktree $Name not found at $path" -ForegroundColor Red
            Write-Host "Tip: run worktree-helper list to see worktree names" -ForegroundColor DarkGray
        }
    }

    "clean" {
        $confirm = Read-Host "Remove ALL worktrees in $worktreeDir? (y/n)"
        if ($confirm -eq 'y') {
            git worktree list --porcelain |
                Select-String "^worktree " |
                ForEach-Object { ($_ -replace "^worktree ", "").Trim() } |
                Where-Object { $_ -like "*worktrees*" } |
                ForEach-Object {
                    git worktree remove $_
                    Write-Host "Removed: $_" -ForegroundColor Yellow
                }
            git worktree prune
            Write-Host "Done." -ForegroundColor Green
        }
    }

    "done" {
        if (-not $Name) {
            Write-Host 'Missing name. Usage: worktree-helper done <n> -m "commit message"' -ForegroundColor Red
            return
        }
        if (-not $Message) {
            Write-Host 'Missing commit message. Usage: worktree-helper done <n> -m "commit message"' -ForegroundColor Red
            return
        }

        $path = Join-Path $worktreeDir $Name
        if (-not (Test-Path $path)) {
            Write-Host "Worktree $Name not found at $path" -ForegroundColor Red
            return
        }

        # Get the main repo root (parent of worktrees dir)
        $mainRepo = Resolve-Path (Join-Path $worktreeDir "..")

        # Commit in the worktree
        Write-Host "Committing in $Name..." -ForegroundColor Cyan
        Push-Location $path
        git add .
        git commit -m $Message
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Commit failed (maybe nothing to commit?)" -ForegroundColor Red
            Pop-Location
            return
        }
        Pop-Location

        # Merge into main
        Write-Host "Merging $Name into main..." -ForegroundColor Cyan
        Push-Location $mainRepo
        git checkout main
        git merge $Name
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Merge failed. Resolve conflicts in main repo, then run:" -ForegroundColor Red
            Write-Host "  worktree-helper remove $Name" -ForegroundColor DarkGray
            Write-Host "  git branch -d $Name" -ForegroundColor DarkGray
            Pop-Location
            return
        }
        Pop-Location

        # Clean up worktree and branch
        Write-Host "Cleaning up..." -ForegroundColor Cyan
        git worktree remove $path
        git branch -d $Name

        Write-Host "$Name merged to main and cleaned up." -ForegroundColor Green
    }
}