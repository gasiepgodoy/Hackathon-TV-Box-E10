# Gravar só com movimento

Cada câmera escolhe, no app, entre dois modos de gravação:

| Modo | O que faz | Espaço |
|---|---|---|
| **Sempre** (`continuo`) | guarda tudo até a retenção configurada | previsível e constante |
| **Só com movimento** (`movimento`) | grava tudo e **descarta depois** o que não teve movimento | uma fração — medida pela própria box |

## Por que não é um liga/desliga da captura

O caminho óbvio seria parar a gravação e religá-la quando o detector dispara.
Não é o que acontece aqui, por dois motivos:

**Perderia o começo da cena.** Quando o movimento é detectado, o que interessa
já aconteceu: como a pessoa entrou, de onde veio. Uma gravação que só começa no
disparo entrega o intruso já dentro do quadro.

**Custaria um reinício.** Ligar e desligar `record` no MediaMTX significa
reescrever o `mediamtx.yml` e reiniciar o serviço — o que derruba junto o vídeo
ao vivo. Fazer isso a cada movimento tornaria a câmera inútil justamente durante
o evento.

Gravando sempre e descartando depois, o pré-movimento sai de graça, nada
reinicia, e a economia de espaço é praticamente a mesma. O custo é que o cartão
continua sendo escrito no ritmo de sempre — mas isso já era verdade antes.

## Como o descarte decide

O [`rec-prune.py`](rec-prune.py) roda a cada 5 minutos (timer
`secbox-recprune`) e, para cada câmera em modo movimento, apaga os trechos que
**comprovadamente foram vigiados e estavam vazios**.

A palavra que carrega o peso é *comprovadamente*. "Não há movimento anotado" e
"ninguém estava olhando" são estados diferentes, e tratá-los como o mesmo
apagaria exatamente a gravação do período em que o detector esteve fora do ar —
que é quando ela mais faria falta. Por isso o [`motion.py`](motion.py) escreve
duas coisas em `/opt/secbox/motion-log`:

```
1787929387 cam v     <- "estou vigiando a cam" (a cada 5 min)
1787929502 cam m     <- movimento detectado
```

O podador só considera vigiado o período coberto por marcas `v` consecutivas
próximas o bastante entre si. Detector parado, serviço caído, box reiniciada:
as marcas somem e o período volta a ser intocável.

Um trecho é apagado apenas se **todas** estas forem verdade:

- está inteiro dentro de um período vigiado;
- não cruza nenhuma janela de movimento (30 s antes, 60 s depois de cada um);
- não é o trecho que está sendo gravado agora;
- não foi modificado nos últimos 3 minutos;
- o `secbox-motion` está no ar neste instante.

Qualquer dúvida preserva a gravação. É a única direção de erro aceitável aqui.

Os 60 s posteriores não são um número redondo: o detector tem um *cooldown* de
30 s entre disparos, então uma janela menor abriria buracos no meio de uma cena
de movimento contínuo.

## Segmentos curtos

No modo movimento o `gen-cameras.py` grava em trechos de **60 s** em vez dos
600 s do modo contínuo. O descarte só é fino até o tamanho do arquivo: com
10 minutos por trecho, um único segundo de movimento obrigaria a guardar os
10 minutos inteiros. Custa mais arquivos — e a maioria deles some.

## O modo depende do detector

Sem detecção de movimento ligada (na câmera **e** em Notificações) não há como
saber o que descartar. Nesse caso o `gen-cameras.py` rebaixa o modo para
contínuo e informa isso no `cameras.json`:

```json
{ "record_mode": "continuo", "record_mode_pedido": "movimento" }
```

O app guarda o *pedido* — para a escolha não se perder — e desabilita a opção
enquanto o detector estiver desligado, em vez de oferecer um botão que não faz
o que promete.

## O que o app mostra

O `/storage` devolve, por câmera, o que o podador mediu:

```json
"prune": { "cam": { "vigiado_h": 20.4, "guardado_h": 1.7,
                    "razao": 0.083, "liberado_bytes": 9006123456 } }
```

A `razao` é a fração do tempo vigiado que sobrevive. O app usa **essa medida**
para estimar espaço, em vez de aplicar a conta da gravação contínua e assustar
com um número que não vai acontecer. Enquanto não houver pelo menos uma hora
vigiada a razão não é usada: com dez minutos, um único movimento distorceria a
conta para qualquer lado.

## Ao ligar pela primeira vez

Nada do que já estava gravado é apagado. O registro de vigilância começa no
momento da instalação, e tudo anterior a ele fica fora do alcance do podador —
essas gravações expiram normalmente pela retenção. A economia começa a aparecer
na hora seguinte.

## Verificar

```bash
systemctl list-timers secbox-recprune
journalctl -u secbox-recprune -n 20
cat /opt/secbox/rec-prune.json
tail /opt/secbox/motion-log
```

Na linha do tempo do app, os períodos descartados aparecem como lacunas — que é
a leitura correta: ali não havia nada para ver.
