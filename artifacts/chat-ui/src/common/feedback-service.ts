// src/common/feedback-service.ts
import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { getRuntimeConfig } from "../runtime-config";
import { getAwsCredentials } from "./agentcore-ws";

export interface FeedbackEntry {
    timestamp: string;
    userEmail: string;
    question: string;
    answer: string;
    sources: string[];
    rating: "up" | "down";
}

function getS3Client(credentials: any): S3Client {
    const config = getRuntimeConfig();
    return new S3Client({
        region: config.cognitoRegion,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
    });
}

/**
 * Append a feedback entry to the daily JSONL file.
 * Creates the file if it doesn't exist, appends if it does.
 */
export async function submitFeedback(
    entry: FeedbackEntry,
    idToken: string,
): Promise<void> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const today = new Date().toISOString().split("T")[0];
    const key = `feedback/${today}.jsonl`;

    // Try to read existing file
    let existing = "";
    try {
        const response = await s3.send(new GetObjectCommand({
            Bucket: config.dataBucketName,
            Key: key,
        }));
        existing = await response.Body!.transformToString();
    } catch {
        // File doesn't exist yet, start fresh
    }

    // Append new entry
    const newContent = existing + JSON.stringify(entry) + "\n";

    await s3.send(new PutObjectCommand({
        Bucket: config.dataBucketName,
        Key: key,
        Body: newContent,
        ContentType: "application/jsonl",
    }));
}
