/**
 * WhatsApp Baileys Bridge — Minimal Express server for the AI Assistant.
 *
 * WARNING: Uses unofficial WhatsApp Web protocol.
 * RISK: WhatsApp may ban the phone number used.
 * NEVER use your personal number — use a virtual/dedicated number only.
 *
 * Listens ONLY on 127.0.0.1:3001 (never exposed to the network).
 */

'use strict';

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  delay,
} = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const fs = require('fs');
const path = require('path');
const { Boom } = require('@hapi/boom');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PORT = parseInt(process.env.BRIDGE_PORT || '3001', 10);
const AUTH_DIR = path.join(__dirname, 'auth_info');
const MEDIA_DIR = path.join(__dirname, 'media');
const MAX_QUEUED_MESSAGES = 100;
const MAX_OUTGOING_PER_MINUTE = 10;
const MIN_SEND_DELAY_MS = 1000;
const MAX_SEND_DELAY_MS = 3000;

// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let sock = null;
let connectionStatus = 'disconnected';
let currentQR = null;
const messageQueue = [];          // incoming messages waiting to be fetched
let reconnectAttempts = 0;
const maxReconnectDelay = 60000;  // 60 seconds

// Rate limiter for outgoing messages
const outgoingSendTimestamps = [];

// Ensure directories exist
for (const dir of [AUTH_DIR, MEDIA_DIR]) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

// ---------------------------------------------------------------------------
// Rate limiter
// ---------------------------------------------------------------------------

function canSendMessage() {
  const now = Date.now();
  // Remove timestamps older than 60 seconds
  while (outgoingSendTimestamps.length > 0 && outgoingSendTimestamps[0] < now - 60000) {
    outgoingSendTimestamps.shift();
  }
  return outgoingSendTimestamps.length < MAX_OUTGOING_PER_MINUTE;
}

function recordSend() {
  outgoingSendTimestamps.push(Date.now());
}

/**
 * Random delay between messages to reduce ban risk.
 */
function randomDelay() {
  const ms = MIN_SEND_DELAY_MS + Math.random() * (MAX_SEND_DELAY_MS - MIN_SEND_DELAY_MS);
  return delay(Math.floor(ms));
}

