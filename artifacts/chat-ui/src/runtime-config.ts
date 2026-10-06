export interface RuntimeConfig {
    cognitoUserPoolId: string;
    cognitoClientId: string;
    cognitoIdentityPoolId: string;
    cognitoRegion: string;
    ragRuntimeArn: string;
    multiAgentRuntimeArn: string;
    // Base URL of the authenticated API. The bucket name, knowledge base id and
    // evaluation role ARN used to live here too, for browser-side S3 and Bedrock
    // calls; those calls now go through the API, which does the per-user checks.
    apiUrl: string;
}

let cachedConfig: RuntimeConfig | null = null;

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
    if (cachedConfig) return cachedConfig;
    const response = await fetch("/runtime-config.json");
    if (!response.ok) {
        throw new Error("Failed to load runtime-config.json");
    }
    cachedConfig = await response.json();
    return cachedConfig!;
}

export function getRuntimeConfig(): RuntimeConfig {
    if (!cachedConfig) {
        throw new Error("Runtime config not loaded. Call loadRuntimeConfig() first.");
    }
    return cachedConfig;
}
