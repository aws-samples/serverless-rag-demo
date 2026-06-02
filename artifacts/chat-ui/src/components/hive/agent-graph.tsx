import { useMemo, useCallback, useEffect } from "react";
import { ReactFlow, Background, Controls, useNodesState, useEdgesState, Node, Edge, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode, ChannelNode } from "./agent-graph-nodes";
import { HiveConfig, HiveEvent, AgentStatus } from "./types";

const nodeTypes = { agent: AgentNode, channel: ChannelNode };

interface AgentGraphProps {
    config: HiveConfig | null;
    events: HiveEvent[];
    activeAgent: string | null;
    onNodeClick: (agentId: string) => void;
}

function getAgentStatus(agentId: string, events: HiveEvent[]): AgentStatus {
    const agentEvents = events.filter((e) => e.agent === agentId);
    if (agentEvents.length === 0) return "idle";
    const last = agentEvents[agentEvents.length - 1];
    if (last.event === "error") return "error";
    if (last.event === "received" || last.event === "thinking") return "thinking";
    if (last.event === "responded" || last.event === "acting") return "acting";
    return "idle";
}

export function AgentGraph({ config, events, activeAgent, onNodeClick }: AgentGraphProps) {
    const { initialNodes, initialEdges } = useMemo(() => {
        if (!config) return { initialNodes: [], initialEdges: [] };

        const nodes: Node[] = [];
        const edges: Edge[] = [];

        nodes.push({ id: "core", type: "agent", position: { x: 250, y: 200 }, data: { label: "Hive Core", status: getAgentStatus("router", events), isCore: true } });

        const radius = 150;
        config.agents.forEach((agent, i) => {
            const angle = (2 * Math.PI * i) / config.agents.length - Math.PI / 2;
            nodes.push({
                id: agent.id, type: "agent",
                position: { x: 250 + radius * Math.cos(angle), y: 200 + radius * Math.sin(angle) },
                data: { label: agent.name, status: getAgentStatus(agent.id, events) },
            });
            edges.push({
                id: `core-${agent.id}`, source: "core", target: agent.id,
                animated: activeAgent === agent.id,
                style: { stroke: activeAgent === agent.id ? "#1d8102" : "#8c8c8c" },
                markerEnd: { type: MarkerType.ArrowClosed },
            });
        });

        const chRadius = 280;
        config.channels.forEach((ch, i) => {
            const angle = (2 * Math.PI * i) / Math.max(config.channels.length, 1);
            nodes.push({
                id: `ch-${ch.id}`, type: "channel",
                position: { x: 250 + chRadius * Math.cos(angle), y: 200 + chRadius * Math.sin(angle) },
                data: { label: ch.id.split("-")[0], provider: ch.provider, connected: true },
            });
            ch.agents.forEach((agentId) => {
                edges.push({ id: `ch-${ch.id}-${agentId}`, source: agentId, target: `ch-${ch.id}`, style: { stroke: "#8c8c8c", strokeDasharray: "4 4" } });
            });
        });

        return { initialNodes: nodes, initialEdges: edges };
    }, [config, events, activeAgent]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    useEffect(() => { setNodes(initialNodes); setEdges(initialEdges); }, [initialNodes, initialEdges]);

    const handleNodeClick = useCallback((_: any, node: Node) => {
        if (node.type === "agent" && node.id !== "core") onNodeClick(node.id);
    }, [onNodeClick]);

    return (
        <div style={{ width: "100%", height: 400 }}>
            <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                onNodeClick={handleNodeClick} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }}>
                <Background />
                <Controls />
            </ReactFlow>
        </div>
    );
}
