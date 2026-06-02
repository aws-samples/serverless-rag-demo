import { getAwsCredentials } from "./agentcore-ws";
import { getRuntimeConfig } from "../runtime-config";
import { SignatureV4 } from "@smithy/signature-v4";
import { HttpRequest } from "@smithy/protocol-http";
import { Sha256 } from "@aws-crypto/sha256-js";
import { HiveMessage, HiveResponse } from "../components/hive/types";

export type HiveMessageHandler = (msg: HiveResponse) => void;

let hiveSocket: WebSocket | null = null;

async function presignHiveWebSocketUrl(idToken: string): Promise<string> {
    const config = getRuntimeConfig();
    const region = config.cognitoRegion;
    const runtimeArn = config.hiveRuntimeArn!;
    const credentials = await getAwsCredentials(idToken);

    const host = `bedrock-agentcore.${region}.amazonaws.com`;
    const encodedArn = encodeURIComponent(runtimeArn);
    const sessionId = crypto.randomUUID();

    const url = new URL(`https://${host}/runtimes/${encodedArn}/ws`);
    url.searchParams.set("qualifier", "DEFAULT");
    url.searchParams.set("X-Amzn-Bedrock-AgentCore-Runtime-Session-Id", sessionId);

    const request = new HttpRequest({
        method: "GET",
        protocol: "https:",
        hostname: host,
        path: `/runtimes/${encodedArn}/ws`,
        query: Object.fromEntries(url.searchParams.entries()),
        headers: { host },
    });

    const signer = new SignatureV4({
        service: "bedrock-agentcore",
        region,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
        sha256: Sha256,
    });

    const presigned = await signer.presign(request, { expiresIn: 3600 });
    const signedParams = new URLSearchParams();
    for (const [key, value] of Object.entries(presigned.query || {})) {
        signedParams.set(key, value as string);
    }
    return `wss://${host}${presigned.path}?${signedParams.toString()}`;
}

export async function connectHive(
    idToken: string,
    userId: string,
    onMessage: HiveMessageHandler,
    onError: (error: string) => void,
    onClose: () => void,
): Promise<WebSocket> {
    const wsUrl = await presignHiveWebSocketUrl(idToken);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        sendHiveMessage(ws, { type: "init", user_id: userId });
    };
    ws.onmessage = (event) => {
        try {
            onMessage(JSON.parse(event.data));
        } catch {
            onMessage({ type: "error", message: "Failed to parse message" });
        }
    };
    ws.onerror = () => onError("Hive WebSocket error");
    ws.onclose = onClose;

    hiveSocket = ws;
    return ws;
}

export function sendHiveMessage(ws: WebSocket, message: HiveMessage) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
    }
}

export function getHiveSocket(): WebSocket | null {
    return hiveSocket;
}
