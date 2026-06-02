const express = require("express");
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");
const QRCode = require("qrcode");
const pino = require("pino");
const path = require("path");

const app = express();
app.use(express.json());

const PORT = 3001;
const PYTHON_APP_URL = "http://localhost:8080";
const logger = pino({ level: "info" });

let sock = null;
let currentQR = null;
let connected = false;
let phoneNumber = "";
let authStatePath = "/tmp/wa-auth";

async function startConnection() {
    const { state, saveCreds } = await useMultiFileAuthState(authStatePath);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            currentQR = await QRCode.toDataURL(qr);
            logger.info("QR code generated");
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "qr", qr: currentQR }),
            }).catch(() => {});
        }

        if (connection === "close") {
            connected = false;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            logger.info({ statusCode, shouldReconnect }, "Connection closed");
            if (shouldReconnect) {
                setTimeout(startConnection, 3000);
            }
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "disconnected", logged_out: !shouldReconnect }),
            }).catch(() => {});
        }

        if (connection === "open") {
            connected = true;
            currentQR = null;
            phoneNumber = sock.user?.id?.split(":")[0] || "";
            logger.info({ phoneNumber }, "Connected to WhatsApp");
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "connected", phone: phoneNumber }),
            }).catch(() => {});
        }
    });

    sock.ev.on("messages.upsert", async ({ messages }) => {
        for (const msg of messages) {
            if (msg.key.fromMe || !msg.message) continue;
            const text = msg.message.conversation
                || msg.message.extendedTextMessage?.text
                || "";
            if (!text) continue;

            const from = msg.key.remoteJid;
            const fromName = msg.pushName || "";
            const isGroup = from.endsWith("@g.us");

            fetch(`${PYTHON_APP_URL}/internal/wa-message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    from,
                    from_name: fromName,
                    message: text,
                    timestamp: Math.floor(Date.now() / 1000),
                    is_group: isGroup,
                    group_id: isGroup ? from : null,
                }),
            }).catch((err) => logger.error({ err }, "Failed to forward message"));
        }
    });
}

// REST API
app.post("/init", async (req, res) => {
    if (req.body.authStatePath) {
        authStatePath = req.body.authStatePath;
    }
    try {
        await startConnection();
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (connected) {
            res.json({ status: "connected", phone: phoneNumber });
        } else if (currentQR) {
            res.json({ status: "qr_needed", qr: currentQR });
        } else {
            res.json({ status: "connecting" });
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post("/send", async (req, res) => {
    const { to, message } = req.body;
    if (!sock || !connected) {
        return res.status(503).json({ success: false, error: "Not connected" });
    }
    try {
        await sock.sendMessage(to, { text: message });
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.get("/status", (req, res) => {
    res.json({ connected, phone: phoneNumber });
});

app.get("/qr", (req, res) => {
    res.json({ qr: currentQR });
});

app.post("/shutdown", async (req, res) => {
    if (sock) {
        sock.end();
        sock = null;
    }
    connected = false;
    res.json({ success: true });
});

app.listen(PORT, "127.0.0.1", () => {
    logger.info({ port: PORT }, "WhatsApp sidecar ready");
});
