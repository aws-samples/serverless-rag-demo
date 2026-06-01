# RAG Evaluation Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated Evaluation page using Bedrock Evals with reference-free and ground-truth modes, plus thumbs up/down feedback on chat responses.

**Architecture:** Browser calls Bedrock evaluation APIs directly via Identity Pool credentials. Evaluation datasets and results stored in S3 data bucket under `evaluations/` and `feedback/` prefixes. New top-level "Evaluation" page with dashboard.

**Tech Stack:** Bedrock Evaluation Jobs API (`@aws-sdk/client-bedrock`), S3 (existing data bucket), Cognito Identity Pool, Cloudscape UI (ExpandableSection, Cards, Table, Tabs, FileUpload).

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/common/evaluation-service.ts` | Bedrock eval job API calls (create, get, list) + S3 dataset/results I/O |
| `src/common/feedback-service.ts` | Thumbs up/down feedback writer (append JSONL to S3) |
| `src/pages/eval-page.tsx` | Top-level evaluation page with tabs for input + results |
| `src/components/eval-ui/eval-input.tsx` | Question input component (manual entry + file upload) |
| `src/components/eval-ui/eval-dashboard.tsx` | Results dashboard (aggregate scores + per-question table) |
| `src/components/chat-ui/chat-ui-message.tsx` | Modified: add thumbs up/down buttons |
| `src/components/chat-ui/types.tsx` | Modified: add feedback rating to ChatMessage |
| `src/pages/index.tsx` | Modified: export EvalPage |
| `src/app.tsx` | Modified: add route + nav item for Evaluation |
| `infrastructure/cognito_stack.py` | Modified: add eval + feedback IAM permissions |

---

### Task 1: Feedback Service

**Files:**
- Create: `artifacts/chat-ui/src/common/feedback-service.ts`

- [ ] **Step 1: Create feedback service**

```typescript
// artifacts/chat-ui/src/common/feedback-service.ts
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
```

- [ ] **Step 2: Verify build**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/common/feedback-service.ts
git commit -m "feat: add feedback service for thumbs up/down"
```

---

### Task 2: Thumbs Up/Down on Chat Messages

**Files:**
- Modify: `artifacts/chat-ui/src/components/chat-ui/chat-ui-message.tsx`
- Modify: `artifacts/chat-ui/src/components/chat-ui/types.tsx`

- [ ] **Step 1: Add rating field to ChatMessage type**

In `artifacts/chat-ui/src/components/chat-ui/types.tsx`, add `rating` to `ChatMessage`:

```typescript
export enum ChatMessageType {
  AI = "ai",
  Human = "human",
}

export interface SourceInfo {
  index: number;
  uri: string;
  excerpt?: string;
  presignedUrl?: string;
  fileName?: string;
}

export interface ChatMessage {
  type: ChatMessageType;
  content: string;
  sources?: SourceInfo[];
  rating?: "up" | "down" | null;
  question?: string; // the user question this response answers
}
```

- [ ] **Step 2: Add thumbs up/down buttons to chat-ui-message.tsx**

Add a `FeedbackButtons` component and render it on AI messages that have content. Import `Icon` from Cloudscape and `submitFeedback` from the feedback service.

At the top of `chat-ui-message.tsx`, add imports:
```typescript
import { useContext, useState } from "react";
import { AppContext } from "../../common/context";
import { submitFeedback } from "../../common/feedback-service";
```

