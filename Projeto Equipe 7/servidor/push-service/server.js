// Microserviço de envio de push (FCM) do SecBox.
// O Node-RED chama POST http://localhost:3001/send { tokens, title, body }
// quando um alarme dispara.
//
// Requer a chave de serviço do Firebase em ./secbox-sa.json (NÃO versionada).
// Instalação (Node 18): npm install firebase-admin@12 express
//   (firebase-admin@14 exige Node>=22 e mudou a API; a v12 funciona no Node 18.)

const express = require('express');
const admin = require('firebase-admin');
const serviceAccount = require('./secbox-sa.json');

admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });

const app = express();
app.use(express.json());

app.post('/send', async (req, res) => {
  const { tokens, title, body } = req.body;
  if (!Array.isArray(tokens) || tokens.length === 0) {
    return res.status(400).json({ error: 'no tokens' });
  }
  try {
    const r = await admin.messaging().sendEachForMulticast({
      tokens,
      notification: { title: title || 'SecBox', body: body || '' },
      android: { priority: 'high' },
    });
    res.json({ successCount: r.successCount, failureCount: r.failureCount });
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

app.listen(3001, '127.0.0.1', () => console.log('push service on 3001'));