// ---------------------------------------------------------------------------
// WhatsApp / Baileys connection
// ---------------------------------------------------------------------------

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  logger.info({ version }, 'Using Baileys version');

  sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    logger: pino({ level: 'silent' }), // Baileys internal logs silenced
    printQRInTerminal: false,           // We handle QR ourselves
    generateHighQualityLinkPreview: false,
  });

  // --- Connection updates ---
  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQR = qr;
      logger.info('New QR code generated — scan it with WhatsApp');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'open') {
      connectionStatus = 'connected';
      currentQR = null;
      reconnectAttempts = 0;
      logger.info('WhatsApp connection established');
    }

    if (connection === 'close') {
      connectionStatus = 'disconnected';

      const statusCode = (lastDisconnect?.error)?.output?.statusCode;
      const reason = (lastDisconnect?.error)?.output?.payload?.message || 'unknown';

      logger.warn({ statusCode, reason }, 'Connection closed');

      // If logged out, do NOT reconnect
      if (statusCode === DisconnectReason.loggedOut) {
        logger.error(
          '============================================================\n' +
          '  LOGGED OUT — Session invalidated by WhatsApp.\n' +
          '  Delete auth_info/ and scan the QR code again.\n' +
          '  If this keeps happening, your number may be banned.\n' +
          '============================================================'
        );
        // Clean auth state so next start shows QR
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        fs.mkdirSync(AUTH_DIR, { recursive: true });
        return;
      }

      // Exponential backoff reconnect
      reconnectAttempts++;
      const backoff = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
      logger.info({ backoff, attempt: reconnectAttempts }, 'Reconnecting…');
      setTimeout(connectToWhatsApp, backoff);
    }
  });

  // --- Credentials update ---
  sock.ev.on('creds.update', saveCreds);

  // --- Incoming messages ---
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      // Skip status broadcasts and own messages
      if (msg.key.remoteJid === 'status@broadcast') continue;
      if (msg.key.fromMe) continue;

      const from = msg.key.remoteJid || '';
      const pushName = msg.pushName || '';
      const timestamp = msg.messageTimestamp
        ? (typeof msg.messageTimestamp === 'number'
          ? msg.messageTimestamp
          : msg.messageTimestamp.low || 0)
        : 0;

      const entry = { from, pushName, timestamp, text: null, audioPath: null, imagePath: null, documentPath: null };

      // --- Text ---
      const textContent =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        null;

      if (textContent) {
        entry.text = textContent;
      }

      // --- Audio ---
      const audioMsg = msg.message?.audioMessage;
      if (audioMsg) {
        try {
          const buffer = await downloadMediaMessage(msg);
          const filename = `audio_${Date.now()}_${from.split('@')[0]}.ogg`;
          const filepath = path.join(MEDIA_DIR, filename);
          fs.writeFileSync(filepath, buffer);
          entry.audioPath = filepath;
          logger.info({ filepath }, 'Downloaded audio message');
        } catch (err) {
          logger.error({ err }, 'Failed to download audio message');
        }
      }

      // --- Image ---
      const imageMsg = msg.message?.imageMessage;
      if (imageMsg) {
        try {
          const buffer = await downloadMediaMessage(msg);
          const filename = `image_${Date.now()}_${from.split('@')[0]}.jpg`;
          const filepath = path.join(MEDIA_DIR, filename);
          fs.writeFileSync(filepath, buffer);
          entry.imagePath = filepath;
          entry.text = imageMsg.caption || null;
          logger.info({ filepath }, 'Downloaded image message');
        } catch (err) {
          logger.error({ err }, 'Failed to download image message');
        }
      }

      // --- Document ---
      const docMsg = msg.message?.documentMessage;
      if (docMsg) {
        try {
          const buffer = await downloadMediaMessage(msg);
          const ext = docMsg.fileName ? path.extname(docMsg.fileName) : '';
          const filename = `doc_${Date.now()}_${from.split('@')[0]}${ext}`;
          const filepath = path.join(MEDIA_DIR, filename);
          fs.writeFileSync(filepath, buffer);
          entry.documentPath = filepath;
          entry.text = docMsg.caption || null;
          logger.info({ filepath }, 'Downloaded document');
        } catch (err) {
          logger.error({ err }, 'Failed to download document');
        }
      }

      // Only queue if we got something useful
      if (entry.text || entry.audioPath || entry.imagePath || entry.documentPath) {
        messageQueue.push(entry);
        // Cap queue size
        while (messageQueue.length > MAX_QUEUED_MESSAGES) {
          messageQueue.shift();
        }
        logger.info({ from, type: entry.audioPath ? 'audio' : entry.imagePath ? 'image' : entry.documentPath ? 'document' : 'text' }, 'Message queued');
      }
    }
  });
}

/**
 * Download media from a message using Baileys' built-in download.
 */
async function downloadMediaMessage(msg) {
  const { downloadMediaMessage: dlMedia } = require('@whiskeysockets/baileys');
  return await dlMedia(msg, 'buffer', {});
}

// ---------------------------------------------------------------------------
// Express API
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

// --- Health check ---
app.get('/health', (_req, res) => {
  res.json({ status: connectionStatus });
});

// --- Get queued messages (and clear them) ---
app.get('/messages', (_req, res) => {
  const msgs = messageQueue.splice(0, messageQueue.length);
  res.json(msgs);
});

// --- Current QR code ---
app.get('/qr', (_req, res) => {
  if (!currentQR) {
    res.json({ qr: null, message: connectionStatus === 'connected' ? 'Already connected' : 'No QR available yet' });
    return;
  }
  res.json({ qr: currentQR });
});

