[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function AtualizarVersaoPyproject {
    param (
        [string]$version
    )

    $arquivo = "pyproject.toml"

    if (-not (Test-Path $arquivo)) {
        Write-Host "pyproject.toml not found, skipping update."
        return
    }

    $conteudo = Get-Content $arquivo -Raw -Encoding UTF8

    $novoConteudo = $conteudo -replace 'version\s*=\s*".*?"', "version = `"$version`""

    [System.IO.File]::WriteAllText(
        [System.IO.Path]::GetFullPath($arquivo),
        $novoConteudo,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host "Version updated in pyproject.toml to $version"
}

function AtualizarVersaoPackageJson {
    param (
        [string]$version
    )

    $arquivo = "package.json"

    if (-not (Test-Path $arquivo)) {
        Write-Host "package.json not found, skipping update."
        return
    }

    $conteudo = Get-Content $arquivo -Raw -Encoding UTF8

    $novoConteudo = $conteudo -replace '"version"\s*:\s*".*?"', "`"version`": `"$version`""

    [System.IO.File]::WriteAllText(
        [System.IO.Path]::GetFullPath($arquivo),
        $novoConteudo,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host "Version updated in package.json to $version"
}

# Ask commit type
Write-Host "Commit type:"
Write-host "0 - initial commit"
Write-Host "1 - feature"
Write-Host "2 - bugfix"
Write-Host "3 - release"
Write-Host "4 - build"
Write-Host "5 - docs"

$tipoOpcao = Read-Host "Choose an option (0/1/2/3/4/5)"

switch ($tipoOpcao) {
    "0" { $tipo = "initial commit" }
    "1" { $tipo = "feature" }
    "2" { $tipo = "bugfix" }
    "3" { $tipo = "release" }
    "4" { $tipo = "build" }
    "5" { $tipo = "docs" }
    default {
        Write-Host "Invalid option!"
        exit
    }
}

# ===== ESCOLHA DE ARQUIVOS =====
Write-Host "How do you want to add files?"
Write-Host "1 - All (git add .)"
Write-Host "2 - Choose files"

$addOpcao = Read-Host "Choose (1/2)"

if ($addOpcao -eq "1") {
    git add .
}
elseif ($addOpcao -eq "2") {

    Write-Host ""
    Write-Host "Modified files:"
    git status --short

    Write-Host ""
    Write-Host "Enter the files you want to add (separated by space):"
    $arquivos = Read-Host

    git add $arquivos
}
else {
    Write-Host "Invalid option!"
    exit
}

# Commit message
$mensagem = Read-Host "Enter the commit message"

# Principal commit
git commit -m "[$tipo] - $mensagem"

# Asks if you want to generate version
$gerarVersao = Read-Host "Generate version? (y/n)"

if ($gerarVersao -eq "y") {

    # Version type
    Write-Host "Version type:"
    Write-Host "0 - initial version (0.0.1)"
    Write-Host "1 - release (major)"
    Write-Host "2 - feature (minor)"
    Write-Host "3 - bugfix (patch)"

    $versaoTipo = Read-Host "Choose (0/1/2/3)"

    # Get the latest tag
    $ultimaTag = git describe --tags --abbrev=0 2>$null

    if ($versaoTipo -eq "0") {
        $novaVersao = "0.0.1"
    } else {

        if (-not $ultimaTag) {
            $major = 0
            $minor = 0
            $patch = 0
        } else {
            $versao = $ultimaTag.TrimStart("v")
            $partes = $versao.Split(".")

            $major = [int]$partes[0]
            $minor = [int]$partes[1]
            $patch = [int]$partes[2]
        }

        switch ($versaoTipo) {
            "1" {
                $major++
                $minor = 0
                $patch = 0
            }
            "2" {
                $minor++
                $patch = 0
            }
            "3" {
                $patch++
            }
            default {
                Write-Host "Invalid option!"
                exit
            }
        }

        $novaVersao = "$major.$minor.$patch"
    }

    $tag = "v$novaVersao"
    
    AtualizarVersaoPyproject -version $novaVersao
    AtualizarVersaoPackageJson -version $novaVersao

    # ===== CHANGELOG INPUT =====
    Write-Host ""
    Write-Host "Enter the version notes (one per line)."
    Write-Host "Press ENTER with an empty line to finish."

    $notas = @()

    while ($true) {
        $linha = Read-Host "-"

        if ([string]::IsNullOrWhiteSpace($linha)) {
            break
        }

        $notas += "- $linha"
    }

    # ===== CREATE / UPDATE CHANGELOG =====
    $changelogPath = "CHANGELOG.md"

    $conteudoNovaVersao = "## $tag`n`n" + ($notas -join "`n") + "`n`n"

    if (Test-Path $changelogPath) {
        $conteudoAntigo = Get-Content $changelogPath -Raw -Encoding UTF8
        $novoConteudo = $conteudoNovaVersao + $conteudoAntigo
    } else {
        # Create new changelog file with header
        $novoConteudo = "# Changelog`n`n" + $conteudoNovaVersao
    }

    [System.IO.File]::WriteAllText(
        [System.IO.Path]::GetFullPath($changelogPath),
        $novoConteudo,
        [System.Text.UTF8Encoding]::new($false)
    )

    # ===== CHANGELOG COMMIT =====
    git add $changelogPath
    if (Test-Path "pyproject.toml") {
        git add "pyproject.toml"
    }
    if (Test-Path "package.json") {
        git add "package.json"
    }
    git commit -m "CHANGELOG.md atualization for $tag"

    # ===== TAG =====
    git tag $tag
    git push origin $tag
}

# Final push
git push