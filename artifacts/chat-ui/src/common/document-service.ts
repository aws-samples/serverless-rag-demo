/**
 * Document management service using presigned URLs.
 * Handles upload, list, and delete operations against the KB data bucket.
 */

import { S3Client, ListObjectsV2Command, PutObjectCommand, DeleteObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { BedrockAgentClient, StartIngestionJobCommand, ListIngestionJobsCommand } from "@aws-sdk/client-bedrock-agent";
import { getRuntimeConfig } from "../runtime-config";
import { getAwsCredentials } from "./agentcore-ws";

export interface DocumentInfo {
    key: string;
    fileName: string;
    userEmail: string;
    size: number;
    lastModified: Date;
    isOwner: boolean;
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
 * List documents in the KB bucket.
 * @param userEmail - current user's email
 * @param idToken - Cognito ID token for credential exchange
 * @param globalView - if true, list all users' docs; if false, only current user's
 */
export async function listDocuments(
    userEmail: string,
    idToken: string,
    globalView: boolean = false,
): Promise<DocumentInfo[]> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const prefix = globalView ? "documents/" : `documents/${userEmail}/`;

    const docs: DocumentInfo[] = [];
    let continuationToken: string | undefined;

    do {
        const response = await s3.send(new ListObjectsV2Command({
            Bucket: config.dataBucketName,
            Prefix: prefix,
            ContinuationToken: continuationToken,
        }));

        for (const obj of response.Contents || []) {
        const key = obj.Key || "";
        // Skip metadata sidecar files
        if (key.endsWith(".metadata.json")) continue;
        // Skip folder markers
        if (key.endsWith("/")) continue;

        // Extract user email from path: documents/{email}/{filename}
        const parts = key.replace("documents/", "").split("/");
        const ownerEmail = parts[0];
        const fileName = parts.slice(1).join("/");

        docs.push({
            key,
            fileName,
            userEmail: ownerEmail,
            size: obj.Size || 0,
            lastModified: obj.LastModified || new Date(),
            isOwner: ownerEmail === userEmail,
        });
        }

        continuationToken = response.IsTruncated ? response.NextContinuationToken : undefined;
    } while (continuationToken);

    return docs;
}

/**
 * Get a presigned URL for uploading a document.
 */
export async function getUploadPresignedUrl(
    userEmail: string,
    fileName: string,
    contentType: string,
    idToken: string,
): Promise<string> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const key = `documents/${userEmail}/${fileName}`;
    const command = new PutObjectCommand({
        Bucket: config.dataBucketName,
        Key: key,
        ContentType: contentType,
    });

    return getSignedUrl(s3, command, { expiresIn: 300 });
}

/**
 * Upload metadata sidecar file for a document.
 */
export async function uploadMetadata(
    userEmail: string,
    fileName: string,
    idToken: string,
): Promise<void> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const metadataKey = `documents/${userEmail}/${fileName}.metadata.json`;
    const metadata = {
        metadataAttributes: {
            user_email: userEmail,
        },
    };

    await s3.send(new PutObjectCommand({
        Bucket: config.dataBucketName,
        Key: metadataKey,
        Body: JSON.stringify(metadata),
        ContentType: "application/json",
    }));
}

/**
 * Delete a document and its metadata sidecar.
 */
export async function deleteDocument(
    key: string,
    idToken: string,
): Promise<void> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    // Delete the document
    await s3.send(new DeleteObjectCommand({
        Bucket: config.dataBucketName,
        Key: key,
    }));

    // Delete the metadata sidecar
    await s3.send(new DeleteObjectCommand({
        Bucket: config.dataBucketName,
        Key: `${key}.metadata.json`,
    }));
}

/**
 * Get a presigned URL for downloading/viewing a document.
 */
export async function getDownloadPresignedUrl(
    key: string,
    idToken: string,
): Promise<string> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const command = new GetObjectCommand({
        Bucket: config.dataBucketName,
        Key: key,
    });

    return getSignedUrl(s3, command, { expiresIn: 300 });
}

export interface IngestionStatus {
    status: string; // STARTING | IN_PROGRESS | COMPLETE | FAILED | STOPPING | STOPPED
    startedAt?: Date;
    updatedAt?: Date;
    documentsScanned?: number;
    documentsIndexed?: number;
    documentsFailed?: number;
}

/**
 * Get the latest ingestion job status for the KB.
 */
export async function getIngestionStatus(idToken: string): Promise<IngestionStatus | null> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);

    const client = new BedrockAgentClient({
        region: config.cognitoRegion,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
    });

    const response = await client.send(new ListIngestionJobsCommand({
        knowledgeBaseId: config.knowledgeBaseId,
        dataSourceId: config.dataSourceId,
        maxResults: 1,
        sortBy: { attribute: "STARTED_AT", order: "DESCENDING" },
    }));

    const job = response.ingestionJobSummaries?.[0];
    if (!job) return null;

    return {
        status: job.status || "Unknown",
        startedAt: job.startedAt,
        updatedAt: job.updatedAt,
        documentsScanned: job.statistics?.numberOfDocumentsScanned,
        documentsIndexed: job.statistics?.numberOfNewDocumentsIndexed,
        documentsFailed: job.statistics?.numberOfDocumentsFailed,
    };
}

/**
 * Trigger KB ingestion job after upload/delete to sync the index.
 */
export async function syncKnowledgeBase(idToken: string): Promise<void> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);

    const client = new BedrockAgentClient({
        region: config.cognitoRegion,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
    });

    await client.send(new StartIngestionJobCommand({
        knowledgeBaseId: config.knowledgeBaseId,
        dataSourceId: config.dataSourceId,
    }));
}