Add the component (before `ChatUIMessage`):
```typescript
function FeedbackButtons({ message }: { message: ChatMessage }) {
  const [rating, setRating] = useState<"up" | "down" | null>(message.rating || null);
  const appData = useContext(AppContext);

  const handleRating = async (value: "up" | "down") => {
    const newRating = rating === value ? null : value;
    setRating(newRating);
    if (!newRating) return;

    const idToken = appData.userinfo?.tokens?.idToken?.toString() || "";
    const userEmail = appData.userinfo?.signInDetails?.loginId || appData.userinfo?.username || "";

    try {
      await submitFeedback({
        timestamp: new Date().toISOString(),
        userEmail,
        question: message.question || "",
        answer: message.content,
        sources: message.sources?.map(s => s.uri) || [],
        rating: newRating,
      }, idToken);
    } catch {
      // Silent fail — don't interrupt chat UX
    }
  };

  return (
    <Box margin={{ top: "xs" }} float="right">
      <SpaceBetween direction="horizontal" size="xs">
        <Button
          variant="inline-icon"
          iconName={rating === "up" ? "thumbs-up-filled" : "thumbs-up"}
          onClick={() => handleRating("up")}
        />
        <Button
          variant="inline-icon"
          iconName={rating === "down" ? "thumbs-down-filled" : "thumbs-down"}
          onClick={() => handleRating("down")}
        />
      </SpaceBetween>
    </Box>
  );
}
```

Then render it inside the AI message Container, after the `SourcesSection`:
```typescript
{props.message.content.length > 0 && (
  <FeedbackButtons message={props.message} />
)}
```

- [ ] **Step 3: Pass question context to AI messages**

In `artifacts/chat-ui/src/components/chat-ui/chat-ui-input-panel.tsx`, when sending the AI message, include the user's question. Update the `onSendMessage` call in the Human case to store the query, and in the `handleMessage` token/end cases, pass it through.

In `chat-page.tsx`, update the `sendMessage` function to track the last human question and attach it to AI messages:

```typescript
const sendMessage = (message: string, type: string, sources?: any[]) => {
    if (type === ChatMessageType.Human) {
      setMessages((prevMessages) => [
        ...prevMessages,
        { type: ChatMessageType.Human, content: message },
        {
          type: ChatMessageType.AI,
          content: "",
          question: message, // track which question this answers
        },
      ]);
    } else if (type === ChatMessageType.AI) {
      setMessages((prevMessages) => {
        const prev = prevMessages.slice(0, prevMessages.length - 1);
        const last = prevMessages[prevMessages.length - 1];
        return [
          ...prev,
          {
            ...last,
            content: message,
            sources,
          },
        ];
      });
      setRunning(false);
    }
```

- [ ] **Step 4: Verify build**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add artifacts/chat-ui/src/components/chat-ui/chat-ui-message.tsx artifacts/chat-ui/src/components/chat-ui/types.tsx artifacts/chat-ui/src/pages/chat-page.tsx
git commit -m "feat: add thumbs up/down feedback on chat messages"
```

---

### Task 3: Evaluation Service

**Files:**
- Create: `artifacts/chat-ui/src/common/evaluation-service.ts`

- [ ] **Step 1: Create evaluation service**

```typescript
// artifacts/chat-ui/src/common/evaluation-service.ts
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
    metrics?: string[];
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

const EVAL_METRICS_RAG = [
    "Builtin.Correctness",
    "Builtin.Completeness",
    "Builtin.Helpfulness",
    "Builtin.LogicalCoherence",
    "Builtin.Faithfulness",
];

const EVAL_METRICS_RETRIEVAL = [
    "Builtin.ContextRelevance",
    "Builtin.ContextCoverage",
];

export const ALL_METRICS = [...EVAL_METRICS_RAG, ...EVAL_METRICS_RETRIEVAL];
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
                            knowledgeBaseId: config.knowledgeBaseId,
                            modelArn: `arn:aws:bedrock:${config.cognitoRegion}::foundation-model/anthropic.claude-sonnet-4-6-v1:0`,
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
 * Get evaluation job status and details.
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
        sortBy: "CreationDate",
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

        // Parse Bedrock eval output format
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
```

- [ ] **Step 2: Add `evalRoleArn` to runtime config**

In `artifacts/chat-ui/src/runtime-config.ts`, add the field:

```typescript
export interface RuntimeConfig {
    cognitoUserPoolId: string;
    cognitoClientId: string;
    cognitoIdentityPoolId: string;
    cognitoRegion: string;
    ragRuntimeArn: string;
    multiAgentRuntimeArn: string;
    dataBucketName: string;
    knowledgeBaseId: string;
    dataSourceId: string;
    evalRoleArn: string;
}
```

- [ ] **Step 3: Install @aws-sdk/client-bedrock**

Run: `cd artifacts/chat-ui && npm install @aws-sdk/client-bedrock`

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add artifacts/chat-ui/src/common/evaluation-service.ts artifacts/chat-ui/src/runtime-config.ts artifacts/chat-ui/package.json artifacts/chat-ui/package-lock.json
git commit -m "feat: add evaluation service for Bedrock Evals"
```

