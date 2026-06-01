import {
    BedrockClient,
    CreateEvaluationJobCommand,
    GetEvaluationJobCommand,
    ListEvaluationJobsCommand,
} from "@aws-sdk/client-bedrock";
import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getRuntimeConfig } from "../runtime-config";
import { getAwsCredentials } from "./agentcore-ws";

export interface EvalQuestion {
    question: string;
    expected_answer?: string;
    context?: string;
}

export interface EvalJobSummary {
    jobId: string;
    jobName: string;
    status: string;
    createdAt: Date;
}

export interface EvalMetricResult {
    metricName: string;
    score: number;
}

export interface EvalQuestionResult {
    question: string;
    generatedAnswer: string;
    metrics: EvalMetricResult[];
}

export interface EvalResults {
    aggregateScores: EvalMetricResult[];
    perQuestion: EvalQuestionResult[];
}

export const ALL_METRICS = [
    "Builtin.Correctness",
    "Builtin.Completeness",
    "Builtin.Helpfulness",
    "Builtin.LogicalCoherence",
    "Builtin.Faithfulness",
    "Builtin.ContextRelevance",
    "Builtin.ContextCoverage",
];

export const DEFAULT_METRICS = ["Builtin.Faithfulness", "Builtin.Correctness", "Builtin.Completeness"];

function getBedrockClient(credentials: any): BedrockClient {
    const config = getRuntimeConfig();
    return new BedrockClient({
        region: config.cognitoRegion,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
    });
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
 * Convert user questions to Bedrock JSONL format and upload to S3.
 */
export async function uploadEvalDataset(
    questions: EvalQuestion[],
    jobId: string,
    userEmail: string,
    idToken: string,
): Promise<string> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const jsonl = questions.map(q => {
        const entry: any = {
            conversationTurnContent: {
                prompt: { content: [{ text: q.question }] },
            },
        };
        if (q.expected_answer) {
            entry.conversationTurnContent.referenceResponse = {
                content: [{ text: q.expected_answer }],
            };
        }
        return JSON.stringify(entry);
    }).join("\n");

    const key = `evaluations/${userEmail}/${jobId}/input.jsonl`;
    await s3.send(new PutObjectCommand({
        Bucket: config.dataBucketName,
        Key: key,
        Body: jsonl,
        ContentType: "application/jsonl",
    }));

    return `s3://${config.dataBucketName}/${key}`;
}

/**
 * Create a Bedrock evaluation job for our Knowledge Base.
 */
export async function createEvalJob(
    jobName: string,
    datasetS3Uri: string,
    outputPrefix: string,
    metrics: string[],
    idToken: string,
): Promise<string> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const bedrock = getBedrockClient(credentials);

    const response = await bedrock.send(new CreateEvaluationJobCommand({
        jobName,
        roleArn: config.evalRoleArn,
        applicationType: "RagEvaluation",
        evaluationConfig: {
            automated: {
                datasetMetricConfigs: [
                    {
                        taskType: "General",
                        dataset: { name: jobName, datasetLocation: { s3Uri: datasetS3Uri } },
                        metricNames: metrics,
                    },
                ],
            },
        },
        inferenceConfig: {
            ragConfigs: [
                {
                    knowledgeBaseConfig: {
                        retrieveAndGenerateConfig: {
                            type: "KNOWLEDGE_BASE",
                            knowledgeBaseConfiguration: {
                                knowledgeBaseId: config.knowledgeBaseId,
                                modelArn: `arn:aws:bedrock:${config.cognitoRegion}::foundation-model/anthropic.claude-sonnet-4-6-v1:0`,
                            },
                        },
                    },
                },
            ],
        },
        outputDataConfig: {
            s3Uri: outputPrefix,
        },
    }));

    return response.jobIdentifier!;
}

/**
 * Get evaluation job status.
 */
export async function getEvalJob(jobId: string, idToken: string): Promise<EvalJobSummary> {
    const credentials = await getAwsCredentials(idToken);
    const bedrock = getBedrockClient(credentials);

    const response = await bedrock.send(new GetEvaluationJobCommand({
        jobIdentifier: jobId,
    }));

    return {
        jobId: response.jobArn || jobId,
        jobName: response.jobName || "",
        status: response.status || "Unknown",
        createdAt: response.creationTime || new Date(),
    };
}

/**
 * List recent evaluation jobs.
 */
export async function listEvalJobs(idToken: string): Promise<EvalJobSummary[]> {
    const credentials = await getAwsCredentials(idToken);
    const bedrock = getBedrockClient(credentials);

    const response = await bedrock.send(new ListEvaluationJobsCommand({
        maxResults: 20,
        sortBy: "CreationTime",
        sortOrder: "Descending",
    }));

    return (response.jobSummaries || []).map(job => ({
        jobId: job.jobArn || "",
        jobName: job.jobName || "",
        status: job.status || "Unknown",
        createdAt: job.creationTime || new Date(),
    }));
}

/**
 * Read evaluation results from S3 output location.
 */
export async function getEvalResults(
    userEmail: string,
    jobId: string,
    idToken: string,
): Promise<EvalResults | null> {
    const config = getRuntimeConfig();
    const credentials = await getAwsCredentials(idToken);
    const s3 = getS3Client(credentials);

    const key = `evaluations/${userEmail}/${jobId}/output/results.jsonl`;

    try {
        const response = await s3.send(new GetObjectCommand({
            Bucket: config.dataBucketName,
            Key: key,
        }));
        const content = await response.Body!.transformToString();
        const lines = content.trim().split("\n").map(l => JSON.parse(l));

        const aggregateMap: Record<string, number[]> = {};
        const perQuestion: EvalQuestionResult[] = [];

        for (const line of lines) {
            const question = line.conversationTurnContent?.prompt?.content?.[0]?.text || "";
            const answer = line.output?.text || "";
            const metricResults: EvalMetricResult[] = [];

            for (const [metricName, value] of Object.entries(line.scores || {})) {
                const score = typeof value === "number" ? value : parseFloat(value as string);
                metricResults.push({ metricName, score });
                if (!aggregateMap[metricName]) aggregateMap[metricName] = [];
                aggregateMap[metricName].push(score);
            }

            perQuestion.push({ question, generatedAnswer: answer, metrics: metricResults });
        }

        const aggregateScores = Object.entries(aggregateMap).map(([metricName, scores]) => ({
            metricName,
            score: scores.reduce((a, b) => a + b, 0) / scores.length,
        }));

        return { aggregateScores, perQuestion };
    } catch {
        return null;
    }
}
