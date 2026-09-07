# Phase 0 secrets setup — run this YOURSELF in a PowerShell window.
# Claude never sees the values: input is masked, no fragment of any value is
# ever echoed, and values go straight into your Windows user environment
# (registry, User scope). Stores: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN,
# TELEGRAM_CHAT_ID.
#
# Safe to re-run after Ctrl+C: press Enter at a prompt to keep an already-saved
# value. The script ends with a live test message from your bot to your phone,
# which proves the token, the chat id, and the pairing between them in one shot.

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Read-Secret([string]$Prompt) {
    $sec = Read-Host -Prompt $Prompt -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $v = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
    return $v.Trim()
}

# 401/403 etc. mean the credential is WRONG; 0 means we couldn't reach the API.
function Get-HttpStatus($err) {
    try { return [int]$err.Exception.Response.StatusCode } catch { return 0 }
}

Write-Host "=== Marketplace radar: secrets setup ==="
Write-Host "Paste values at the prompts. Input is hidden; right-click pastes in most terminals."
Write-Host ""

# --- 1. Anthropic API key -------------------------------------------------
$existingKey = [Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')
if ($existingKey) { Write-Host "ANTHROPIC_API_KEY is already saved ($($existingKey.Length) chars)." }
while ($true) {
    $prompt = if ($existingKey) { "Anthropic API key (Enter = keep the saved value)" }
              else { "Anthropic API key (console.anthropic.com/settings/keys -> Create Key)" }
    $key = Read-Secret $prompt
    if (-not $key -and $existingKey) { Write-Host "  Keeping the saved key."; break }
    if ($key -notmatch '^sk-ant-') {
        Write-Host "  That doesn't start with sk-ant- ; please try again."
        continue
    }
    try {
        $null = Invoke-RestMethod -Uri 'https://api.anthropic.com/v1/models' `
            -Headers @{ 'x-api-key' = $key; 'anthropic-version' = '2023-06-01' } -TimeoutSec 20
        Write-Host "  Key verified against the Anthropic API."
    } catch {
        $code = Get-HttpStatus $_
        if ($code -ge 400) {
            Write-Host "  The Anthropic API REJECTED this key (HTTP $code)."
            Write-Host "  The key is wrong or revoked - this is not a network problem. Please re-enter."
            continue
        }
        Write-Host "  Could not reach the Anthropic API ($($_.Exception.Message))."
        $again = Read-Host "  Type r to re-enter, or press Enter to save it unverified"
        if ($again -eq 'r') { continue }
    }
    [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $key, 'User')
    Write-Host "  ANTHROPIC_API_KEY saved ($($key.Length) chars)."
    break
}

# --- 2. Telegram bot token ------------------------------------------------
$existingTok = [Environment]::GetEnvironmentVariable('TELEGRAM_BOT_TOKEN', 'User')
if ($existingTok) { Write-Host "TELEGRAM_BOT_TOKEN is already saved ($($existingTok.Length) chars)." }
$tok = $null
while ($true) {
    $prompt = if ($existingTok) { "Telegram bot token (Enter = keep the saved value)" }
              else { "Telegram bot token (from @BotFather /newbot, looks like 123456:ABC...)" }
    $t = Read-Secret $prompt
    if (-not $t -and $existingTok) { $tok = $existingTok; Write-Host "  Keeping the saved token."; break }
    if ($t -notmatch '^\d+:\S+$') {
        Write-Host "  Expected digits, a colon, then the secret; please try again."
        continue
    }
    try {
        $me = Invoke-RestMethod -Uri "https://api.telegram.org/bot$t/getMe" -TimeoutSec 20
        Write-Host ("  Token verified - your bot is @{0}" -f $me.result.username)
    } catch {
        $code = Get-HttpStatus $_
        if ($code -ge 400) {
            Write-Host "  Telegram REJECTED this token (HTTP $code)."
            Write-Host "  The token is wrong - this is not a network problem. Please re-enter."
            continue
        }
        Write-Host "  Could not reach Telegram ($($_.Exception.Message))."
        $again = Read-Host "  Type r to re-enter, or press Enter to save it unverified"
        if ($again -eq 'r') { continue }
    }
    [Environment]::SetEnvironmentVariable('TELEGRAM_BOT_TOKEN', $t, 'User')
    Write-Host "  TELEGRAM_BOT_TOKEN saved ($($t.Length) chars)."
    $tok = $t
    break
}

# --- 3. Chat id (an identifier, not a secret) -----------------------------
$chatId = [Environment]::GetEnvironmentVariable('TELEGRAM_CHAT_ID', 'User')
Write-Host ""
if ($chatId) {
    Write-Host "TELEGRAM_CHAT_ID is already saved: $chatId"
    $r = Read-Host "Press Enter to use it, or type n to re-discover it from your bot's messages"
    if ($r -eq 'n') { $chatId = $null }
}
if (-not $chatId) {
    Write-Host "Send any message (e.g. 'hi') to YOUR new bot in Telegram now."
    for ($i = 0; $i -lt 12 -and -not $chatId; $i++) {
        Read-Host "Press Enter AFTER you've messaged the bot" | Out-Null
        try {
            $updates = Invoke-RestMethod -Uri "https://api.telegram.org/bot$tok/getUpdates" -TimeoutSec 20
            # Private chats only — a reused bot may carry group or third-party
            # messages, and blindly taking the newest chat id would route every
            # future deal-approval card to a stranger.
            $private = @($updates.result | Where-Object {
                $_.PSObject.Properties['message'] -and $_.message.chat.type -eq 'private'
            })
            if ($private.Count -gt 0) {
                $c = $private[-1].message.chat
                Write-Host ("  Newest private chat: {0} @{1} (id {2})" -f $c.first_name, $c.username, $c.id)
                $ok = Read-Host "  Is that you? Enter = yes, n = no"
                if ($ok -ne 'n') { $chatId = $c.id }
            }
        } catch {
            Write-Host "  getUpdates failed: $($_.Exception.Message)"
            if ((Get-HttpStatus $_) -eq 401) {
                Write-Host "  A 401 here means your BOT TOKEN is wrong - re-run this script and re-enter it."
            }
        }
        if (-not $chatId) { Write-Host "  Not confirmed yet - message the bot, then press Enter again." }
    }
}
if (-not $chatId) {
    Write-Host "Could not determine your chat id. Get it from @userinfobot, then re-run this script."
    exit 1
}

# --- 4. End-to-end proof: the bot messages YOU ----------------------------
Write-Host ""
Write-Host "Final check: your bot will now send YOU a test message."
Write-Host "(Bots can only message people who messaged them first - if you haven't sent"
Write-Host " your new bot anything yet, do that now.)"
Read-Host "Press Enter to send the test" | Out-Null
try {
    $null = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$tok/sendMessage" `
        -Body @{ chat_id = $chatId; text = 'Marketplace radar: test message. If you can read this, notifications are wired correctly.' } `
        -TimeoutSec 20
} catch {
    $code = Get-HttpStatus $_
    Write-Host "sendMessage failed: $($_.Exception.Message)"
    if ($code -eq 401) { Write-Host "Your BOT TOKEN is wrong - re-run this script and re-enter it." }
    elseif ($code -eq 400) {
        Write-Host "Telegram rejected the chat id - it is likely wrong, or you haven't messaged"
        Write-Host "this bot yet (bots cannot start conversations). Fix that and re-run."
    }
    exit 1
}
$got = Read-Host "Did the test message arrive in YOUR Telegram? Enter = yes, n = no"
if ($got -eq 'n') {
    Write-Host "Then this chat id points somewhere else. Re-run this script and answer n at the"
    Write-Host "chat-id prompt to re-discover it, or get your id from @userinfobot."
    exit 1
}
[Environment]::SetEnvironmentVariable('TELEGRAM_CHAT_ID', "$chatId", 'User')
Write-Host ""
Write-Host "All three values saved, and the notification pipeline is proven working."
Write-Host "Tell Claude 'go' and it will launch the radar."
