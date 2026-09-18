// Decode the actual rendered panels using an independent QR decoder.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { PNG } = require('pngjs');
const jsQR = require('jsqr');
const folder = process.argv[2] || 'artifacts';
const wifi = 'WIFI:T:WPA;S:ForgeOS • Configuração;P:BemVindo2026;;';
const cases = {
  'startup-ap_solo.png': wifi,
  'startup-failed.png': wifi,
  'startup-peer.png': 'http://192.168.4.1:8080',
  'startup-connected.png': 'http://192.168.1.120:8080',
  'startup-long-values.png': `WIFI:T:WPA;S:${'R'.repeat(32)};P:${'S'.repeat(63)};;`,
  'qr-special.png': 'WIFI:T:WPA;S:Lab\\; A\\:B\\, \\"C\\"\\\\D;P:a\\;b\\:c\\,d\\"e\\\\f;;',
  'qr-open.png': 'WIFI:T:nopass;S:Aberta;P:;;',
};
for (const [file, expected] of Object.entries(cases)) {
  const png = PNG.sync.read(fs.readFileSync(path.join(folder, file)));
  const decoded = jsQR(new Uint8ClampedArray(png.data), png.width, png.height);
  assert.equal(decoded?.data, expected, `${file}: QR payload must round-trip`);
  console.log(`PASS decoded ${file}`);
}
