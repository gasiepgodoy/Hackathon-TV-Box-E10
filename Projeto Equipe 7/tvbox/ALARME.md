# Alarme sonoro

Sirene tocada pela TV box, acionada por MQTT. O módulo é
[`alarm.py`](alarm.py) + [`systemd/secbox-alarm.service`](systemd/secbox-alarm.service).

## ⚠️ Primeiro: a saída de áudio

**Na TV box S905X2 com o device tree genérico, o jack AV não produz som.** Vale
conferir antes de comprar alto-falante ou perder tempo com o ALSA:

```bash
aplay -l
amixer -c 0 scontrols | grep -viE 'FRDDR|TODDR'
```

No nosso caso a placa existe (`card 0: MESONG12A`, driver `axg-sound-card`) e
tem três PCMs, mas o mixer só oferece:

```
SPDIFOUT_A   SPDIFOUT_B   TDMOUT_B   TOHDMITX
```

Ou seja: **HDMI e SPDIF apenas**. Não aparecem `ACODEC`, `TOACODEC` nem
`Lineout`.

O codec analógico **está descrito** no device tree — `amlogic,t9015` em
`audio-controller@32000` e `amlogic,g12a-toacodec` em `audio-controller@740` —
mas ambos com `status = "disabled"`, e o nó `sound` não tem dai-link para eles.
Sem caminho, não há controle de mixer nem PCM.

O sintoma engana: `mpg123` e `aplay` decodificam o arquivo inteiro e terminam
**sem erro nenhum**. É que no G12A o FRDDR (o bloco que lê as amostras da
memória) precisa ser roteado para um backend pela matriz `FRDDR_x SINK n SEL`;
sem destino, as amostras são escritas no vazio em silêncio.

### Saídas possíveis

| Caminho | Custo | Risco |
|---|---|---|
| **Adaptador USB de áudio** (CM108, PCM2704) | ~R$ 20, vira `card 1` na hora | nenhum |
| HDMI | zero, se houver TV/receiver ligado | não serve para caixa no AV |
| Habilitar o `t9015` no device tree | alto — ver abaixo | o DTB já foi editado à mão para o SDIO a 25 MHz; errar impede o boot |

### Por que o caminho do device tree não compensa

Tomando o `meson-g12a-u200.dts` da mainline como referência, ligar o analógico
não é trocar `disabled` por `okay`. É preciso, **tudo à mão num DTS
decompilado**:

1. dar `phandle` aos nós `acodec` e `toacodec` — como estão desabilitados e
   ninguém os referencia, eles não têm phandle no DTB compilado, e é preciso
   inventar números que não colidam com os existentes;
2. `AVDD-supply` no t9015, apontando para o phandle de um regulador;
3. acrescentar um `codec-1` no `dai-link-3` com `<toacodec TOACODEC_IN_B>`, ao
   lado do `tohdmitx` que já está lá;
4. criar um dai-link novo com `<toacodec TOACODEC_OUT>` tendo `acodec` como
   codec;
5. estender `audio-routing` e acrescentar `audio-widgets = "Line", "Lineout"`.

E há um detalhe do hardware que fecha a questão: no `u200` o caminho não vai do
`ACODEC` direto ao conector — passa por um amplificador na placa
(`"10U2 INL", "ACODEC LOLP"`). TV box popular não costuma trazer esse
amplificador, e há caixa que traz o conector sem sequer levar a trilha do
áudio. Ou seja: dá para fazer todo o trabalho, arriscar o boot, e ainda assim
não sair som — por motivo que nenhum patch resolve.

O adaptador USB é o recomendado. Descubra o dispositivo com `aplay -l` e ponha
em `config.json`:

```json
{ "alsa_device": "plughw:1,0" }
```

> **Hardware:** a saída é nível de linha. Alto-falante **passivo** não toca por
> mais correto que esteja o ALSA — precisa de caixa amplificada ou de um
> miniamplificador.

## O som

[`gen-sirene.py`](gen-sirene.py) gera o WAV localmente, sem download:

```bash
mkdir -p /opt/secbox/sounds
python3 /opt/secbox/gen-sirene.py /opt/secbox/sounds/sirene.wav 10
aplay -D plughw:1,0 /opt/secbox/sounds/sirene.wav
```

Duas escolhas deliberadas: **WAV** (o `aplay` toca nativo, sem depender de
`mpg123`) e **varredura de 600–1400 Hz**, que é onde o ouvido é mais sensível e
onde alto-falante pequeno reproduz bem. Os "sons de alarme" de banco de áudio
costumam ser tom puro agudo (9 kHz): soam altíssimos no celular e somem na
caixinha ligada na saída de linha.

## Comandos MQTT

Tópico `devices/{deviceId}/alarme/command`:

| Payload | Efeito |
|---|---|
| `{"action":"on","seconds":60}` | liga a sirene por 60 s (limitada por `siren_max_seconds`) |
| `{"action":"off"}` | desliga |
| `{"action":"test"}` | toca 3 s |

Um `on` durante uma sirene já tocando **estende** o prazo em vez de ser
ignorado — segundo disparo durante o primeiro alarme é motivo para continuar,
não para encerrar.

Eventos publicados em `devices/{deviceId}/alarme/event`: `sirene_ligada`,
`sirene_desligada` (com `motivo`) e `sirene_falhou`.

> O flow de push do servidor assina `devices/+/alarme/event`. Sem um caso para
> estes tipos ele monta a mensagem genérica — vale acrescentar os textos em
> [`../servidor/nodered/alarme-push.json`](../servidor/nodered/alarme-push.json).

## Travas de segurança

Sirene presa tocando é pior que sirene que não toca, ainda mais num
equipamento que fica sozinho no local:

- **Tempo máximo** (`siren_max_seconds`, padrão 300 s) limita qualquer pedido.
- Um watchdog desliga no prazo mesmo que o comando de parada se perca — o que
  é bem possível, já que a rede desta box cai (ver [`WIFI-INTERNO.md`](WIFI-INTERNO.md)).
- `SIGTERM`/`SIGINT` matam o grupo de processos direto, sem passar pelo lock,
  para que `systemctl stop` e reboot sempre silenciem.
- Se o `aplay` morrer sozinho (dispositivo ALSA errado), publica
  `sirene_falhou` em vez de ficar em silêncio — silêncio seria confundido com
  "o alarme não disparou".

## Instalar

```bash
install -Dm755 alarm.py /opt/secbox/alarm.py
install -Dm755 gen-sirene.py /opt/secbox/gen-sirene.py
python3 /opt/secbox/gen-sirene.py /opt/secbox/sounds/sirene.wav 10
cp systemd/secbox-alarm.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now secbox-alarm
```

Teste ponta a ponta, do servidor ou de qualquer máquina com o broker à mão:

```bash
mosquitto_pub -h SEU_SERVIDOR -u serverapp -P SUA_SENHA \
  -t devices/TVB-XXXXXX/alarme/command -m '{"action":"test"}'
```
