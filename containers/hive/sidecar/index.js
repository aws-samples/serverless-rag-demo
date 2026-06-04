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

// In-memory message store (per contact, capped at 50 messages each)
const MAX_MESSAGES_PER_CONTACT = 50;
const messageStore = {}; // { "jid": [{from, text, timestamp, fromMe}] }

// Bidirectional LID <-> phone JID mapping (populated from contacts events)
const lidToPhone = {}; // { "12345@lid": "61412345678@s.whatsapp.net" }
const phoneToLid = {}; // { "61412345678@s.whatsapp.net": "12345@lid" }

// Contact name store: YOUR saved name for each contact (address book name)
const contactNames = {}; // { "jid_or_lid": "Fraser Aus" }

function storeMessage(jid, text, timestamp, fromMe, fromName = "") {
    if (!messageStore[jid]) messageStore[jid] = [];
    const entry = { from: fromMe ? "me" : fromName || jid, text, timestamp, fromMe };
    messageStore[jid].push(entry);
    if (messageStore[jid].length > MAX_MESSAGES_PER_CONTACT) {
        messageStore[jid] = messageStore[jid].slice(-MAX_MESSAGES_PER_CONTACT);
    }
    // Also store under alternate JID so both LID and phone queries work
    const altJid = lidToPhone[jid] || phoneToLid[jid];
    if (altJid && altJid !== jid) {
        if (!messageStore[altJid]) messageStore[altJid] = [];
        messageStore[altJid].push(entry);
        if (messageStore[altJid].length > MAX_MESSAGES_PER_CONTACT) {
            messageStore[altJid] = messageStore[altJid].slice(-MAX_MESSAGES_PER_CONTACT);
        }
    }
}
let connected = false;
let phoneNumber = "";
let authStatePath = "/tmp/wa-auth";

