const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

async function renderForgeImager() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1200, height: 780 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  const boardImgFile = path.resolve(__dirname, '../../../ForgeImager/board_processed.png');
  const b64Data = fs.readFileSync(boardImgFile).toString('base64');

  const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<title>ForgeImager</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

  :root {
    --Forge-orange: #f26419;
    --Forge-teal: #22a079;
    --bg-app: #0d1614;
    --bg-secondary: #13221e;
    --bg-card: #182824;
    --bg-hover: #213933;
    --text-primary: #f0f7f5;
    --text-secondary: #b8ccc6;
    --text-muted: #748c85;
    --border-color: #243c35;
    --border-light: #2d4a41;
    --accent: #f26419;
    --accent-rgb: 242, 100, 25;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: #080d0c;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
    -webkit-font-smoothing: antialiased;
  }

  .window {
    width: 1080px;
    height: 680px;
    background: var(--bg-app);
    border-radius: 16px;
    border: 1px solid var(--border-color);
    box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.85), 0 0 0 1px rgba(255, 255, 255, 0.05);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Title bar */
  .titlebar {
    height: 48px;
    background: #0a110f;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 18px;
    user-select: none;
  }

  .titlebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .titlebar-logo {
    width: 26px;
    height: 26px;
    border-radius: 7px;
    background: linear-gradient(135deg, #f26419, #e63946);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 15px;
    color: white;
    box-shadow: 0 2px 8px rgba(242, 100, 25, 0.4);
  }

  .titlebar-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }

  .titlebar-version {
    font-size: 11px;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
    background: var(--bg-secondary);
    padding: 2px 7px;
    border-radius: 10px;
    border: 1px solid var(--border-color);
  }

  .titlebar-controls {
    display: flex;
    gap: 8px;
  }

  .window-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }
  .window-dot.close { background: #e63946; }
  .window-dot.min { background: #f59e0b; }
  .window-dot.max { background: #22a079; }

  /* Stepper header */
  .stepper {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 14px 24px;
    background: #0f1a17;
    border-bottom: 1px solid var(--border-color);
  }

  .step-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .step-item.completed {
    color: var(--Forge-teal);
  }

  .step-item.active {
    color: var(--Forge-orange);
  }

  .step-badge {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #1b2e29;
    border: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
  }

  .step-item.completed .step-badge {
    background: rgba(34, 160, 121, 0.2);
    border-color: var(--Forge-teal);
    color: var(--Forge-teal);
  }

  .step-item.active .step-badge {
    background: rgba(242, 100, 25, 0.2);
    border-color: var(--Forge-orange);
    color: var(--Forge-orange);
    font-weight: 700;
  }

  .step-separator {
    width: 32px;
    height: 2px;
    background: var(--border-color);
  }
  .step-separator.completed {
    background: var(--Forge-teal);
  }

  /* Main stage */
  .stage-content {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 36px 52px;
    gap: 52px;
    background: radial-gradient(circle at 25% 50%, rgba(242, 100, 25, 0.09) 0%, transparent 65%);
  }

  /* Board column */
  .board-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
  }

  .board-glow {
    position: absolute;
    width: 280px;
    height: 280px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(242, 100, 25, 0.35) 0%, rgba(242, 100, 25, 0.08) 45%, transparent 70%);
    filter: blur(28px);
    z-index: 0;
  }

  .board-image {
    width: 310px;
    height: auto;
    object-fit: contain;
    position: relative;
    z-index: 1;
    filter: drop-shadow(0 24px 38px rgba(0, 0, 0, 0.75));
  }

  /* Details column */
  .details-col {
    flex: 1.25;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .board-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .board-title {
    font-size: 32px;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .badges-row {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 100px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  /* Progress Card */
  .progress-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
  }

  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }

  .card-status-label {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .status-tag {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
    color: var(--Forge-orange);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .status-tag-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--Forge-orange);
    box-shadow: 0 0 8px var(--Forge-orange);
  }

  .card-main-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
  }

  .card-percent {
    font-size: 32px;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
    line-height: 1;
  }

  /* Progress bar */
  .bar-container {
    width: 100%;
    height: 10px;
    background: #101c18;
    border-radius: 6px;
    overflow: hidden;
    position: relative;
    border: 1px solid var(--border-color);
  }

  .bar-fill {
    width: 68%;
    height: 100%;
    background: linear-gradient(90deg, #f26419, #ff8c42);
    border-radius: 6px;
    box-shadow: 0 0 16px rgba(242, 100, 25, 0.6);
  }

  .card-metrics {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11.5px;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
  }

  .metric-item strong {
    color: var(--text-secondary);
  }

  /* Phase steps timeline */
  .phases-timeline {
    display: flex;
    flex-direction: column;
    gap: 9px;
    background: #111d19;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid var(--border-color);
  }

  .phase-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
  }

  .phase-left {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-secondary);
  }

  .phase-indicator {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
  }

  .phase-row.done .phase-indicator {
    background: rgba(34, 160, 121, 0.25);
    color: var(--Forge-teal);
  }
  .phase-row.done .phase-name {
    color: var(--text-secondary);
  }

  .phase-row.running .phase-indicator {
    background: var(--Forge-orange);
    color: white;
    box-shadow: 0 0 10px rgba(242, 100, 25, 0.5);
  }
  .phase-row.running .phase-name {
    color: var(--text-primary);
    font-weight: 600;
  }

  .phase-row.pending .phase-indicator {
    background: #1e332c;
    color: var(--text-muted);
  }
  .phase-row.pending .phase-name {
    color: var(--text-muted);
  }

  .phase-status-badge {
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    padding: 2px 8px;
    border-radius: 6px;
  }

  .phase-row.done .phase-status-badge {
    background: rgba(34, 160, 121, 0.15);
    color: var(--Forge-teal);
  }
  .phase-row.running .phase-status-badge {
    background: rgba(242, 100, 25, 0.2);
    color: var(--Forge-orange);
    font-weight: 700;
  }
  .phase-row.pending .phase-status-badge {
    color: var(--text-muted);
  }

  /* Footer action */
  .actions-row {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }

  .btn {
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    border: none;
  }

  .btn-cancel {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    color: var(--text-secondary);
  }
