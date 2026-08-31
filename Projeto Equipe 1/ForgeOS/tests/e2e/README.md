# E2E do Portal com Playwright (browser real → box real)

Pré-requisitos:
- PC com dongle Wi-Fi conectado ao AP da box (`RTL8189FTV_AP`) — o portal fica em `http://192.168.4.1`
- Se houver outra rede Wi-Fi com autoconexão no PC, bloqueie-a durante o teste
  (o AP da box sai do ar durante o ciclo de rollback e o Windows "rouba" a
  conexão): `netsh wlan add filter permission=block ssid="<rede>" networktype=infra` (admin)

Executar:
```bash
npm install
npx playwright install chromium
npx playwright test
```

Cobertura:
- **P1** carregamento: brand, badge, abas PSK/EAP, seção módulos
- **P2** API: 400 para senha curta e EAP sem identidade; AP segue ativo
- **P3** ciclo completo: provision p/ rede inexistente → AP sai → rollback →
  badge de falha + `ap_active` true (≈90s)
- **P4** reset: volta ao modo provisionamento limpo
