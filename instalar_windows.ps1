$ErrorActionPreference = "Stop"
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $pasta

function Executar($descricao, [scriptblock]$comando) {
    Write-Host ""
    Write-Host "==> $descricao" -ForegroundColor Cyan
    & $comando
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $descricao" }
}

try {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $python = { py -3 @args }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $python = { python @args }
    } else {
        Write-Host "Python não encontrado." -ForegroundColor Red
        Write-Host "Instale em https://www.python.org/downloads/ marcando 'Add python.exe to PATH' e rode este instalador de novo."
        exit 1
    }

    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Executar "Criando ambiente Python" { & $python -m venv .venv }
    }
    $venv = Join-Path $pasta ".venv\Scripts\python.exe"
    Executar "Instalando dependências" { & $venv -m pip install --upgrade pip -q; & $venv -m pip install -r requirements.txt -q }
    Executar "Instalando o navegador automatizado (Chromium)" { & $venv -m playwright install chromium }

    if (-not (Test-Path ".env")) { Copy-Item ".env.exemplo" ".env" }

    Write-Host ""
    Write-Host "==> Agendando a busca diária às 07:17" -ForegroundColor Cyan
    $acao = New-ScheduledTaskAction -Execute (Join-Path $pasta "rodar_windows.bat") -WorkingDirectory $pasta
    $gatilho = New-ScheduledTaskTrigger -Daily -At "07:17"
    # StartWhenAvailable: se o PC estiver desligado às 07:17, roda assim que for ligado.
    $opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 3)
    Register-ScheduledTask -TaskName "Buscador Smiles" -Action $acao -Trigger $gatilho -Settings $opcoes `
        -Description "Busca diária de passagens em milhas Smiles" -Force | Out-Null

    Write-Host ""
    Write-Host "Pronto! Agora:" -ForegroundColor Green
    Write-Host " 1. No Bloco de Notas que vai abrir, preencha SMTP_USUARIO e SMTP_SENHA e salve."
    Write-Host " 2. Dê dois cliques em 'testar_email_windows.bat' para conferir se o e-mail chega."
    Write-Host " 3. Para buscar agora, dê dois cliques em 'rodar_windows.bat' (o resultado vai para busca.log)."
    Start-Process notepad.exe (Join-Path $pasta ".env")
} catch {
    Write-Host ""
    Write-Host "Erro: $_" -ForegroundColor Red
    exit 1
}