---

### Task 4: Evaluation Input Component

**Files:**
- Create: `artifacts/chat-ui/src/components/eval-ui/eval-input.tsx`

- [ ] **Step 1: Create eval input component**

```typescript
// artifacts/chat-ui/src/components/eval-ui/eval-input.tsx
import { useState } from "react";
import {
    Box, Button, Checkbox, Container, FileUpload, FormField,
    Header, SpaceBetween, Tabs, Textarea, Toggle,
} from "@cloudscape-design/components";
import { ALL_METRICS, DEFAULT_METRICS, EvalQuestion } from "../../common/evaluation-service";

export interface EvalInputProps {
    onStartEvaluation: (questions: EvalQuestion[], metrics: string[]) => void;
    isRunning: boolean;
}

export function EvalInput({ onStartEvaluation, isRunning }: EvalInputProps) {
    const [activeTab, setActiveTab] = useState("manual");
    const [manualQuestions, setManualQuestions] = useState("");
    const [uploadedFile, setUploadedFile] = useState<File[]>([]);
    const [selectedMetrics, setSelectedMetrics] = useState<string[]>(DEFAULT_METRICS);
    const [isGroundTruth, setIsGroundTruth] = useState(false);

    const parseManualQuestions = (): EvalQuestion[] => {
        return manualQuestions
            .split("\n")
            .map(line => line.trim())
            .filter(line => line.length > 0)
            .map(question => ({ question }));
    };

    const parseUploadedFile = async (): Promise<EvalQuestion[]> => {
        if (uploadedFile.length === 0) return [];
        const text = await uploadedFile[0].text();
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed)) throw new Error("JSON must be an array");
        return parsed.map((item: any) => ({
            question: item.question,
            expected_answer: item.expected_answer,
            context: item.context,
        }));
    };

    const handleStart = async () => {
        let questions: EvalQuestion[];
        if (activeTab === "manual") {
            questions = parseManualQuestions();
        } else {
            questions = await parseUploadedFile();
        }
        if (questions.length === 0) return;
        onStartEvaluation(questions, selectedMetrics);
    };

    const toggleMetric = (metric: string) => {
        setSelectedMetrics(prev =>
            prev.includes(metric)
                ? prev.filter(m => m !== metric)
                : [...prev, metric]
        );
    };

    return (
        <Container header={<Header variant="h2">Configure Evaluation</Header>}>
            <SpaceBetween size="l">
                <Toggle
                    checked={isGroundTruth}
                    onChange={({ detail }) => setIsGroundTruth(detail.checked)}
                >
                    Ground Truth Mode (provide expected answers)
                </Toggle>

                <Tabs
                    activeTabId={activeTab}
                    onChange={({ detail }) => setActiveTab(detail.activeTabId)}
                    tabs={[
                        {
                            id: "manual",
                            label: "Manual Entry",
                            content: (
                                <FormField
                                    label="Questions (one per line)"
                                    description={isGroundTruth
                                        ? "For ground truth, use the file upload tab with JSON format"
                                        : "Enter questions to evaluate your RAG system against"
                                    }
                                >
                                    <Textarea
                                        value={manualQuestions}
                                        onChange={({ detail }) => setManualQuestions(detail.value)}
                                        rows={8}
                                        placeholder="What is the join process?\nHow do I submit a claim?\nWhat are the waiting periods?"
                                    />
                                </FormField>
                            ),
                        },
                        {
                            id: "upload",
                            label: "File Upload",
                            content: (
                                <FormField
                                    label="Upload JSON file"
                                    description={isGroundTruth
                                        ? 'Format: [{"question": "...", "expected_answer": "..."}]'
                                        : 'Format: [{"question": "..."}]'
                                    }
                                >
                                    <FileUpload
                                        accept=".json"
                                        value={uploadedFile}
                                        onChange={({ detail }) => setUploadedFile(detail.value)}
                                        i18nStrings={{
                                            uploadButtonText: () => "Choose file",
                                            dropzoneText: () => "Drop JSON file here",
                                            removeFileAriaLabel: () => "Remove file",
                                            limitShowFewer: "Show fewer",
                                            limitShowMore: "Show more",
                                            errorIconAriaLabel: "Error",
                                        }}
                                        showFileSize
                                    />
                                </FormField>
                            ),
                        },
                    ]}
                />

                <FormField label="Metrics">
                    <SpaceBetween size="xs" direction="horizontal">
                        {ALL_METRICS.map(metric => (
                            <Checkbox
                                key={metric}
                                checked={selectedMetrics.includes(metric)}
                                onChange={() => toggleMetric(metric)}
                            >
                                {metric.replace("Builtin.", "")}
                            </Checkbox>
                        ))}
                    </SpaceBetween>
                </FormField>

                <Button
                    variant="primary"
                    onClick={handleStart}
                    disabled={isRunning || selectedMetrics.length === 0}
                    loading={isRunning}
                >
                    Run Evaluation
                </Button>
            </SpaceBetween>
        </Container>
    );
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/eval-ui/eval-input.tsx
git commit -m "feat: add evaluation input component"
```

