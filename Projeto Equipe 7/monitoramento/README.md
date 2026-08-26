# Monitoramento

Coletor que verifica a TV box e o servidor e reporta **o que mudou** desde a
execução anterior. Roda numa máquina Windows que alcance as duas por VPN.

| Arquivo | O quê |
|---|---|
| [`check.ps1`](check.ps1) | o coletor |
| [`config.example.json`](config.example.json) | modelo dos endereços (copiar para `config.json`) |

## O que ele enxerga

**Sem SSH** — ping, portas (9997, 8889 e 9996 na box; 1880 e 1883 no servidor),
`/cameras` e `/storage` do clip-server, e `/api/me` do servidor, que deve
responder `401` (rota viva recusando um token inválido).

**Com SSH** — uptime, estado de cada serviço systemd, **contador de reinícios
por serviço**, uso de disco e a contagem de quedas do Wi-Fi no `wifi-guard`.

O contador de reinícios existe porque `is-active` não basta: um serviço em laço
de falha alterna entre `activating` e `failed`, e uma coleta pontual pega
qualquer um dos dois. Foi assim que a detecção de movimento ficou cinco dias
parada sem ninguém notar — o `activating` aparecia e passava por transição
normal. `NRestarts` subindo é inequívoco.

Cada execução acrescenta uma linha JSON em `history.jsonl` e imprime um resumo
com uma seção **"mudou desde a coleta anterior"** — que é o que torna o relatório
útil sem ninguém precisar ler número por número.

## Instalar

```powershell
copy config.example.json config.json   # preencher os endereços
ssh-keygen -t ed25519 -f id_monitor -N '""' -C "secbox-monitor"
```

Instale a chave pública nas duas máquinas (`~/.ssh/authorized_keys`). Para
apertar, prefixe a linha com `from="IP_DA_MAQUINA_QUE_MONITORA" `.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check.ps1
```

Para rodar periodicamente, aponte o Agendador de Tarefas do Windows para essa
mesma linha.

## Decisões que valem explicação

**O token da 9997 não é guardado aqui.** O coletor busca o `config.json` da
própria box por SSH a cada execução e extrai o token dali. Uma cópia a menos de
credencial no mundo, e ela nunca fica desatualizada quando o token é girado.

**`/health` é consultado sem token** — é o único endpoint aberto do
clip-server, e existe justamente para denunciar o estado perigoso: se ele
responder `auth: false`, a porta 9997 subiu sem proteção e o relatório destaca
isso.

**Duas tentativas nas chamadas HTTP.** A rede da box cai várias vezes por hora,
e medindo dava cerca de uma coleta em três perdendo esses dados. A repetição
recupera a maioria, e só custa uma pausa quando já falhou.

**Leitura ausente não é mudança de estado.** O comparador exige os dois lados
presentes: sem isso, um soluço de rede apareceria como
`cams_conectadas : 1 -> ` e treinaria quem lê a ignorar o relatório.

**Falha de rede e "aparelho offline" são coisas diferentes.** O coletor não
converte uma na outra: quando não consegue falar com o servidor, diz isso, em
vez de reportar tudo como fora do ar.

**O comando remoto que lê o `config.json` não usa aspas.** O Windows PowerShell
5.1 mastiga aspas ao repassar argumentos para executáveis nativos, e o comando
chegava truncado no destino. Por isso ele traz o JSON inteiro e faz o parse
local.

## Nunca versionar

O `.gitignore` já cobre, mas vale explicitar: `config.json` (endereços internos),
`id_monitor` (**chave privada**), `id_monitor.pub` e `history.jsonl`.
