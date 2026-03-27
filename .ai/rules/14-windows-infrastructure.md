---
description: Windows Server / Hyper-V and PowerShell infrastructure gotchas
---

# Windows Infrastructure Gotchas

## SSH Port Forwarding — Use nginx stream, NOT netsh portproxy
`netsh portproxy` is unreliable for SSH. It causes `kex_exchange_identification: Connection reset` errors during the SSH handshake. Always use **nginx stream proxy** for forwarding SSH ports on Windows:

```nginx
stream {
  server {
    listen <external-port>;
    proxy_pass 172.20.0.10:22;
  }
}
```

Run nginx as a service via NSSM. Do not suggest portproxy for SSH forwarding.

## Two Separate Firewalls on the PWP Host
The Windows Server at `profiaa13cl.pwp1.net` has **two independent firewalls**:
1. Windows Firewall (`netsh advfirewall`) — configured on the server
2. PWP network-level firewall — configured in the hosting provider's control panel

A port that is open in Windows Firewall will still time out if it hasn't been opened in the PWP panel. When a new port is added, both must be updated.

## RRAS Conflicts with WinNAT
Installing `Install-WindowsFeature -Name Routing` (RRAS) **breaks** `New-NetNat` / `Add-NetNatStaticMapping`. They are two separate NAT implementations and cannot coexist. The Hyper-V VM's NAT uses WinNAT — do not install the Routing feature.

## IIS SSL Certificate Binding
`(Get-WebBinding).AddSslCertificate()` in PowerShell is unreliable for SNI bindings and throws `0x80070520`. Use `netsh` instead:

```powershell
netsh http add sslcert hostnameport=nuera.digital:443 certhash=<thumbprint> appid='{any-valid-guid}' certstorename=MY
```

## Debian Minimal Install
Debian netinstall does not include `curl` or `sudo`. When running setup commands on the VM:
- Install curl first: `apt install curl -y`
- Drop `sudo` — run as root directly during initial setup

## Spec Sync — Document Infrastructure Changes in the Same Commit
When any of the following change, update the relevant documentation (deployment specs, `PROJECT_SUMMARY.md`, or inline comments) **in the same commit** as the implementation:
- Architecture changes (networking path, SSL termination, proxy layer)
- Secret/variable names or scoping
- New automation scripts
- VM OS, platform, or static IP config
- GitHub Actions workflow steps

Do not leave documentation catchup for a separate session.

## `mail` Exit Code in Non-Interactive SSH Sessions
`mailutils mail` exits non-zero in non-interactive SSH sessions even when the email sends successfully (it only exits 0 when reading from a real TTY). Never use `command -v mail && ... | mail ... && echo 'sent' || echo 'no-mail'` — the `|| no-mail` branch fires on a successful send. Use `if/then/else` to separate the existence check from the send:

```bash
if command -v mail > /dev/null 2>&1; then
  echo 'body' | mail -s 'subject' "$ADDR" 2>/dev/null
  echo 'sent'
else
  echo 'no-mail'
fi
```

## GitHub Actions Conventions

### Environment-scoped secrets: use the same name in both environments
When a secret differs between staging and production (e.g. database URL), set it as an **environment-scoped** secret with the **same name** in each environment (`DB_URL` in both `staging` and `production`). Do NOT use `STAGING_X` / `PROD_X` naming — it's redundant when the job already has `environment:` set and the correct value resolves automatically.

Repo-level secrets (same value for all environments, e.g. `SERVER_HOST`, `SERVER_SSH_KEY`) stay at repo level with no environment prefix.

## PowerShell Script Conventions (deploy scripts)

### No non-ASCII characters in string literals
Em dashes (`—`), section signs (`§`), and other Unicode characters in PS string literals cause parser errors when the file is saved with the wrong encoding. Use plain ASCII equivalents (`-`, `s.`) instead.

### plink variable scoping — always use `$script:` prefix
When plink/pscp helpers are defined as PS functions, the script-level params (`$KeyFile`, `$VmPort`, `$WinUser`, etc.) are not automatically in function scope. Array splatting also breaks. Always reference them with the `$script:` prefix inside helper functions:
```powershell
function Ssh-Run([string]$cmd) {
    & plink -batch -agent -P $script:VmPort "$($script:VmUser)@$($script:VmHost)" $cmd
}
```

### Remote PowerShell via plink — use EncodedCommand
Passing complex PS commands through SSH quoting is fragile. Encode as UTF-16LE base64 and use `-EncodedCommand`:
```powershell
$bytes   = [System.Text.Encoding]::Unicode.GetBytes($cmd)
$encoded = [Convert]::ToBase64String($bytes)
& plink ... "powershell.exe -NonInteractive -EncodedCommand $encoded"
```

### Strip CLIXML from captured remote PS output
PowerShell remote output includes `#< CLIXML` serialization headers. Always strip before parsing:
```powershell
function Parse-Output([string[]]$lines) {
    $clean = $lines | Where-Object { $_ -notmatch "^#< CLIXML" -and $_.Trim() -ne "" -and $_ -notmatch "^<Objs" }
    return ($clean | Select-Object -Last 1).Trim()
}
```

### Read-Host path inputs include surrounding quotes
When a user pastes a file path into a `Read-Host` prompt on Windows (e.g. from Explorer's address bar or tab-completion), PowerShell includes the literal `"` characters in the returned string. Always strip them before calling `Test-Path` or `Get-Content`:
```powershell
$path = (Read-Host "Enter file path").Trim().Trim('"').Trim("'")
```

### `$host` is a reserved PowerShell variable
Never use `$host` as a variable name — it shadows the built-in `$host` automatic variable and throws a read-only error. Use `$siteHost`, `$winHost`, etc. instead.

### AutomaticStartDelay is Int32, not TimeSpan (Windows Server 2019 Hyper-V)
`(Get-VM).AutomaticStartDelay` returns an `Int32` (seconds) on Windows Server 2019 — it is NOT a `TimeSpan`. Calling `.TotalSeconds` on it returns null, silently breaking comparisons. Compare the value directly:
```powershell
$v.AutomaticStartDelay -eq 30   # correct
$v.AutomaticStartDelay.TotalSeconds -eq 30   # WRONG — always null
```

### Prefer remote-side comparison for pipe-split outputs
When fetching multiple VM properties via pipe-separated remote output, null values concatenate to empty strings, shifting all subsequent fields and breaking parsing. For simple pass/fail checks, do the comparison on the remote side and return a single `OK`/`WRONG` token. For display purposes (showing per-property values), pipe-split is fine when the properties are guaranteed non-null (e.g., enum values, integers).