---

### Task 5: Evaluation Dashboard Component

**Files:**
- Create: `artifacts/chat-ui/src/components/eval-ui/eval-dashboard.tsx`

- [ ] **Step 1: Create eval dashboard component**

```typescript
// artifacts/chat-ui/src/components/eval-ui/eval-dashboard.tsx
import {
    Box, Cards, Container, ExpandableSection, Header,
    SpaceBetween, StatusIndicator, Table,
} from "@cloudscape-design/components";
import { EvalResults, EvalMetricResult, EvalQuestionResult } from "../../common/evaluation-service";

function getScoreColor(score: number): "success" | "warning" | "error" {
    if (score >= 0.8) return "success";
    if (score >= 0.6) return "warning";
    return "error";
}

function ScoreCard({ metric }: { metric: EvalMetricResult }) {
    const displayName = metric.metricName.replace("Builtin.", "");
    const color = getScoreColor(metric.score);
    return (
        <Container>
            <Box textAlign="center">
                <Box fontSize="heading-s" fontWeight="bold">{displayName}</Box>
                <Box margin={{ top: "s" }}>
                    <StatusIndicator type={color}>
                        <Box fontSize="display-l" fontWeight="bold">
                            {(metric.score * 100).toFixed(0)}%
                        </Box>
                    </StatusIndicator>
                </Box>
            </Box>
        </Container>
    );
}

export interface EvalDashboardProps {
    results: EvalResults | null;
    isLoading: boolean;
}

export function EvalDashboard({ results, isLoading }: EvalDashboardProps) {
    if (isLoading) {
        return (
            <Container header={<Header variant="h2">Results</Header>}>
                <Box textAlign="center" padding="xl">
                    <StatusIndicator type="loading">
                        Evaluation in progress... This typically takes 2-5 minutes.
                    </StatusIndicator>
                </Box>
            </Container>
        );
    }

    if (!results) {
        return (
            <Container header={<Header variant="h2">Results</Header>}>
                <Box textAlign="center" padding="l" color="text-body-secondary">
                    Run an evaluation to see results here.
                </Box>
            </Container>
        );
    }

    return (
        <SpaceBetween size="l">
            <Container header={<Header variant="h2">Aggregate Scores</Header>}>
                <Cards
                    items={results.aggregateScores}
                    cardDefinition={{
                        body: (item) => <ScoreCard metric={item} />,
                    }}
                    cardsPerRow={[{ cards: 1 }, { minWidth: 200, cards: 3 }, { minWidth: 400, cards: 5 }]}
                />
            </Container>

            <Container header={<Header variant="h2">Per-Question Breakdown</Header>}>
                <Table
                    columnDefinitions={[
                        {
                            id: "question",
                            header: "Question",
                            cell: (item: EvalQuestionResult) => item.question,
                            width: 300,
                        },
                        ...results.aggregateScores.map(agg => ({
                            id: agg.metricName,
                            header: agg.metricName.replace("Builtin.", ""),
                            cell: (item: EvalQuestionResult) => {
                                const m = item.metrics.find(x => x.metricName === agg.metricName);
                                if (!m) return "-";
                                const color = getScoreColor(m.score);
                                return (
                                    <StatusIndicator type={color}>
                                        {(m.score * 100).toFixed(0)}%
                                    </StatusIndicator>
                                );
                            },
                            width: 120,
                        })),
                        {
                            id: "answer",
                            header: "Answer",
                            cell: (item: EvalQuestionResult) => (
                                <ExpandableSection headerText="View answer">
                                    <Box fontSize="body-s">{item.generatedAnswer}</Box>
                                </ExpandableSection>
                            ),
                            width: 200,
                        },
                    ]}
                    items={results.perQuestion}
                    stripedRows
                    wrapLines
                    stickyHeader
                />
            </Container>
        </SpaceBetween>
    );
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/eval-ui/eval-dashboard.tsx
git commit -m "feat: add evaluation dashboard component"
```

