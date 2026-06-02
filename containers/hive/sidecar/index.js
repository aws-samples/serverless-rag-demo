import express from 'express';
import { WhatsAppClient } from './whatsapp.js';

const app = express();
app.use(express.json());

const PORT = process.env.SIDECAR_PORT || 3001;
const HIVE_CORE_URL = process.env.HIVE_CORE_URL || 'http://localhost:8080';

let waClient = null;

app.post('/whatsapp/init', async (req, res) => {
    const { authStatePath } = req.body;
    try {
        waClient = new WhatsAppClient(authStatePath, HIVE_CORE_URL);
        const qrCode = await waClient.connect();
        res.json({ status: 'connecting', qr_code: qrCode });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/whatsapp/send', async (req, res) => {
    const { to, message } = req.body;
    if (!waClient) return res.status(400).json({ error: 'WhatsApp not initialized' });
    try {
        await waClient.sendMessage(to, message);
        res.json({ status: 'sent' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/whatsapp/status', (req, res) => {
    res.json({ connected: waClient?.isConnected() ?? false, phone: waClient?.phoneNumber ?? null });
});

app.get('/health', (req, res) => res.json({ status: 'ok' }));

app.listen(PORT, () => console.log(`Hive sidecar listening on port ${PORT}`));
