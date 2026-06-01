/**
 * AgentCore WebSocket helper with SigV4 presigned URLs.
 *
 * Flow: Cognito ID token → Identity Pool → temp AWS creds → SigV4 presign → WebSocket
 */

import { CognitoIdentityClient, GetIdCommand, GetCredentialsForIdentityCommand } from "@aws-sdk/client-cognito-identity";
import { SignatureV4 } from "@smithy/signature-v4";
import { HttpRequest } from "@smithy/protocol-http";
import { Sha256 } from "@aws-crypto/sha256-js";
import { getRuntimeConfig } from "../runtime-config";

export interface AgentCoreMessage {
    type: string;
    text?: string;
    query?: string;
    sources?: any[];
    intent?: string;
    message?: string;
    [key: string]: any;
}

export type MessageHandler = (msg: AgentCoreMessage) => void;
export type ErrorHandler = (error: string) => void;
export type CloseHandler = () => void;

interface CachedCredentials {
    accessKeyId: string;
    secretAccessKey: string;
    sessionToken: string;
    expiration: number;
}

let cachedCreds: CachedCredentials | null = null;

export async function getAwsCredentials(idToken: string): Promise<CachedCredentials> {
    // Return cached creds if still valid (5min buffer)
    if (cachedCreds && cachedCreds.expiration > Date.now() + 300_000) {
        return cachedCreds;
    }

    const config = getRuntimeConfig();
    const region = config.cognitoRegion;
    const identityPoolId = config.cognitoIdentityPoolId;
    const userPoolId = config.cognitoUserPoolId;

    const cognitoIdentity = new CognitoIdentityClient({ region });
    const providerName = `cognito-idp.${region}.amazonaws.com/${userPoolId}`;

    // Step 1: Get identity ID
    const idResponse = await cognitoIdentity.send(new GetIdCommand({
        IdentityPoolId: identityPoolId,
        Logins: { [providerName]: idToken },
    }));

    // Step 2: Get temporary credentials
    const credResponse = await cognitoIdentity.send(new GetCredentialsForIdentityCommand({
        IdentityId: idResponse.IdentityId!,
        Logins: { [providerName]: idToken },
    }));

    const creds = credResponse.Credentials!;
    cachedCreds = {
        accessKeyId: creds.AccessKeyId!,
        secretAccessKey: creds.SecretKey!,
        sessionToken: creds.SessionToken!,
        expiration: creds.Expiration!.getTime(),
    };

    return cachedCreds;
}

async function presignWebSocketUrl(runtimeArn: string, credentials: CachedCredentials): Promise<string> {
    const config = getRuntimeConfig();
    const region = config.cognitoRegion;
    const host = `bedrock-agentcore.${region}.amazonaws.com`;
    const encodedArn = encodeURIComponent(runtimeArn);
    const sessionId = crypto.randomUUID();

    const url = new URL(`https://${host}/runtimes/${encodedArn}/ws`);
    url.searchParams.set("qualifier", "DEFAULT");
    url.searchParams.set("X-Amzn-Bedrock-AgentCore-Runtime-Session-Id", sessionId);

    // Build HTTP request for signing
    const request = new HttpRequest({
        method: "GET",
        protocol: "https:",
        hostname: host,
        path: `/runtimes/${encodedArn}/ws`,
        query: Object.fromEntries(url.searchParams.entries()),
        headers: {
            host: host,
        },
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

    // Convert to wss:// URL with signed query params
    const signedParams = new URLSearchParams();
    for (const [key, value] of Object.entries(presigned.query || {})) {
        signedParams.set(key, value as string);
    }

    return `wss://${host}${presigned.path}?${signedParams.toString()}`;
}

export function clearCredentialsCache(): void {
    cachedCreds = null;
}

export async function createAgentCoreWebSocket(
    runtimeArn: string,
    idToken: string,
    onMessage: MessageHandler,
    onError: ErrorHandler,
    onClose: CloseHandler,
): Promise<WebSocket> {
    // Exchange Cognito ID token for AWS credentials
    const credentials = await getAwsCredentials(idToken);

    // Presign the WebSocket URL
    const wsUrl = await presignWebSocketUrl(runtimeArn, credentials);

    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        try {
            const msg: AgentCoreMessage = JSON.parse(event.data);
            onMessage(msg);
        } catch {
            onMessage({ type: "token", text: event.data });
        }
    };

    ws.onerror = () => {
        onError("WebSocket connection error");
    };

    ws.onclose = () => {
        onClose();
    };

    return ws;
}