---

### Task 6: Evaluation Page

**Files:**
- Create: `artifacts/chat-ui/src/pages/eval-page.tsx`
- Modify: `artifacts/chat-ui/src/pages/index.tsx`
- Modify: `artifacts/chat-ui/src/app.tsx`

- [ ] **Step 1: Create evaluation page**

```typescript
// artifacts/chat-ui/src/pages/eval-page.tsx
import { useState, useContext, useEffect } from "react";
import {
    ContentLayout, Header, SpaceBetween, Container,
    Table, StatusIndicator, Button, Box,
} from "@cloudscape-design/components";
import { withAuthenticator } from "@aws-amplify/ui-react";
import { AppContext } from "../common/context";
import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import { EvalInput } from "../components/eval-ui/eval-input";
import { EvalDashboard } from "../components/eval-ui/eval-dashboard";
import {
    EvalQuestion, EvalResults, EvalJobSummary,
    uploadEvalDataset, createEvalJob, getEvalJob,
    getEvalResults, listEvalJobs,
} from "../common/evaluation-service";

function EvalPageContent(props: AppPage) {
    const appData = useContext(AppContext);
    const [isRunning, setIsRunning] = useState(false);
    const [results, setResults] = useState<EvalResults | null>(null);
    const [recentJobs, setRecentJobs] = useState<EvalJobSummary[]>([]);
    const [error, setError] = useState("");

    useEffect(() => {
        AuthHelper(props, appData);
    }, []);

    const getIdToken = (): string =>
        appData.userinfo?.tokens?.idToken?.toString() || "";

    const getUserEmail = (): string =>
        appData.userinfo?.signInDetails?.loginId || appData.userinfo?.username || "";

    const refreshJobs = async () => {
        try {
            const jobs = await listEvalJobs(getIdToken());
            setRecentJobs(jobs);
        } catch { /* ignore */ }
    };

    useEffect(() => {
        if (appData.userinfo) refreshJobs();
    }, [appData]);

    const handleStartEvaluation = async (questions: EvalQuestion[], metrics: string[]) => {
        setIsRunning(true);
        setResults(null);
        setError("");

        const idToken = getIdToken();
        const userEmail = getUserEmail();
        const jobId = crypto.randomUUID();
        const jobName = `srd-eval-${Date.now()}`;

        try {
            // Upload dataset
            const datasetUri = await uploadEvalDataset(questions, jobId, userEmail, idToken);
            const outputPrefix = `s3://${(await import("../runtime-config")).getRuntimeConfig().dataBucketName}/evaluations/${userEmail}/${jobId}/output/`;

            // Create eval job
            const jobArn = await createEvalJob(jobName, datasetUri, outputPrefix, metrics, idToken);

            // Poll for completion
            const pollInterval = setInterval(async () => {
                try {
                    const job = await getEvalJob(jobArn, idToken);
                    if (job.status === "Completed") {
                        clearInterval(pollInterval);
                        const evalResults = await getEvalResults(userEmail, jobId, idToken);
                        setResults(evalResults);
                        setIsRunning(false);
                        refreshJobs();
                    } else if (job.status === "Failed" || job.status === "Stopped") {
                        clearInterval(pollInterval);
                        setError(`Evaluation ${job.status.toLowerCase()}`);
                        setIsRunning(false);
                        refreshJobs();
                    }
                } catch (err: any) {
                    clearInterval(pollInterval);
                    setError(`Polling error: ${err.message}`);
                    setIsRunning(false);
                }
            }, 15000);

            // Timeout after 10 minutes
            setTimeout(() => {
                clearInterval(pollInterval);
                if (isRunning) {
                    setError("Evaluation is still running. Check back later in Recent Evaluations.");
                    setIsRunning(false);
                    refreshJobs();
                }
            }, 600000);

        } catch (err: any) {
            setError(`Failed to start evaluation: ${err.message}`);
            setIsRunning(false);
        }
    };

    return (
        <ContentLayout header={<Header variant="h1">RAG Evaluation</Header>}>
            <SpaceBetween size="l">
                {error && (
                    <Container>
                        <StatusIndicator type="error">{error}</StatusIndicator>
                    </Container>
                )}

                <EvalInput onStartEvaluation={handleStartEvaluation} isRunning={isRunning} />
                <EvalDashboard results={results} isLoading={isRunning} />

                <Container header={
                    <Header variant="h2" actions={<Button iconName="refresh" onClick={refreshJobs}>Refresh</Button>}>
                        Recent Evaluations
                    </Header>
                }>
                    <Table
                        items={recentJobs}
                        columnDefinitions={[
                            { id: "name", header: "Job Name", cell: (item) => item.jobName },
                            {
                                id: "status", header: "Status", cell: (item) => {
                                    const type = item.status === "Completed" ? "success"
                                        : item.status === "InProgress" ? "loading"
                                        : item.status === "Failed" ? "error" : "info";
                                    return <StatusIndicator type={type}>{item.status}</StatusIndicator>;
                                }
                            },
                            { id: "created", header: "Created", cell: (item) => item.createdAt.toLocaleString() },
                        ]}
                        empty={<Box textAlign="center" color="text-body-secondary">No evaluations yet</Box>}
                        stripedRows
                    />
                </Container>
            </SpaceBetween>
        </ContentLayout>
    );
}

