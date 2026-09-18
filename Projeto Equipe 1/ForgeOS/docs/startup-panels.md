# Painéis de inicialização — revisão visual

## Apresentação

O portal mantém o minimalismo aprovado, com logos alinhadas, menos divisórias
decorativas e cards de métricas com espaçamento consistente. O circuito HDMI
usa a mesma paleta e tipografia nos estados: Wi-Fi inicial, celular detectado,
configuração em andamento, conectado e falha.

`display/panel_renderer.py` contém apenas apresentação. Recebe estado e dados,
retorna uma imagem Pillow 1920 × 1080 e não configura rede nem escreve no
framebuffer. `qr_screen.py` utiliza esse renderizador e detecta a associação de
um celular para avançar do QR Wi-Fi ao QR do portal. `kiosk_bridge.py` adapta o
motor ForgeHub já instalado, preservando suas rotinas de estados e framebuffer.
Temperatura, memória e atividade continuam disponíveis no rodapé.

Os QR codes usam módulos inteiros, preto sobre branco e margem de quatro módulos,
conforme a [orientação da DENSO WAVE](https://www.qrcode.com/en/howto/code.html).
A logo fica fora da área do código. Credenciais especiais recebem escape no
payload Wi-Fi; redes abertas usam `nopass`. Credenciais longas quebram linha sem
ser truncadas. Nenhum progresso percentual fictício é exibido durante a conexão.

## Validação

Na Armbian, dentro de ForgeOS:

```sh
python3 tests/render_display_previews.py /tmp/forgeos-panel-previews
```

Com os PNGs copiados para `tests/e2e/artifacts`, dentro de `tests/e2e`:

```sh
npm ci
npm test
npm run test:qr
```

Foram renderizados os cinco estados, além do caso de SSID com 32 caracteres e
senha com 63. Sete QR codes foram decodificados por jsQR, uma implementação
independente do gerador qrencode. Casos incluem portal, Wi-Fi, rede aberta e
caracteres especiais. As imagens de demonstração usam credenciais fictícias.
Os nove testes de navegador, incluindo acessibilidade, também passaram.

## Ativação nesta TV Box

O novo renderizador e o adaptador foram instalados em
`/opt/forgehub/hardware/display/`. O arquivo original `forge_kiosk.py` foi
preservado. O serviço `forge-kiosk` usa um override:

`/etc/systemd/system/forge-kiosk.service.d/50-minimal-panels.conf`

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /opt/forgehub/hardware/display/kiosk_bridge.py
```

Backup: `/root/forgeos-display-backups/20260914-142051`.
Após o reinício do serviço, ele permaneceu ativo com zero reinícios inesperados
e produziu uma imagem nova do framebuffer. A TV Box não foi reiniciada e a
conexão de rede não foi alterada. O override permanece para as próximas partidas.
A leitura com uma câmera física ainda depende de distância, brilho e tela.

Para voltar ao motor visual anterior, remova somente esse override, execute
`systemctl daemon-reload` e reinicie `forge-kiosk`. O backend web ForgeHub não
foi substituído pelo portal Python; os refinamentos web continuam no checkout
`/root/work/Hackathon-TV-Box-E10-frontend`.
