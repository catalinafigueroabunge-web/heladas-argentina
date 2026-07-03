# =============================================================
# setup_github.ps1 — Configura Git, crea repo en GitHub y
# activa GitHub Pages para el dashboard de heladas.
#
# INSTRUCCIONES:
# 1. Abre PowerShell en C:\Users\s1134058\heladas-argentina
# 2. Ejecuta: .\setup_github.ps1
# 3. El script pausara en el Paso 2 para que te logues en GitHub
# =============================================================

$ErrorActionPreference = "Stop"
$projectDir = "C:\Users\s1134058\heladas-argentina"
$repoName   = "heladas-argentina"
$env:PATH  += ";C:\Users\s1134058\AppData\Local\Programs\gh\bin"

Set-Location $projectDir

Write-Host ""
Write-Host "=============================================="
Write-Host "  Setup GitHub Pages - Dashboard Heladas"
Write-Host "=============================================="

# ── PASO 1: Configurar identidad git ──────────────────────────────────────────
Write-Host ""
Write-Host "[1/6] Configurando identidad git..."

$gitName  = git config --global user.name  2>$null
$gitEmail = git config --global user.email 2>$null

if (-not $gitName) {
    $gitName = Read-Host "  Ingresa tu nombre completo (para los commits)"
    git config --global user.name $gitName
}
if (-not $gitEmail) {
    $gitEmail = Read-Host "  Ingresa tu email de GitHub"
    git config --global user.email $gitEmail
}

Write-Host "  Nombre : $gitName"
Write-Host "  Email  : $gitEmail"
Write-Host "  OK"

# ── PASO 2: Autenticar gh CLI ─────────────────────────────────────────────────
Write-Host ""
Write-Host "[2/6] Autenticando con GitHub..."
Write-Host "  Se abrira el navegador para que inicies sesion en GitHub."
Write-Host "  Segui las instrucciones en pantalla."
Write-Host ""

$authStatus = gh auth status 2>&1
if ($authStatus -match "Logged in") {
    Write-Host "  Ya autenticado. Saltando."
} else {
    gh auth login --web --git-protocol https
}

# Obtener username de GitHub
$GITHUB_USER = gh api user --jq ".login"
Write-Host "  GitHub user: $GITHUB_USER"

# ── PASO 3: Crear repositorio en GitHub ───────────────────────────────────────
Write-Host ""
Write-Host "[3/6] Creando repositorio '$repoName' en GitHub..."

$repoCheck = gh repo view "$GITHUB_USER/$repoName" 2>&1
if ($repoCheck -notmatch "error") {
    Write-Host "  El repo ya existe: https://github.com/$GITHUB_USER/$repoName"
} else {
    gh repo create $repoName --public --description "Dashboard agrometeorológico de heladas - Argentina" --confirm
    Write-Host "  Repo creado: https://github.com/$GITHUB_USER/$repoName"
}

# ── PASO 4: Configurar git remote y primer push ───────────────────────────────
Write-Host ""
Write-Host "[4/6] Configurando remote y haciendo primer push..."

# Configurar remote origin
$remoteUrl = "https://github.com/$GITHUB_USER/$repoName.git"
git remote remove origin 2>$null
git remote add origin $remoteUrl

# Renombrar rama a main si es master
$currentBranch = git branch --show-current
if ($currentBranch -eq "master") {
    git branch -m master main
}

# Hacer el primer commit si hay cambios sin commitear
$status = git status --short
if ($status) {
    Write-Host "  Haciendo commit inicial..."
    git add .gitignore heladas.csv config.py fetch_data.py build_dashboard.py
    git add update_dashboard.py run_update.bat fetch_elevation.py
    git add create_grid.py frost_calculator.py map_generator.py main.py meteoblue_client.py
    git add argentina_boundary.py
    git add docs/
    git add data/grid_elevation.json 2>$null
    git status --short
    git commit -m "Dashboard heladas: setup inicial con GitHub Pages"
}

# Push
Write-Host "  Pusheando a GitHub..."
git push --set-upstream origin main

Write-Host "  Remote: $remoteUrl"
Write-Host "  OK"

# ── PASO 5: Activar GitHub Pages desde docs/ ──────────────────────────────────
Write-Host ""
Write-Host "[5/6] Activando GitHub Pages..."

gh api --method POST "repos/$GITHUB_USER/$repoName/pages" `
    --field "source[branch]=main" `
    --field "source[path]=/docs" 2>&1

# Si ya estaba activado, puede dar error 409 - es OK
Write-Host "  GitHub Pages configurado: docs/ en rama main"
Write-Host "  URL (disponible en ~1 min): https://$GITHUB_USER.github.io/$repoName/"

# ── PASO 6: Verificar ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[6/6] Verificacion final..."

gh repo view "$GITHUB_USER/$repoName" --json name,url,visibility | ConvertFrom-Json | Format-List

$pagesInfo = gh api "repos/$GITHUB_USER/$repoName/pages" 2>&1
Write-Host $pagesInfo

Write-Host ""
Write-Host "=============================================="
Write-Host "  COMPLETADO"
Write-Host "  Dashboard disponible en ~2 minutos en:"
Write-Host "  https://$GITHUB_USER.github.io/$repoName/"
Write-Host "=============================================="
Write-Host ""
Write-Host "Cada domingo a las 21:00, el Task Scheduler actualizara"
Write-Host "los datos y pusheara el nuevo index.html automaticamente."