export default withAuthenticator(EvalPageContent);
```

- [ ] **Step 2: Add export to pages/index.tsx**

```typescript
export { default as ChatPage } from './chat-page';
export { default as NotFound } from './not-found';
export { default as AgentPage } from './agent-page';
export { default as HomePage } from './home-page';
export { default as Help } from './help-page';
export { default as EvalPage } from './eval-page';
```

- [ ] **Step 3: Add route and nav item to app.tsx**

In `src/app.tsx`, add `EvalPage` to the import:
```typescript
import { NotFound, ChatPage, AgentPage, HomePage, Help, EvalPage } from './pages'
```

Add to navigation items (after Multi-Agent):
```typescript
{ type: "link", text: "Evaluation", href: "#/evaluation" },
```

Add route (after the multi-agent route):
```typescript
<Route path="/evaluation" element={<EvalPage setAppData={setAppData} />} />
```

Add help route:
```typescript
<Route path="/evaluation" element={<Help setPageId="evaluation" />} />
```

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add artifacts/chat-ui/src/pages/eval-page.tsx artifacts/chat-ui/src/pages/index.tsx artifacts/chat-ui/src/app.tsx
git commit -m "feat: add evaluation page with routing"
```

---

### Task 7: IAM Permissions for Evaluation

**Files:**
- Modify: `infrastructure/cognito_stack.py`

- [ ] **Step 1: Add evaluation and feedback IAM policies**

In `infrastructure/cognito_stack.py`, add two new policies to the `inline_policies` dict of `authenticated_role`:

