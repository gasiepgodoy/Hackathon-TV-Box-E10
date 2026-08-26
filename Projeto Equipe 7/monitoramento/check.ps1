# Coletor de estado do SecBox: TV box (borda) e servidor.
#
# Funciona sem SSH -- ping, portas e os dois endpoints abertos da 9997 ja dizem
# muita coisa. Com a chave instalada, acrescenta uptime, estado dos servicos e
# a contagem de quedas do wifi-guard.
#
# Escreve uma linha JSON por execucao em history.jsonl e imprime um resumo
# legivel. A interpretacao (o que mudou, o que importa) fica com quem le.

$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'

$KEY  = Join-Path $PSScriptRoot 'id_monitor'
$HIST = Join-Path $PSScriptRoot 'history.jsonl'
$CFG  = Join-Path $PSScriptRoot 'config.json'

# Enderecos ficam fora do script: eles sao topologia interna, e este arquivo e
# versionado. Copie config.example.json para config.json e preencha.
if (-not (Test-Path $CFG)) {
    Write-Output "config.json nao encontrado em $PSScriptRoot."
    Write-Output "Copie config.example.json para config.json e preencha os enderecos."
    exit 1
}
$conf = Get-Content $CFG -Raw | ConvertFrom-Json
$BOX  = $conf.box
$SRV  = $conf.servidor
$USR  = $conf.usuario_servidor

function Test-Porta($alvo, $porta) {
    Test-NetConnection -ComputerName $alvo -Port $porta -InformationLevel Quiet -WarningAction SilentlyContinue
}