</style>
</head>
<body>
  <div class="window">
    <div class="titlebar">
      <div class="titlebar-brand">
        <div class="titlebar-logo">F</div>
        <span class="titlebar-title">ForgeImager</span>
        <span class="titlebar-version">v2.0.0</span>
      </div>
      <div class="titlebar-controls">
        <div class="window-dot min"></div>
        <div class="window-dot max"></div>
        <div class="window-dot close"></div>
      </div>
    </div>

    <div class="stepper">
      <div class="step-item completed">
        <div class="step-badge">✓</div>
        <span>1. Imagem do Sistema</span>
      </div>
      <div class="step-separator completed"></div>
      <div class="step-item completed">
        <div class="step-badge">✓</div>
        <span>2. Dispositivo de Destino</span>
      </div>
      <div class="step-separator completed"></div>
      <div class="step-item active">
        <div class="step-badge">3</div>
        <span>3. Gravação & Injeção ext4</span>
      </div>
    </div>

    <div class="stage-content">
      <div class="board-col">
        <div class="board-glow"></div>
        <img class="board-image" src="data:image/png;base64,${b64Data}" alt="BTV Express E10" />
      </div>

      <div class="details-col">
        <div class="board-header">
          <h1 class="board-title">BTV Express E10</h1>
          <div class="badges-row">
            <div class="badge">
              <span>⚡ Amlogic S905X2 (ARM64)</span>
            </div>
            <div class="badge">
              <span>💾 SanDisk Ultra 32GB (MicroSD)</span>
            </div>
          </div>
        </div>

        <div class="progress-card">
          <div class="card-top">
            <div class="card-status-label">
              <div class="status-tag">
                <span class="status-tag-dot"></span>
                <span>Gravando Imagem</span>
              </div>
              <div class="card-main-title">forgeos-btv-e10-v2.1.0.img.xz</div>
            </div>
            <div class="card-percent">68%</div>
          </div>

          <div class="bar-container">
            <div class="bar-fill"></div>
          </div>

          <div class="card-metrics">
            <div class="metric-item">Velocidade: <strong>24.8 MB/s</strong></div>
            <div class="metric-item">Tempo Restante: <strong>00:38</strong></div>
            <div class="metric-item">Gravado: <strong>1.4 GB / 2.1 GB</strong></div>
          </div>
        </div>

        <div class="phases-timeline">
          <div class="phase-row done">
            <div class="phase-left">
              <div class="phase-indicator">✓</div>
              <span class="phase-name">Download do manifesto & imagem oficial</span>
            </div>
            <span class="phase-status-badge">Concluído</span>
          </div>

          <div class="phase-row running">
            <div class="phase-left">
              <div class="phase-indicator">⚡</div>
              <span class="phase-name">Descompressão e gravação multithread</span>
            </div>
            <span class="phase-status-badge">68% (24.8 MB/s)</span>
          </div>

          <div class="phase-row pending">
            <div class="phase-left">
              <div class="phase-indicator">3</div>
              <span class="phase-name">Verificação de integridade SHA-256</span>
            </div>
            <span class="phase-status-badge">Aguardando</span>
          </div>

          <div class="phase-row pending">
            <div class="phase-left">
              <div class="phase-indicator">4</div>
              <span class="phase-name">Injeção userspace ext4 (Wi-Fi / Setup)</span>
            </div>
            <span class="phase-status-badge">Aguardando</span>
          </div>
        </div>

        <div class="actions-row">
          <button class="btn btn-cancel">Cancelar Operação</button>
        </div>
      </div>
    </div>
  </div>
</body>
</html>`;

  await page.setContent(html, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  const destPath = path.resolve(__dirname, '../../../imagens/forgeimager_flashing.png');
  await page.locator('.window').screenshot({ path: destPath, scale: 'css' });
  console.log('Saved ForgeImager screenshot to:', destPath);

  await browser.close();
}

renderForgeImager().catch(console.error);
