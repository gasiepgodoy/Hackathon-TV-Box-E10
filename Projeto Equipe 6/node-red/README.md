# Dashboard Node-RED

Painel para ver o que está no banco da TV Box e testar o caminho dos dados sem
abrir terminal. O arquivo `dashboard-hub.json` é um flow pronto para importar.

O painel **lê o SQLite direto** (`/var/lib/hub/dados.db`) e **publica no
Mosquitto local** para os testes. Ele não reimplementa o hub: os botões de teste
mandam mensagens MQTT de verdade, que atravessam o `hub-coletor` e caem no banco
pelo caminho normal. Se a leitura aparece na tabela, a cadeia inteira funciona.

---

## Instalação

Tudo roda **na box**, porque o dashboard precisa do arquivo do banco.

```bash
# Node-RED
sudo npm install -g --unsafe-perm node-red

# Os dois complementos que este flow usa
cd ~/.node-red
npm install node-red-dashboard node-red-node-sqlite

sudo systemctl enable --now nodered
```

`node-red-dashboard` é o dashboard **1.x** (nós `ui_*`). O flow não é compatível
com o Dashboard 2.0 (`@flowfuse/node-red-dashboard`), que usa outros tipos de nó.

Depois: abra `http://<ip-da-box>:1880`, menu **☰ → Import → select a file to
import**, escolha `dashboard-hub.json`, **Import** e **Deploy**.
O painel fica em `http://<ip-da-box>:1880/ui`.

### Permissão no banco — o tropeço mais provável

O banco está em WAL, e **em WAL até quem só lê precisa escrever**: o SQLite cria
os arquivos `dados.db-wal` e `dados.db-shm` ao abrir. Por isso a permissão tem de
estar no **diretório**, não só no arquivo — dar `chmod +r` no `.db` não resolve, e
o erro que aparece (`SQLITE_CANTOPEN`) não diz nada sobre isso.

Supondo que o Node-RED rode como o usuário `nodered`:

```bash
sudo chgrp -R nodered /var/lib/hub
sudo chmod  g+rwx     /var/lib/hub
sudo chmod  g+rw      /var/lib/hub/dados.db
```

Confira com qual usuário ele está rodando: `systemctl show -p User nodered`.

Se o caminho do banco estiver errado, **não aparece erro**: o nó de configuração
usa o modo `RWC`, que cria um arquivo vazio em silêncio, e o painel abre em
branco. O botão **Rodar diagnóstico** detecta exatamente esse caso.

### Memória

A box tem 1,8 GB e já roda Zigbee2MQTT, ChirpStack, PostgreSQL e Mosquitto — foi
com essa combinação que o Z2M entrou em *crash-loop* antes. O Node-RED soma uns
100–150 MB. Antes de deixá-lo permanentemente ligado, garanta alguma folga:

```bash
free -h                                    # veja o que sobra
sudo apt install zram-tools                # compressão em RAM, sem gastar o SD
```

Uma alternativa é habilitar o serviço só durante a demonstração
(`sudo systemctl start nodered`) e desligar depois.

---

## As três abas

**Visão Geral** — contagens do hub, últimas 15 leituras, fila do backhaul
opcional, medidores do sensor escolhido no seletor e um atalho para a página de
exportação. A cor de "Última leitura" fica verde até 10 minutos porque o coletor
grava em lote a cada 5 minutos (`intervalo_flush_s`): atraso menor que isso é o
funcionamento normal, não falha.

O atalho **Levar os dados** monta o endereço em JavaScript, a partir do host da
própria página, em vez de fixar `192.168.4.1`. Quem abrir o painel pelo AP, pela
rede cabeada ou por VPN recebe um link válido na rede em que já está. Ele aponta
para o `hub-exportador` na porta 8000 — o dashboard serve para *ver*, a página de
exportação serve para *levar*. Detalhes em
[Levar os dados embora](../README.md#levar-os-dados-embora).

**Histórico** — gráficos por período. Até 6 horas o gráfico usa as **leituras
brutas**, onde a resolução real importa; acima disso usa os **agregados**, porque
7 dias de leituras brutas seriam milhares de pontos para o navegador desenhar.
Nos agregados aparecem mín/média/máx juntos: uma geada de 20 minutos some numa
média horária, e é justamente esse evento que o hub existe para detectar.

**Testes** — cinco botões que publicam no MQTT:

| Botão | O que publica | Resultado esperado |
|---|---|---|
| Leitura Zigbee normal | `zigbee2mqtt/teste_zigbee` | aparece na tabela |
| Uplink LoRa (BME280) | envelope do ChirpStack com base64 | aparece **com pressão** |
| Simular geada (1.5 °C) | temperatura abaixo de `temp_min` | evento, **após o hub-ciclo** |
| Nó LoRa com BME quebrado | `{"err":"bme280"}` | recusado, mas visível no tráfego |
| Payload inválido | texto que não é JSON | recusado |

Os dois últimos servem para ver a **rejeição acontecendo**. Um nó vivo sem sensor
e um nó fora do alcance do gateway produzem o mesmo silêncio no banco; o painel
de tráfego é o que separa os dois casos.

O botão **Apagar sensores de teste** remove `teste_zigbee`, `teste_lora` e
`teste_geada` com suas leituras, agregados e eventos, deixando os sensores reais
intactos.

---

## Duas limitações que valem saber

**A classificação no painel de tráfego é uma dica, não o veredito.** Quem decide
o que entra no banco é `diagnosticar()` em `src/hub/coletor.py`, em Python. O
JavaScript do painel é uma réplica simplificada e pode divergir dele com o tempo.
A comparação útil é entre as duas telas: se algo aparece como *aceita* no tráfego
mas **não** aparece na tabela de leituras, o problema está no coletor, não no
MQTT. Para o veredito autoritativo, use `python3 -m hub.cli espiar` na box.

**O botão de geada não cria o evento na hora.** Ele só grava uma leitura fria. O
evento nasce quando o `hub-ciclo` roda e processa a janela — é assim que o
processamento de borda funciona. Para ver na hora, rode o ciclo à mão na box e
atualize a aba.

---

## Sobre o arquivo

`dashboard-hub.json` é gerado, não editado à mão. Se precisar mexer, prefira
editar pelo próprio Node-RED e exportar de volta (**☰ → Export → all flows**).