```python
                "BedrockEval": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "bedrock:CreateEvaluationJob",
                            "bedrock:GetEvaluationJob",
                            "bedrock:ListEvaluationJobs",
                        ],
                        resources=["*"],
                    ),
                ]),
                "S3EvalAndFeedback": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="EvalReadWrite",
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/evaluations/*"],
                    ),
                    iam.PolicyStatement(
                        sid="FeedbackWrite",
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/feedback/*"],
                    ),
                ]),
```

- [ ] **Step 2: Add Bedrock evaluation service role**

After the `authenticated_role`, add a new role for the Bedrock eval service:

```python
        # IAM role for Bedrock Evaluation service
        eval_service_role = iam.Role(
            self, f"srd-eval-service-role-{env_name}",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "EvalKBAccess": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                        resources=[f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"],
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=[
                            f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        ],
                    ),
                ]),
                "EvalS3Access": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{data_bucket_name}/evaluations/*"],
                    ),
                ]),
            },
        )

        # Export eval role ARN for runtime-config
        CfnOutput(self, f"eval-role-arn-{env_name}",
                  value=eval_service_role.role_arn,
                  description="Bedrock Evaluation service role ARN")
```

- [ ] **Step 3: Expose eval role ARN as stack output**

Add to the class (after identity pool outputs):
```python
        self.eval_role_arn = eval_service_role.role_arn
```

- [ ] **Step 4: Commit**

```bash
git add infrastructure/cognito_stack.py
git commit -m "feat: add IAM permissions for Bedrock Evals and feedback"
```

---

### Task 8: Update deploy.sh and runtime-config

**Files:**
- Modify: `deploy.sh`

- [ ] **Step 1: Extract eval role ARN from CDK outputs and add to runtime-config.json**

In `deploy.sh`, after extracting `DATA_SOURCE_ID`, add:
```bash
EVAL_ROLE_ARN=$(jq -r ".[\"SRD-Auth-$ENV_NAME\"] | to_entries[] | select(.key | contains(\"eval-role-arn\")) | .value" cdk-outputs.json)
```

Update the runtime-config.json heredoc to include the new field:
```json
{
  "cognitoUserPoolId": "$COGNITO_POOL_ID",
  "cognitoClientId": "$COGNITO_CLIENT_ID",
  "cognitoIdentityPoolId": "$COGNITO_IDENTITY_POOL_ID",
  "cognitoRegion": "$REGION",
  "ragRuntimeArn": "$RAG_RUNTIME_ARN",
  "multiAgentRuntimeArn": "$MA_RUNTIME_ARN",
  "dataBucketName": "$DATA_BUCKET",
  "knowledgeBaseId": "$KB_ID",
  "dataSourceId": "$DATA_SOURCE_ID",
  "evalRoleArn": "$EVAL_ROLE_ARN"
}
```

- [ ] **Step 2: Commit**

```bash
git add deploy.sh
git commit -m "feat: add evalRoleArn to deploy.sh runtime-config"
```

---

### Task 9: Build, Deploy, and Verify

- [ ] **Step 1: Deploy CDK stacks**

```bash
cd /path/to/serverless-rag-demo
export CDK_DEFAULT_REGION=us-east-1
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
DEPLOYER_ARN=$(aws sts get-caller-identity --query Arn --output text)
cdk deploy "SRD-Auth-test" --context environment_name=test --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0 --context ocu_mode=demo --context deployer_arn=$DEPLOYER_ARN --require-approval never --outputs-file cdk-outputs.json
```

- [ ] **Step 2: Update runtime-config.json in S3 with evalRoleArn**

Extract the eval role ARN from CDK outputs and update S3 runtime-config.json.

- [ ] **Step 3: Build and deploy UI**

```bash
cd artifacts/chat-ui
npm run build
aws s3 sync dist/ s3://<UI_BUCKET>/ --delete --exclude "runtime-config.json"
```

- [ ] **Step 4: Invalidate CloudFront**

```bash
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

- [ ] **Step 5: Verify**

Open the UI, navigate to the Evaluation tab. Confirm:
- Manual question entry works
- File upload accepts JSON
- Metrics checkboxes toggle
- "Run Evaluation" button triggers a job
- Thumbs up/down buttons appear on chat messages

- [ ] **Step 6: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: complete RAG evaluation feature deployment"
```
