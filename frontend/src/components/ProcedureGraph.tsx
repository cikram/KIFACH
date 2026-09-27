/**
 * The procedure as a graph: steps as nodes, dependencies as solid edges, and
 * reviewed ordering rules as dashed ones. Layout is computed with dagre so a
 * proposal is readable the moment it arrives, and the same component renders
 * live step states during an attempt.
 */
import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import type { SkillGraph, StepState } from "@/types/api";
import { STEP_STATE_COLOR, STEP_STATE_LABEL } from "@/lib/format";

const NODE_WIDTH = 210;
const NODE_HEIGHT = 74;

type StepNodeData = {
  title: string;
  state: StepState;
  index: number;
  proposed: boolean;
  onSelect?: () => void;
};

function StepNode({ data, selected }: NodeProps) {
  const payload = data as StepNodeData;
  const color = STEP_STATE_COLOR[payload.state];
  return (
    <div
      className="rounded-lg border bg-surface-raised px-3 py-2 text-left shadow-panel"
      style={{
        width: NODE_WIDTH,
        borderColor: selected ? "var(--accent)" : color,
        borderLeftWidth: 4,
      }}
      onClick={payload.onSelect}
      data-testid={`graph-node-${payload.state}`}
    >
      <Handle type="target" position={Position.Top} />
      <p className="mono text-[10px] text-ink-faint">STEP {payload.index + 1}</p>
      <p className="truncate text-sm font-medium text-ink" title={payload.title}>
        {payload.title}
      </p>
      <p className="mt-0.5 text-[11px]" style={{ color }}>
        {STEP_STATE_LABEL[payload.state]}
        {payload.proposed && <span className="text-ink-faint"> · proposed</span>}
      </p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { step: StepNode };

function layout(
  skill: SkillGraph,
  states: Record<string, StepState>,
  onSelect?: (stepId: string) => void,
): { nodes: Node[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 34, ranksep: 54 });

  const steps = skill.steps ?? [];
  for (const step of steps) {
    graph.setNode(step.step_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  const edges: Edge[] = [];
  for (const step of steps) {
    for (const dependency of step.depends_on ?? []) {
      if (!steps.some((candidate) => candidate.step_id === dependency)) continue;
      graph.setEdge(dependency, step.step_id);
      edges.push({
        id: `dep-${dependency}-${step.step_id}`,
        source: dependency,
        target: step.step_id,
        animated: false,
      });
    }
  }
  for (const rule of skill.rules ?? []) {
    if (
      !steps.some((candidate) => candidate.step_id === rule.before) ||
      !steps.some((candidate) => candidate.step_id === rule.after)
    ) {
      continue;
    }
    graph.setEdge(rule.before, rule.after);
    edges.push({
      id: `rule-${rule.rule_id}`,
      source: rule.before,
      target: rule.after,
      className: "rule-edge",
      label: rule.confirmed_by_expert ? "rule" : "proposed rule",
      labelStyle: { fill: "var(--warn)", fontSize: 10 },
      labelBgStyle: { fill: "var(--surface)" },
    });
  }

  dagre.layout(graph);

  const nodes: Node[] = steps.map((step, index) => {
    const position = graph.node(step.step_id);
    return {
      id: step.step_id,
      type: "step",
      position: {
        x: (position?.x ?? index * 60) - NODE_WIDTH / 2,
        y: (position?.y ?? index * 110) - NODE_HEIGHT / 2,
      },
      data: {
        title: step.title,
        state: states[step.step_id] ?? "pending",
        index,
        // Once published, nothing on the graph is still a bare proposal.
        proposed: (step.proposed_by_model ?? false) && skill.status !== "published",
        onSelect: onSelect ? () => onSelect(step.step_id) : undefined,
      } satisfies StepNodeData,
    };
  });

  return { nodes, edges };
}

export function ProcedureGraph({
  skill,
  states = {},
  onSelect,
  height = 420,
}: {
  skill: SkillGraph;
  states?: Record<string, StepState>;
  onSelect?: (stepId: string) => void;
  height?: number;
}) {
  const { nodes, edges } = useMemo(
    () => layout(skill, states, onSelect),
    [skill, states, onSelect],
  );

  return (
    <div
      style={{ height }}
      className="overflow-hidden rounded-lg border border-line bg-surface-sunken"
      data-testid="procedure-graph"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={Boolean(onSelect)}
        zoomOnScroll={false}
        panOnScroll
      >
        <Background color="var(--line)" gap={18} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
