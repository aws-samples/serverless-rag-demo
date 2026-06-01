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
