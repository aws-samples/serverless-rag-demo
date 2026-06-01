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
