import makeWASocket, { useMultiFileAuthState, DisconnectReason } from '@whiskeysockets/baileys';
import pino from 'pino';

const logger = pino({ level: 'warn' });

export class WhatsAppClient {
    constructor(authStatePath, hiveCoreUrl) {
        this.authStatePath = authStatePath;
        this.hiveCoreUrl = hiveCoreUrl;
        this.sock = null;
        this.phoneNumber = null;
        this._connected = false;
    }

    isConnected() { return this._connected; }

    async connect() {
        const { state, saveCreds } = await useMultiFileAuthState(this.authStatePath);
        let qrCode = null;

        this.sock = makeWASocket({ auth: state, logger, printQRInTerminal: false });

        this.sock.ev.on('connection.update', (update) => {
            const { connection, qr, lastDisconnect } = update;
            if (qr) qrCode = qr;
            if (connection === 'open') {
                this._connected = true;
                this.phoneNumber = this.sock.user?.id?.split(':')[0] || null;
            }
            if (connection === 'close') {
                this._connected = false;
                const reason = lastDisconnect?.error?.output?.statusCode;
                if (reason !== DisconnectReason.loggedOut) setTimeout(() => this.connect(), 5000);
            }
        });

        this.sock.ev.on('creds.update', saveCreds);

        this.sock.ev.on('messages.upsert', async ({ messages }) => {
            for (const msg of messages) {
                if (msg.key.fromMe) continue;
                const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || '';
                if (!text) continue;
                try {
                    await fetch(`${this.hiveCoreUrl}/channel/incoming`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ channel_id: 'whatsapp', from: msg.key.remoteJid, text, timestamp: msg.messageTimestamp }),
                    });
                } catch (err) { console.error('Forward to Hive failed:', err); }
            }
        });

        await new Promise(resolve => setTimeout(resolve, 2000));
        return qrCode;
    }

    async sendMessage(to, text) {
        if (!this.sock || !this._connected) throw new Error('WhatsApp not connected');
        const jid = to.includes('@') ? to : `${to}@s.whatsapp.net`;
        await this.sock.sendMessage(jid, { text });
    }
}