// --- Send text ---
app.post('/send/text', async (req, res) => {
  const { phone, message } = req.body || {};
  if (!phone || !message) {
    return res.status(400).json({ error: 'phone and message are required' });
  }
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'WhatsApp not connected' });
  }
  if (!canSendMessage()) {
    return res.status(429).json({ error: 'Rate limit exceeded (max 10/min)' });
  }

  try {
    await randomDelay();
    const jid = formatJid(phone);
    await sock.sendMessage(jid, { text: message });
    recordSend();
    logger.info({ phone }, 'Text message sent');
    res.json({ success: true });
  } catch (err) {
    logger.error({ err, phone }, 'Failed to send text');
    res.status(500).json({ error: err.message });
  }
});

// --- Send audio ---
app.post('/send/audio', async (req, res) => {
  const { phone, audioPath } = req.body || {};
  if (!phone || !audioPath) {
    return res.status(400).json({ error: 'phone and audioPath are required' });
  }
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'WhatsApp not connected' });
  }
  if (!canSendMessage()) {
    return res.status(429).json({ error: 'Rate limit exceeded (max 10/min)' });
  }
  if (!fs.existsSync(audioPath)) {
    return res.status(404).json({ error: `File not found: ${audioPath}` });
  }

  try {
    await randomDelay();
    const jid = formatJid(phone);
    await sock.sendMessage(jid, {
      audio: fs.readFileSync(audioPath),
      mimetype: 'audio/ogg; codecs=opus',
      ptt: true,  // send as voice note
    });
    recordSend();
    logger.info({ phone, audioPath }, 'Audio message sent');
    res.json({ success: true });
  } catch (err) {
    logger.error({ err, phone }, 'Failed to send audio');
    res.status(500).json({ error: err.message });
  }
});

// --- Send document ---
app.post('/send/document', async (req, res) => {
  const { phone, path: filePath, caption } = req.body || {};
  if (!phone || !filePath) {
    return res.status(400).json({ error: 'phone and path are required' });
  }
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'WhatsApp not connected' });
  }
  if (!canSendMessage()) {
    return res.status(429).json({ error: 'Rate limit exceeded (max 10/min)' });
  }
  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: `File not found: ${filePath}` });
  }

  try {
    await randomDelay();
    const jid = formatJid(phone);
    const filename = path.basename(filePath);
    await sock.sendMessage(jid, {
      document: fs.readFileSync(filePath),
      fileName: filename,
      caption: caption || undefined,
      mimetype: 'application/octet-stream',
    });
    recordSend();
    logger.info({ phone, filePath }, 'Document sent');
    res.json({ success: true });
  } catch (err) {
    logger.error({ err, phone }, 'Failed to send document');
    res.status(500).json({ error: err.message });
  }
});

// --- Send typing indicator ---
app.post('/send/typing', async (req, res) => {
  const { phone } = req.body || {};
  if (!phone) {
    return res.status(400).json({ error: 'phone is required' });
  }
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'WhatsApp not connected' });
  }

  try {
    const jid = formatJid(phone);
    await sock.sendPresenceUpdate('composing', jid);
    res.json({ success: true });
  } catch (err) {
    logger.error({ err, phone }, 'Failed to send typing indicator');
    res.status(500).json({ error: err.message });
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a phone number to WhatsApp JID.
 * Strips + prefix and appends @s.whatsapp.net.
 */
function formatJid(phone) {
  const cleaned = phone.replace(/[^0-9]/g, '');
  return `${cleaned}@s.whatsapp.net`;
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main() {
  logger.info('Starting WhatsApp Baileys Bridge…');

  // Start Express first so health endpoint is available
  app.listen(PORT, '127.0.0.1', () => {
    logger.info({ port: PORT, host: '127.0.0.1' }, 'Bridge HTTP server listening');
  });

  // Connect to WhatsApp
  await connectToWhatsApp();
}

main().catch((err) => {
  logger.fatal({ err }, 'Fatal error starting bridge');
  process.exit(1);
});
