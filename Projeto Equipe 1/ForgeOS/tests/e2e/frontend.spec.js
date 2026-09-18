const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const responses = {
  '/rest/metrics': { cpu_pct: 12.5, cpu_temp: 48, ram_used_mb: 420, ram_total_mb: 1980, ram_pct: 21.2, disk_used_gb: 3.5, disk_total_gb: 8, rx_kbs: 1.2, tx_kbs: 0.3, load_avg: [0.1, 0.2, 0.1], top_processes: [{pid: 753, name: 'forge-portal', cpu: 1, mem: 2}] },
  '/api/status': { ap_active: true, ssid: 'ForgeOS', client_connected: false },
  '/rest/ethernetStatus': { local_ip: '192.168.1.20', mac_address: 'AA:BB:CC:DD:EE:FF' },
  '/api/scan': { networks: [{ssid: 'Lab "A" d\'água', encryption: 'psk', flags: '[WPA2]', rssi: -45, channel: 6}] },
  '/api/services': { services: [{unit: 'forge-portal.service', desc: 'Portal ForgeOS', category: 'forgeos', state: 'active', active: true, enabled: true}] },
  '/rest/modules': { modules: [{id: 'mina', name: 'Mina', description: 'Assistente virtual acadêmica', category: 'ai', status: {state: 'available'}}] },
  '/api/logs': { logs: [] },
};
test.beforeEach(async ({ page }) => {
  await page.route(/\/(api|rest)\//, route => {
    const pathname = new URL(route.request().url()).pathname;
    return route.fulfill({json: responses[pathname] || {ok:true}});
  });
});
for (const [name, width, height] of [['mobile',390,844], ['tablet',800,1024], ['desktop',1440,1000], ['tv',1920,1080]]) {
  test(`${name}: all screens render without horizontal overflow or script errors`, async ({page}) => {
    await page.setViewportSize({width,height});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/');
    await expect(page.locator('#dash-cpu-val')).toHaveText('12.5%');
    await expect(page.locator('#connection-notice')).toBeHidden();
    for (const tab of ['overview','networking','interfaces','services','modules','logs']) {
      await page.evaluate(tab => { location.hash = tab; }, tab);
      await expect(page.locator(`#view-${tab}`)).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    expect(errors).toEqual([]);
    await page.evaluate(() => { location.hash = 'overview'; });
    await expect(page.locator('#view-overview')).toBeVisible();
    await page.screenshot({path:`artifacts/modern-${name}.png`,fullPage:true});
  });
}
test('quoted SSID, Wi-Fi payload and modal keyboard focus', async ({page}) => {
  await page.goto('/#networking');
  const button = page.locator('#wifi-networks-container [data-connect-ssid]');
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#prov-ssid')).toHaveValue('Lab "A" d\'água');
  await expect(page.locator('#prov-ssid')).toBeFocused();
  await page.locator('#btn-submit-provision').focus();
  await page.keyboard.press('Tab');
  await expect(page.locator('#connect-modal [aria-label="Fechar modal"]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(button).toBeFocused();
  await button.click();
  await page.locator('#prov-password').fill('test-password');
  const request = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/api/provision'));
  await page.locator('#btn-submit-provision').click();
  expect((await request).postDataJSON()).toMatchObject({ssid:'Lab "A" d\'água', password:'test-password'});
});
test('command palette and TV arrows are keyboard operable', async ({page}) => {
  await page.goto('/');
  await page.locator('[data-tab="overview"]').focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('[data-tab="logs"]')).toBeFocused();
  await page.keyboard.press('Control+k');
  await page.locator('#cmd-input').fill('Interfaces');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  await expect(page.locator('#view-interfaces')).toBeVisible();
  await expect(page.locator('#cmd-modal')).toBeHidden();
});
test('unavailable telemetry is explicit and recovers', async ({page}) => {
  await page.route('**/rest/metrics', route => route.fulfill({status:503,json:{error:'offline'}}));
  await page.goto('/');
  await expect(page.locator('#connection-notice')).toContainText('Sem conexão');
  await expect(page.locator('#dash-cpu-val')).toHaveText('—');
  await page.unroute('**/rest/metrics');
  await page.getByRole('button', {name:'Atualizar telemetria'}).click();
  await expect(page.locator('#connection-notice')).toBeHidden();
});
test('theme persists, unknown routes recover, zoom is allowed', async ({page}) => {
  await page.goto('/#unknown');
  await expect(page.locator('#view-overview')).toBeVisible();
  await page.locator('#theme-toggle').click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  expect(await page.locator('meta[name="viewport"]').getAttribute('content')).not.toContain('user-scalable=no');
  await page.screenshot({path:'artifacts/modern-light.png',fullPage:true});
});
test('all portal screens meet automated WCAG AA checks in both themes', async ({page}) => {
  await page.goto('/');
  for (const theme of ['dark', 'light']) {
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    for (const tab of ['overview','networking','interfaces','services','modules','logs']) {
      await page.evaluate(tab => { location.hash = tab; }, tab);
      await expect(page.locator(`#view-${tab}`)).toBeVisible();
      const result = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
      expect.soft(result.violations.map(v => ({id:v.id,nodes:v.nodes.map(n => n.target)})), `${theme}/${tab}`).toEqual([]);
    }
  }
});
