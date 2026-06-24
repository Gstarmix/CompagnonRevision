param(
    [Parameter(Mandatory=$false)]
    [string]$Task = "",
    [Parameter(Mandatory=$false)]
    [string]$ExtraFile = "",
    [Parameter(Mandatory=$false)]
    [switch]$Verbose
)
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = Split-Path -Leaf $ProjectRoot
if ($ProjectName -ne "Compagnon_Revision") {
    Write-Host "ERREUR : ce script doit etre dans la racine de Compagnon_Revision/" `
        -ForegroundColor Red
    Write-Host "Detecte : $ProjectName" -ForegroundColor Red
    exit 1
}
$RequiredFiles = @(
    "CLAUDE.md",
    "_prompts\PROMPT_SYSTEME_COMPAGNON.md"
)
$OptionalFiles = @(
    "ARCHITECTURE.md",
    "README.md"
)
$Missing = @()
foreach ($f in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $ProjectRoot $f))) {
        $Missing += $f
    }
}
if ($Missing.Count -gt 0) {
    Write-Host "ERREUR : fichiers de doctrine manquants :" -ForegroundColor Red
    $Missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host "Reviens vers Claude.ai pour les recuperer." -ForegroundColor Yellow
    exit 1
}
$MissingOptional = @()
foreach ($f in $OptionalFiles) {
    if (-not (Test-Path (Join-Path $ProjectRoot $f))) {
        $MissingOptional += $f
    }
}
if ($MissingOptional.Count -gt 0) {
    Write-Host "AVERTISSEMENT : fichiers de doctrine optionnels absents :" `
        -ForegroundColor Yellow
    $MissingOptional | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "(Normal en debut de Phase A. Continue.)" -ForegroundColor DarkGray
    Write-Host ""
}
$ArsenalPath = Join-Path (Split-Path -Parent $ProjectRoot) "Arsenal_Arguments"
$QuotaScript = Join-Path $ArsenalPath "claude_usage.py"
if (Test-Path $QuotaScript) {
    Write-Host "Verification quota Claude Max 5x..." -ForegroundColor Cyan
    $QuotaOutput = & python $QuotaScript --fetch 2>&1
    $QuotaExitCode = $LASTEXITCODE
    if ($QuotaExitCode -eq 0) {
        Write-Host $QuotaOutput -ForegroundColor DarkGray
        Write-Host ""
    } else {
        Write-Host "Avertissement : le check quota a echoue (cookie expire ?)." `
            -ForegroundColor Yellow
        Write-Host "Pour rafraichir : python `"$QuotaScript`" --set-cookie" `
            -ForegroundColor Yellow
        Write-Host "(On continue quand meme.)" -ForegroundColor DarkGray
        Write-Host ""
    }
} else {
    Write-Host "Module quota Arsenal non trouve a $ArsenalPath - skip." `
        -ForegroundColor DarkGray
    Write-Host ""
}
$ContextFiles = @(
    "CLAUDE.md"
)
if (Test-Path (Join-Path $ProjectRoot "ARCHITECTURE.md")) {
    $ContextFiles += "ARCHITECTURE.md"
}
if ($ExtraFile -ne "") {
    $ExtraFullPath = Join-Path $ProjectRoot $ExtraFile
    if (Test-Path $ExtraFullPath) {
        $ContextFiles += $ExtraFile
    } else {
        Write-Host "AVERTISSEMENT : -ExtraFile $ExtraFile introuvable, ignore." `
            -ForegroundColor Yellow
    }
}
$ContextList = ($ContextFiles | ForEach-Object { "  - $_" }) -join "`n"
$Preamble = @"
Lis les fichiers suivants pour te calibrer :
$ContextList
Mode econome en tokens (cf. CLAUDE.md section 6).
Regles absolues :
- Tu ne touches pas a _prompts/, CLAUDE.md, README.md, ARCHITECTURE.md, CHANGELOG.md
- Tu demandes avant de coder en cas de doute
- Tu codes par bouts, pas 10 fichiers d'un coup
- Tu respectes les conventions de CLAUDE.md section 3
"@
if ($Task -ne "") {
    $Preamble += "`n`nTache de cette session :`n$Task"
} else {
    $Preamble += "`n`n(Aucune tache fournie. Je decrirai la tache apres ton recap des fichiers lus.)"
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Compagnon_Revision - Demarrage session Claude Code" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Repertoire   : $ProjectRoot" -ForegroundColor White
Write-Host "Fichiers contexte :" -ForegroundColor White
$ContextFiles | ForEach-Object { Write-Host "  - $_" -ForegroundColor DarkGray }
if ($Task -ne "") {
    Write-Host ""
    Write-Host "Tache         : $Task" -ForegroundColor White
}
Write-Host ""
if ($Verbose) {
    Write-Host "--- Preambule envoye a Claude Code ---" -ForegroundColor Yellow
    Write-Host $Preamble -ForegroundColor DarkGray
    Write-Host "--- Fin du preambule ---" -ForegroundColor Yellow
    Write-Host ""
}
$ClaudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $ClaudeCmd) {
    Write-Host "ERREUR : commande `claude` introuvable dans le PATH." -ForegroundColor Red
    Write-Host "Installe Claude Code CLI ou ajoute-le au PATH." -ForegroundColor Yellow
    exit 1
}
$EnginePref = "cli_subscription"
$EnginePrefFile = Join-Path $ProjectRoot "_secrets\engine_pref.json"
if (Test-Path $EnginePrefFile) {
    try {
        $EnginePrefData = Get-Content $EnginePrefFile -Raw | ConvertFrom-Json
        if ($EnginePrefData.engine) {
            $EnginePref = $EnginePrefData.engine
        }
    } catch {
        Write-Host "Avertissement : engine_pref.json malforme, on utilise cli_subscription par defaut." `
            -ForegroundColor Yellow
    }
}
if ($EnginePref -eq "cli_subscription") {
    if ($env:ANTHROPIC_API_KEY) {
        Write-Host "Mode CLI subscription : ANTHROPIC_API_KEY temporairement masquee." `
            -ForegroundColor DarkGray
        $env:ANTHROPIC_API_KEY = $null
    }
} else {
    Write-Host "Mode API Anthropic actif (engine_pref.json)." -ForegroundColor Yellow
    if (-not $env:ANTHROPIC_API_KEY) {
        Write-Host "ERREUR : engine=api_anthropic mais ANTHROPIC_API_KEY absente de l'env." `
            -ForegroundColor Red
        exit 1
    }
}
Set-Location $ProjectRoot
Write-Host "Lancement de Claude Code..." -ForegroundColor Green
Write-Host "(Le preambule sera envoye comme premier message.)" -ForegroundColor DarkGray
Write-Host ""
try {
    & claude -p $Preamble
} catch {
    Write-Host "Injection directe echouee, fallback presse-papier..." -ForegroundColor Yellow
    $Preamble | Set-Clipboard
    Write-Host "Preambule copie dans le presse-papier. Colle-le dans Claude Code (Ctrl+V)." `
        -ForegroundColor Cyan
    & claude
}