// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('ForgeOS Portal — E2E na box real', () => {

  test('P1 · portal carrega: brand, badge, formulário e módulos', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('MultiForge');
    await expect(page.locator('#status-badge')).toBeVisible();
    await expect(page.locator('#mode-psk')).toBeChecked();
    await expect(page.locator('#psk-ssid')).toBeVisible();
    await expect(page.locator('#psk-pass')).toBeVisible();
    await expect(page.locator('#btn-go')).toBeEnabled();

    // alternância de abas PSK -> EAP
    await page.check('#mode-eap');
    await expect(page.locator('#card-eap')).toBeVisible();
    await expect(page.locator('#card-psk')).toBeHidden();
    await expect(page.locator('#eap-ssid')).toHaveValue('eduroam');
    await page.check('#mode-psk');
    await expect(page.locator('#card-psk')).toBeVisible();

    await expect(page.locator('text=Módulos')).toBeVisible();
    await page.screenshot({ path: 'artifacts/p1-portal.png', fullPage: true });
  });

  test('P2 · API rejeita payload inválido (400) sem derrubar o AP', async ({ request }) => {
    const r1 = await request.post('/api/provision', {
      data: { mode: 'psk', ssid: 'RedeQualquer', password: '123' },
    });
    expect(r1.status()).toBe(400);
    expect(await r1.json()).toHaveProperty('error');

    const r2 = await request.post('/api/provision', {
      data: { mode: 'eap', ssid: 'eduroam', method: 'PEAP', phase2: 'MSCHAPV2', identity: '', password: 'p' },
    });
    expect(r2.status()).toBe(400);

    const st = await request.get('/api/status');
    expect((await st.json()).ap_active).toBe(true);
  });

  test('P3 · provisionamento para rede inexistente → badge de falha + AP restaurado', async ({ page, request }) => {
    test.setTimeout(300_000);
    await page.goto('/');
    await page.fill('#psk-ssid', 'Playwright-Fake-Net');
    await page.fill('#psk-pass', 'senha-falsa-123');
    await page.click('#btn-go');

    // UI entra em modo "testando conexão"
    await expect(page.locator('#status-badge')).toContainText(/testando|enviando/i, { timeout: 15_000 });

    // ciclo completo: AP sai (~75s), rollback, AP volta — badge final de falha
    await expect(page.locator('#status-badge')).toContainText(/falh/i, { timeout: 240_000 });

    const st = await (await request.get('/api/status')).json();
    expect(st.last_failed).toBe(true);
    expect(st.ap_active).toBe(true);

    await page.screenshot({ path: 'artifacts/p3-rollback-falha.png', fullPage: true });
  });

  test('P4 · reset restaura modo provisionamento limpo', async ({ page, request }) => {
    await page.goto('/');
    await page.click('#btn-reset');
    await expect.poll(async () => (await (await request.get('/api/status')).json()).last_failed, {
      timeout: 30_000,
    }).toBe(false);
    await expect(page.locator('#status-badge')).toContainText(/provisionamento/i, { timeout: 60_000 });
  });
});