async function startConnection() {
    // Close previous socket to prevent duplicate connections
    if (sock) {
        try { sock.end(); } catch (e) {}
        sock = null;
    }

    const { state, saveCreds } = await useMultiFileAuthState(authStatePath);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
        syncFullHistory: true,
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
            const loggedOut = statusCode === DisconnectReason.loggedOut;
            logger.info({ statusCode, loggedOut }, "Connection closed");

            if (loggedOut) {
                // Auth expired/revoked — clear state and reconnect for fresh QR
                const fs = require("fs");
                fs.rmSync(authStatePath, { recursive: true, force: true });
                fs.mkdirSync(authStatePath, { recursive: true });
                logger.info("Auth state cleared, reconnecting for fresh QR");
                setTimeout(startConnection, 1000);
            } else if (statusCode === 440) {
                // Session replaced by another connection — do NOT reconnect (would loop)
                logger.info("Session replaced (440), stopping reconnection");
            } else {
                // Transient error — retry
                setTimeout(startConnection, 3000);
            }

            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "disconnected", logged_out: loggedOut }),
            }).catch(() => {});
        }

        if (connection === "open") {
            connected = true;
            currentQR = null;
            phoneNumber = sock.user?.id?.split(":")[0] || "";
            console.log(`[SIDECAR] Connected to WhatsApp: ${phoneNumber}`);
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "connected", phone: phoneNumber }),
            }).catch(() => {});
        }
    });

    // Track contacts: bidirectional LID <-> phone JID mapping + saved names
    sock.ev.on("contacts.upsert", (contacts) => {
        for (const contact of contacts) {
            if (contact.lid && contact.id && contact.id.endsWith("@s.whatsapp.net")) {
                lidToPhone[contact.lid] = contact.id;
                phoneToLid[contact.id] = contact.lid;
            }
            // Store YOUR saved contact name (address book name)
            const savedName = contact.name || contact.notify || "";
            if (savedName) {
                if (contact.id) contactNames[contact.id] = savedName;
                if (contact.lid) contactNames[contact.lid] = savedName;
            }
        }
        console.log(`[SIDECAR] Contact store: ${Object.keys(lidToPhone).length} LID mappings, ${Object.keys(contactNames).length} names`);
    });

    sock.ev.on("contacts.update", (contacts) => {
        for (const contact of contacts) {
            if (contact.lid && contact.id && contact.id.endsWith("@s.whatsapp.net")) {
                lidToPhone[contact.lid] = contact.id;
                phoneToLid[contact.id] = contact.lid;
            }
            const savedName = contact.name || contact.notify || "";
            if (savedName) {
                if (contact.id) contactNames[contact.id] = savedName;
                if (contact.lid) contactNames[contact.lid] = savedName;
            }
        }
    });

    // History sync: capture messages and contacts from initial sync
    sock.ev.on("messaging-history.set", ({ messages: histMsgs, contacts: histContacts, isLatest }) => {
        console.log(`[SIDECAR] History sync: ${histMsgs.length} messages (isLatest=${isLatest})`);
        // Extract bidirectional LID<->phone mappings from synced contacts
        if (histContacts) {
            for (const contact of histContacts) {
                if (contact.lid && contact.id && contact.id.endsWith("@s.whatsapp.net")) {
                    lidToPhone[contact.lid] = contact.id;
                    phoneToLid[contact.id] = contact.lid;
                }
            }
        }
        for (const msg of histMsgs) {
            if (!msg.message) continue;
            const text = msg.message.conversation
                || msg.message.extendedTextMessage?.text
                || "";
            if (!text) continue;
            const from = msg.key.remoteJid;
            const fromName = msg.pushName || "";
            const ts = msg.messageTimestamp ? Number(msg.messageTimestamp) : Math.floor(Date.now() / 1000);
            storeMessage(from, text, ts, msg.key.fromMe, fromName);
        }
        console.log(`[SIDECAR] Message store: ${Object.keys(messageStore).length} contacts, LID map: ${Object.keys(lidToPhone).length}`);
    });

    sock.ev.on("messages.upsert", async ({ messages }) => {
        for (const msg of messages) {
            if (!msg.message) continue;
            const text = msg.message.conversation
                || msg.message.extendedTextMessage?.text
                || "";
            if (!text) continue;

            const from = msg.key.remoteJid;
            const fromName = msg.pushName || "";
            const isGroup = from.endsWith("@g.us");
            const ts = Math.floor(Date.now() / 1000);

            // Store all messages (incoming and outgoing)
            storeMessage(from, text, ts, msg.key.fromMe, fromName);

            if (msg.key.fromMe) continue; // Don't forward our own messages to Python

            // Resolve phone JID from LID mapping
            let resolvedPhone = "";
            if (from.endsWith("@lid") && lidToPhone[from]) {
                resolvedPhone = lidToPhone[from];
            } else if (from.endsWith("@s.whatsapp.net")) {
                resolvedPhone = from;
            }

            // Resolve saved contact name (your address book name for them)
            const savedName = contactNames[from] || contactNames[resolvedPhone] || "";

            fetch(`${PYTHON_APP_URL}/internal/wa-message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    from,
                    from_name: fromName,
                    saved_name: savedName || undefined,
                    phone_jid: resolvedPhone || undefined,
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
        storeMessage(to, message, Math.floor(Date.now() / 1000), true);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.get("/status", (req, res) => {
    res.json({ connected, phone: phoneNumber, lid_mappings: Object.keys(lidToPhone).length });
});

app.get("/resolve", (req, res) => {
    const { lid } = req.query;
    if (!lid) {
        return res.status(400).json({ error: "lid query param required" });
    }
    const phone = lidToPhone[lid] || null;
    res.json({ lid, phone });
});

app.get("/qr", (req, res) => {
    res.json({ qr: currentQR });
});

app.get("/messages", (req, res) => {
    const { jid, limit } = req.query;
    if (!jid) {
        return res.status(400).json({ error: "jid query param required" });
    }
    // Try exact match first, then alternate JID format (LID<->phone)
    let msgs = messageStore[jid];
    let resolvedJid = jid;
    if (!msgs || msgs.length === 0) {
        // Try LID → phone mapping
        const altJid = lidToPhone[jid] || phoneToLid[jid];
        if (altJid && messageStore[altJid]) {
            msgs = messageStore[altJid];
            resolvedJid = altJid;
        }
    }
    const n = parseInt(limit) || 20;
    res.json({ jid: resolvedJid, messages: (msgs || []).slice(-n) });
});

app.get("/contacts", (req, res) => {
    const contacts = Object.keys(messageStore).map((jid) => {
        const msgs = messageStore[jid];
        const last = msgs[msgs.length - 1];
        // Resolve alternate JID (LID→phone or phone→LID)
        const phoneJid = lidToPhone[jid] || (jid.endsWith("@s.whatsapp.net") ? jid : null);
        // Get name from message history (pushName)
        const nameFromMsgs = msgs.find((m) => !m.fromMe && m.from !== "me" && m.from !== jid)?.from;
        return {
            jid,
            phone_jid: phoneJid || null,
            name: nameFromMsgs || (phoneJid ? phoneJid.split("@")[0] : jid.split("@")[0]),
            last_message: last?.text?.slice(0, 50) || "",
            last_timestamp: last?.timestamp || 0,
            message_count: msgs.length,
        };
    });
    contacts.sort((a, b) => b.last_timestamp - a.last_timestamp);
    res.json({ contacts });
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
