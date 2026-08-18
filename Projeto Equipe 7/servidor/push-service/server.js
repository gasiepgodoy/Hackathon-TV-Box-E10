// Microserviço de saída do SecBox: push (FCM) e e-mail (SMTP).
//
// O Node-RED chama:
//   POST http://localhost:3001/send { tokens, title, body }   -> push
//   POST http://localhost:3001/mail { to, name, code, purpose } -> e-mail
//
// Requer a chave de serviço do Firebase em ./secbox-sa.json (NÃO versionada).
// Instalação (Node 18): npm install firebase-admin@12 express nodemailer
//   (firebase-admin@14 exige Node>=22 e mudou a API; a v12 funciona no Node 18.)
//
// SMTP vem do ambiente, nunca do código — ver .env.example:
//   SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS SMTP_FROM

const express = require('express');
const admin = require('firebase-admin');
const nodemailer = require('nodemailer');
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

// --- e-mail -----------------------------------------------------------------

// Criado uma vez só: abrir conexão SMTP a cada envio é lento e alguns
// provedores tratam a rajada de conexões como abuso.
const mailer = process.env.SMTP_HOST
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT || 587),
      secure: Number(process.env.SMTP_PORT) === 465,
      auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
    })
  : null;

const TEXTOS = {
  verify: {
    assunto: 'Confirme seu e-mail no SecBox',
    linha: 'Use o código abaixo para confirmar seu e-mail no aplicativo:',
  },
  reset: {
    assunto: 'Redefinição de senha do SecBox',
    linha: 'Use o código abaixo no aplicativo para cadastrar uma nova senha:',
  },
};

app.post('/mail', async (req, res) => {
  const { to, name, code, purpose } = req.body;
  const t = TEXTOS[purpose];
  if (!t) return res.status(400).json({ error: 'purpose invalido' });
  if (!to || !code) return res.status(400).json({ error: 'faltam to/code' });
  if (!mailer) return res.status(503).json({ error: 'SMTP nao configurado' });

  const ola = name ? `Olá, ${name}.` : 'Olá.';
  const texto =
    `${ola}\n\n${t.linha}\n\n    ${code}\n\n` +
    `O código vale por 15 minutos e só pode ser usado uma vez.\n` +
    `Se não foi você quem pediu, ignore esta mensagem — nada muda na sua conta.\n\n` +
    `— SecBox`;

  try {
    const info = await mailer.sendMail({
      from: process.env.SMTP_FROM || process.env.SMTP_USER,
      to,
      subject: t.assunto,
      text: texto,
    });
    // O código nunca vai para o log: quem lê o journal não pode entrar na conta.
    console.log(`mail ${purpose} -> ${to} (${info.messageId})`);
    res.json({ ok: true });
  } catch (e) {
    console.error(`mail ${purpose} -> ${to} FALHOU: ${e.message}`);
    res.status(500).json({ error: String(e) });
  }
});

app.listen(3001, '127.0.0.1', () =>
  console.log(`secbox out on 3001 (smtp: ${mailer ? 'ok' : 'desligado'})`));