function Get-Json($url, $token) {
    $h = @{}
    if ($token) { $h['Authorization'] = "Bearer $token" }
    # Duas tentativas: o Wi-Fi da box cai varias vezes por hora, e medindo dava
    # cerca de 1 coleta em 3 perdendo estes dados. Uma repeticao recupera a
    # maioria, e o custo e uma pausa de 3s so quando ja falhou.
    foreach ($tentativa in 1..2) {
        try {
            return (Invoke-WebRequest -Uri $url -TimeoutSec 8 -UseBasicParsing `
                        -Headers $h).Content | ConvertFrom-Json
        } catch {
            if ($tentativa -lt 2) { Start-Sleep -Seconds 3 }
        }
    }
    return $null
}

function Invoke-Remoto($destino, $comando) {
    if (-not (Test-Path $KEY)) { return $null }
    # BatchMode: sem chave valida, falha na hora em vez de pedir senha e travar
    $saida = & ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=8 `
                   -o StrictHostKeyChecking=accept-new $destino $comando 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($saida -join "`n")
}

$e = [ordered]@{ ts = (Get-Date).ToString('s') }

# A 9997 passou a exigir token. Ele vem da propria box por SSH -- assim o
# monitoramento nao guarda copia de credencial em lugar nenhum.
# Sem aspas no comando remoto de proposito: o PowerShell 5.1 mastiga aspas ao
# repassar argumentos para executaveis nativos, e o comando chegava truncado.
# Traz o JSON inteiro e extrai aqui; so o token e guardado.
$cfg = Invoke-Remoto "root@$BOX" "cat /opt/secbox/config.json"
$TOKEN = $null
if ($cfg) { try { $TOKEN = ($cfg | ConvertFrom-Json).api_token } catch { } }
if ($TOKEN) { $TOKEN = $TOKEN.Trim() }

# ---------- TV box ----------
$e.box_ping = [bool](Test-Connection -ComputerName $BOX -Count 2 -Quiet)
$e.box_9997 = [bool](Test-Porta $BOX 9997)   # clip-server
$e.box_8889 = [bool](Test-Porta $BOX 8889)   # WHEP (ao vivo)
$e.box_9996 = [bool](Test-Porta $BOX 9996)   # playback

$saude = Get-Json "http://$BOX`:9997/health"
if ($saude) { $e.box_9997_auth = [bool]$saude.auth }

$cams = Get-Json "http://$BOX`:9997/cameras" $TOKEN
if ($cams) {
    $e.cams_conectadas = [int]$cams.connected
    $e.cams_limite     = [int]$cams.limit
    $e.cams_excedido   = [bool]$cams.exceeded
    $e.cams_nomes      = ($cams.cameras | ForEach-Object { $_.path }) -join ','
}

$st = Get-Json "http://$BOX`:9997/storage" $TOKEN
if ($st) {
    $e.disco_livre_gb = [math]::Round($st.free / 1GB, 1)
    $e.disco_uso_pct  = [math]::Round(100 * $st.used / $st.total)
    $e.gravacao_horas = [math]::Round($st.hours, 1)
    $e.carga          = [double]$st.load
    $e.cpus           = [int]$st.cpus
}

# ---------- servidor ----------
$e.srv_ping = [bool](Test-Connection -ComputerName $SRV -Count 2 -Quiet)
$e.srv_1880 = [bool](Test-Porta $SRV 1880)   # Node-RED / API
$e.srv_1883 = [bool](Test-Porta $SRV 1883)   # Mosquitto

# a rota /api/me sem token deve responder 401: prova que a API esta viva e que
# o flow foi importado, sem precisar de credencial nenhuma
try {
    $r = Invoke-WebRequest -Uri "http://$SRV`:1880/api/me" -TimeoutSec 8 -UseBasicParsing `
             -Headers @{ Authorization = 'Bearer monitor' }
    $e.api_me = [int]$r.StatusCode
} catch {
    # No Windows PowerShell 5.1 um 401 vira excecao -- e 401 aqui e a resposta
    # CERTA (rota viva, token invalido). 0 significa que nem respondeu.
    $resp = $_.Exception.Response
    if ($resp) { $e.api_me = [int]$resp.StatusCode } else { $e.api_me = 0 }
}

# ---------- via SSH (opcional) ----------
$svcBox = 'mediamtx secbox-agent secbox-motion secbox-clip secbox-leds wifi-guard secbox-mqtt-tunnel'
$outBox = Invoke-Remoto "root@$BOX" `
    "cut -d. -f1 /proc/uptime; systemctl is-active $svcBox | tr '\n' ' '; echo; grep -c 'queda detectada' /var/log/wifi-guard.log 2>/dev/null || echo 0; for u in $svcBox; do printf '%s=%s ' `$u `$(systemctl show `$u -p NRestarts --value); done; echo"
if ($outBox) {
    $l = $outBox -split "`n"
    $e.box_uptime_s   = [int]($l[0].Trim())
    $e.box_servicos   = $l[1].Trim()
    $e.box_quedas_wifi = [int]($l[2].Trim())
    if ($l.Count -gt 3) { $e.box_reinicios = $l[3].Trim() }
    $e.ssh_box = $true
} else { $e.ssh_box = $false }

$svcSrv = 'mosquitto postgresql nodered secbox-push'
$outSrv = Invoke-Remoto "$USR@$SRV" `
    "cut -d. -f1 /proc/uptime; systemctl is-active $svcSrv | tr '\n' ' '; echo; df --output=pcent / | tail -1 | tr -dc '0-9'; echo; for u in $svcSrv; do printf '%s=%s ' `$u `$(systemctl show `$u -p NRestarts --value); done; echo"
if ($outSrv) {
    $l = $outSrv -split "`n"
    $e.srv_uptime_s = [int]($l[0].Trim())
    $e.srv_servicos = $l[1].Trim()
    $e.srv_disco_pct = [int]($l[2].Trim())
    if ($l.Count -gt 3) { $e.srv_reinicios = $l[3].Trim() }
    $e.ssh_srv = $true
} else { $e.ssh_srv = $false }

# ---------- histórico e resumo ----------
($e | ConvertTo-Json -Compress) | Add-Content -Path $HIST -Encoding utf8

# mantém o arquivo em tamanho utilizável (uma linha a cada 30 min ~ 1 mês)
$linhas = @(Get-Content $HIST)
if ($linhas.Count -gt 2000) { $linhas[-1500..-1] | Set-Content -Path $HIST -Encoding utf8 }

"=== SecBox $($e.ts) ==="
"TV box    ping=$(if($e.box_ping){'ok'}else{'FORA'})  9997=$(if($e.box_9997){'ok'}else{'FECHADA'})  8889=$(if($e.box_8889){'ok'}else{'FECHADA'})  9996=$(if($e.box_9996){'ok'}else{'FECHADA'})"
if ($e.PSObject -and $null -ne $e.box_9997_auth -and -not $e.box_9997_auth) {
    "  ATENCAO   9997 SEM TOKEN -- qualquer um que alcance a porta escreve a configuracao"
}
if ($null -ne $e.cams_conectadas) {
    "  cameras   $($e.cams_conectadas)/$($e.cams_limite) ($($e.cams_nomes))  excedido=$($e.cams_excedido)"
}
if ($null -ne $e.disco_livre_gb) {
    "  disco     $($e.disco_livre_gb) GB livres ($($e.disco_uso_pct)% usado)  autonomia $($e.gravacao_horas) h  carga $($e.carga)/$($e.cpus)"
}
if ($e.ssh_box) {
    "  uptime    $([math]::Round($e.box_uptime_s/3600,1)) h   servicos: $($e.box_servicos)"
    "  wifi      $($e.box_quedas_wifi) quedas no log"
    "  reinicios $($e.box_reinicios)"
}
"Servidor  ping=$(if($e.srv_ping){'ok'}else{'FORA'})  1880=$(if($e.srv_1880){'ok'}else{'FECHADA'})  1883=$(if($e.srv_1883){'ok'}else{'FECHADA'})  /api/me=$($e.api_me)"
if ($e.ssh_srv) {
    "  uptime    $([math]::Round($e.srv_uptime_s/3600,1)) h   servicos: $($e.srv_servicos)"
    "  disco     $($e.srv_disco_pct)% usado"
    "  reinicios $($e.srv_reinicios)"
}
if (-not $e.ssh_box -or -not $e.ssh_srv) {
    "  (sem SSH em: $(@(if(-not $e.ssh_box){'box'}; if(-not $e.ssh_srv){'servidor'}) -join ', ') -- chave nao instalada ou recusada)"
}

# ---------- o que mudou desde a coleta anterior ----------
if ($linhas.Count -ge 2) {
    $ant = $linhas[-2] | ConvertFrom-Json
    $mud = @()
    foreach ($k in $e.Keys) {
        if ($k -eq 'ts') { continue }
        $a = $ant.$k
        $b = $e[$k]
        # Exige os dois lados presentes: a rede da box cai, e uma leitura que
        # faltou nao e mudanca de estado. Sem isto, um soluco de rede apareceria
        # como "cams_conectadas: 1 -> " e treinaria quem le a ignorar o relatorio.
        if ($null -ne $a -and $null -ne $b -and "$a" -ne "$b") {
            $mud += "$k : $a -> $b"
        }
    }
    if ($mud.Count) { ""; "=== mudou desde a coleta anterior ==="; $mud | ForEach-Object { "  $_" } }
}
