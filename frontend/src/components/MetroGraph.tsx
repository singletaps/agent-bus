import React, { useMemo } from "react";
import {
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Diamond,
  FileCheck2,
  FileText,
  Flag,
  GitBranch,
  Play,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import type { UiMetroNode, UiTaskWorkflowProjection, UiTone } from "../operationsApi";
import { stateLabel } from "../uiText";

export type MetroGraphProps = {
  metro: UiTaskWorkflowProjection;
  onNodeSelect: (node: UiMetroNode) => void;
};

type Point = {
  x: number;
  y: number;
};

const nodeWidth = 136;
const nodeHeight = 76;

export function MetroGraph({ metro, onNodeSelect }: MetroGraphProps) {
  const layout = useMemo(() => buildMetroLayout(metro), [metro]);

  if (!metro.nodes.length) {
    return (
      <div className="metroGraphEmpty">
        <GitBranch size={22} strokeWidth={2.1} />
        <strong>暂无任务工作流节点</strong>
        <span>等待真实 run、task、context、claim、gate 或 artifact 写入后生成视图。</span>
      </div>
    );
  }

  return (
    <div className="metroGraphViewport" aria-label="任务工作流图">
      <div
        className="metroGraphCanvas"
        style={{ width: layout.width, height: layout.height }}
      >
        <svg
          aria-hidden="true"
          className="metroGraphSvg"
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          width={layout.width}
        >
          {layout.edges.map((edge) => (
            <path
              className="metroGraphEdge"
              d={edge.path}
              data-kind={edge.kind}
              data-tone={edge.tone}
              key={edge.id}
            />
          ))}
        </svg>
        {metro.nodes.map((node) => {
          const point = layout.points[node.id];
          if (!point) {
            return null;
          }
          return (
            <button
              aria-current={metro.currentNodeId === node.id ? "step" : undefined}
              className="metroGraphNode"
              data-current={metro.currentNodeId === node.id ? "true" : undefined}
              data-kind={node.kind}
              data-tone={node.tone}
              key={node.id}
              onClick={() => onNodeSelect(node)}
              style={{
                left: point.x - nodeWidth / 2,
                top: point.y - nodeHeight / 2,
                width: nodeWidth,
                minHeight: nodeHeight,
              }}
              type="button"
            >
              <span className="metroGraphNodeIcon">{nodeIcon(node)}</span>
              <span className="metroGraphNodeCopy">
                <strong>{node.title}</strong>
                <small>{node.subtitle || stateLabel(node.state)}</small>
              </span>
              <span className="metroGraphNodeState">{stateLabel(node.state)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function buildMetroLayout(metro: UiTaskWorkflowProjection) {
  const mainIds =
    metro.mainPathNodeIds.length > 0
      ? metro.mainPathNodeIds
      : metro.nodes
          .filter((node) => node.kind === "start" || node.kind === "task")
          .map((node) => node.id);
  const included = new Set(mainIds);
  const width = Math.max(720, 150 + Math.max(0, mainIds.length - 1) * 190);
  const height = 340;
  const y = 170;
  const points: Record<string, Point> = {};

  mainIds.forEach((id, index) => {
    points[id] = {
      x: 76 + index * 190,
      y,
    };
  });

  for (const [source, branchIds] of Object.entries(metro.branchGroups)) {
    const sourcePoint = points[source];
    if (!sourcePoint) {
      continue;
    }
    branchIds.forEach((branchId, index) => {
      included.add(branchId);
      const direction = index % 2 === 0 ? -1 : 1;
      const lane = Math.floor(index / 2);
      points[branchId] = {
        x: sourcePoint.x + 76 + lane * 72,
        y: sourcePoint.y + direction * 104,
      };
    });
  }

  const orphanNodes = metro.nodes.filter((node) => !included.has(node.id));
  orphanNodes.forEach((node, index) => {
    points[node.id] = {
      x: 96 + index * 160,
      y: 292,
    };
  });

  const edges = metro.edges
    .map((edge) => {
      const source = points[edge.source];
      const target = points[edge.target];
      if (!source || !target) {
        return null;
      }
      return {
        ...edge,
        path: edgePath(source, target, edge.kind),
      };
    })
    .filter(
      (
        edge,
      ): edge is {
        id: string;
        source: string;
        target: string;
        kind: string;
        tone: UiTone;
        path: string;
      } => edge !== null,
    );

  return { width, height, points, edges };
}

function edgePath(source: Point, target: Point, kind: string): string {
  if (kind === "main") {
    return `M ${source.x} ${source.y} L ${target.x} ${target.y}`;
  }
  const controlX = source.x + (target.x - source.x) * 0.45;
  return `M ${source.x} ${source.y} C ${controlX} ${source.y}, ${controlX} ${target.y}, ${target.x} ${target.y}`;
}

function nodeIcon(node: UiMetroNode) {
  const size = 16;
  if (node.kind === "start") {
    return <Play size={size} strokeWidth={2.2} />;
  }
  if (node.kind === "gate") {
    return node.tone === "bad" ? (
      <ShieldAlert size={size} strokeWidth={2.2} />
    ) : (
      <Diamond size={size} strokeWidth={2.2} />
    );
  }
  if (node.kind === "artifact") {
    return <FileText size={size} strokeWidth={2.2} />;
  }
  if (node.kind === "context") {
    return <ClipboardCheck size={size} strokeWidth={2.2} />;
  }
  if (node.kind === "claim") {
    return <FileCheck2 size={size} strokeWidth={2.2} />;
  }
  if (node.kind === "replacement") {
    return <RefreshCw size={size} strokeWidth={2.2} />;
  }
  if (node.kind === "terminal") {
    return <Flag size={size} strokeWidth={2.2} />;
  }
  if (node.tone === "good") {
    return <CheckCircle2 size={size} strokeWidth={2.2} />;
  }
  if (node.tone === "bad") {
    return <XCircle size={size} strokeWidth={2.2} />;
  }
  return <Circle size={size} strokeWidth={2.2} />;
}
