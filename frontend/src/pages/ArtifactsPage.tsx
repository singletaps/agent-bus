import React, { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Box,
  Download,
  FileCheck2,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  MoreHorizontal,
  RefreshCw,
  ScrollText,
} from "lucide-react";

import { IdChip } from "../components/IdChip";
import type { ArtifactManifestRow, OperationsProjection } from "../operationsApi";
import { fetchArtifactManifests } from "../operationsApi";

type ArtifactsPageProps = {
  projection: OperationsProjection;
};

type ArtifactTab = "all" | "screenshot" | "report" | "log" | "handoff";

const artifactTabs: Array<{ key: ArtifactTab; label: string }> = [
  { key: "all", label: "全部" },
  { key: "screenshot", label: "截图" },
  { key: "report", label: "报告" },
  { key: "log", label: "日志" },
  { key: "handoff", label: "交接" },
];

export function ArtifactsPage({ projection }: ArtifactsPageProps) {
  const [artifacts, setArtifacts] = useState<ArtifactManifestRow[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [activeTab, setActiveTab] = useState<ArtifactTab>("all");
  const [status, setStatus] = useState("等待同步");
  const allArtifacts = useMemo(
    () => mergeArtifactRows(artifacts, projection.artifacts.map(durableArtifactToRow)),
    [artifacts, projection.artifacts],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadArtifacts(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!allArtifacts.length) {
      setSelectedArtifactId("");
      return;
    }
    if (!allArtifacts.some((artifact) => artifact.artifactId === selectedArtifactId)) {
      setSelectedArtifactId(allArtifacts[0].artifactId);
    }
  }, [allArtifacts, selectedArtifactId]);

  async function loadArtifacts(signal?: AbortSignal) {
    try {
      const nextArtifacts = await fetchArtifactManifests(signal);
      setArtifacts(nextArtifacts);
      setStatus(`${nextArtifacts.length} manifest artifacts`);
    } catch (error) {
      if (!signal?.aborted) {
        setStatus(error instanceof Error ? error.message : "artifact manifests unavailable");
      }
    }
  }

  const visibleArtifacts = useMemo(
    () =>
      activeTab === "all"
        ? allArtifacts
        : allArtifacts.filter((artifact) => artifactCategory(artifact) === activeTab),
    [activeTab, allArtifacts],
  );
  const selectedArtifact =
    visibleArtifacts.find((artifact) => artifact.artifactId === selectedArtifactId) ||
    visibleArtifacts[0] ||
    allArtifacts.find((artifact) => artifact.artifactId === selectedArtifactId) ||
    allArtifacts[0];
  const todayAdded = allArtifacts.filter((artifact) => isToday(artifact.createdAt)).length;

  return (
    <section className="artifactsPage pageShell referencePage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">ARTIFACTS</span>
          <h2>产物</h2>
          <p>查看任务生成的截图、报告、交接文档和日志；manifest 文件与 durable artifact 记录共同作为真实来源。</p>
        </div>
        <button className="toolbarButton" onClick={() => void loadArtifacts()} type="button">
          <RefreshCw size={14} strokeWidth={2.2} />
          刷新
        </button>
      </header>

      <div className="referenceTabs artifactTabs" role="tablist" aria-label="产物类型">
        {artifactTabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.key}
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="metricStrip artifactMetrics">
        <Metric label="Manifest artifacts" value={artifacts.length} icon={Box} />
        <Metric label="Durable records" value={projection.artifacts.length} icon={FileCheck2} />
        <Metric label="今日新增" value={todayAdded} icon={Archive} />
      </div>

      <div className="artifactsWorkspace">
        <section className="referenceCard artifactListPanel">
          <header className="referenceCardHeader">
            <div>
              <h3>产物列表 ({visibleArtifacts.length})</h3>
              <p>{status} · {projection.artifacts.length} durable records</p>
            </div>
          </header>
          {visibleArtifacts.length ? (
            <div className="artifactList">
              {visibleArtifacts.map((artifact) => (
                <button
                  className="artifactListItem"
                  data-selected={artifact.artifactId === selectedArtifact?.artifactId ? "true" : "false"}
                  key={artifact.artifactId}
                  onClick={() => setSelectedArtifactId(artifact.artifactId)}
                  type="button"
                >
                  <ArtifactIcon artifact={artifact} />
                  <div>
                    <strong>{artifact.title}</strong>
                    <div className="artifactMetaLine">
                      <IdChip value={artifact.runId || "no-run"} label="Run" />
                      {artifact.taskId ? <IdChip value={artifact.taskId} label="Task" /> : null}
                      {artifact.agentId ? <IdChip value={artifact.agentId} label="Agent" /> : null}
                    </div>
                    <span>
                      生成于 {formatDateTime(artifact.createdAt)} · {artifact.type}
                      {artifact.sizeBytes !== null ? ` · ${formatBytes(artifact.sizeBytes)}` : ""}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="referenceEmpty">
              <strong>暂无匹配产物</strong>
              <span>当前筛选下没有 manifest-backed 记录。</span>
            </div>
          )}
        </section>

        <section className="referenceCard artifactDetailPanel">
          {selectedArtifact ? (
            <>
              <header className="artifactDetailHeader">
                <ArtifactIcon artifact={selectedArtifact} />
                <div>
                  <h3>{selectedArtifact.title}</h3>
                  <span className="artifactTypeBadge">{artifactCategoryLabel(selectedArtifact)}</span>
                </div>
                <div className="artifactActionRow">
                  <ArtifactFileLink
                    disabledLabel="无文件"
                    icon={Download}
                    label="下载"
                    url={selectedArtifact.downloadUrl}
                  />
                  <ArtifactFileLink
                    disabledLabel="无预览"
                    icon={FolderOpen}
                    label="打开"
                    url={selectedArtifact.previewUrl}
                  />
                  <button aria-label="更多产物操作" type="button">
                    <MoreHorizontal size={16} strokeWidth={2.2} />
                  </button>
                </div>
              </header>

              <div className="chipRow">
                {selectedArtifact.runId ? <IdChip value={selectedArtifact.runId} label="Run" /> : null}
                {selectedArtifact.taskId ? <IdChip value={selectedArtifact.taskId} label="Task" /> : null}
                {selectedArtifact.agentId ? <IdChip value={selectedArtifact.agentId} label="Agent" /> : null}
              </div>

              <div className="artifactPathLine">
                <code>{selectedArtifact.path || "未记录路径"}</code>
              </div>

              <ArtifactPreview artifact={selectedArtifact} />

              <section className="artifactDescription">
                <h4>描述</h4>
                <p>
                  {selectedArtifact.summary || "该 manifest 未记录描述。"}
                  {selectedArtifact.contentType ? ` 类型：${selectedArtifact.contentType}` : ""}
                </p>
              </section>

              <section className="artifactDescription">
                <h4>关联</h4>
                <div className="chipRow">
                  {selectedArtifact.taskId ? <IdChip value={selectedArtifact.taskId} label="任务" /> : null}
                  {selectedArtifact.runId ? <IdChip value={selectedArtifact.runId} label="运行" /> : null}
                </div>
              </section>

              <section className="artifactDescription">
                <h4>下一步</h4>
                <div className="actionBar">
                  <button className="filterButton" type="button">查看任务</button>
                  <button className="filterButton" type="button">查看门禁</button>
                  <button className="filterButton" type="button">在任务流中定位</button>
                </div>
              </section>
            </>
          ) : (
            <div className="referenceEmpty artifactDetailEmpty">
              <strong>没有可预览的产物</strong>
              <span>当 manifest 出现后，右侧会显示路径、描述、关联任务和下一步操作。</span>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  value: number;
}) {
  return (
    <div className="metricTile artifactMetric">
      <Icon size={22} strokeWidth={2.2} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ArtifactFileLink({
  disabledLabel,
  icon: Icon,
  label,
  url,
}: {
  disabledLabel: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  url: string;
}) {
  if (!url) {
    return (
      <button className="artifactLinkButton" disabled type="button">
        <Icon size={14} strokeWidth={2.2} />
        {disabledLabel}
      </button>
    );
  }
  return (
    <a className="artifactLinkButton" href={url} rel="noreferrer" target="_blank">
      <Icon size={14} strokeWidth={2.2} />
      {label}
    </a>
  );
}

function ArtifactIcon({ artifact }: { artifact: ArtifactManifestRow }) {
  const category = artifactCategory(artifact);
  const Icon =
    category === "screenshot"
      ? ImageIcon
      : category === "report"
        ? FileText
        : category === "log"
          ? ScrollText
          : category === "handoff"
            ? Archive
            : Box;
  return (
    <span className="artifactIcon" data-category={category}>
      <Icon size={20} strokeWidth={2.2} />
    </span>
  );
}

function ArtifactPreview({ artifact }: { artifact: ArtifactManifestRow }) {
  const previewSrc = previewSource(artifact);
  if (previewSrc && isImageArtifact(artifact)) {
    return (
      <div className="artifactPreview">
        <img alt={artifact.title} src={previewSrc} />
      </div>
    );
  }
  if (previewSrc && isTextArtifact(artifact)) {
    return (
      <div className="artifactPreview artifactTextPreview">
        <iframe src={previewSrc} title={artifact.title} />
      </div>
    );
  }
  return (
    <div className="artifactPreview artifactPreviewEmpty">
      <ArtifactIcon artifact={artifact} />
      <strong>{artifact.type || "artifact"}</strong>
      <span>{artifact.previewUrl ? "此类型可以打开或下载，但不直接内嵌预览。" : artifact.path || "没有可直接预览的路径"}</span>
    </div>
  );
}

function artifactCategory(artifact: ArtifactManifestRow): ArtifactTab {
  const haystack = `${artifact.type} ${artifact.title} ${artifact.path}`.toLowerCase();
  if (haystack.includes("screen") || haystack.includes("png") || haystack.includes("jpg") || haystack.includes("jpeg")) {
    return "screenshot";
  }
  if (haystack.includes("report") || haystack.includes("md") || haystack.includes("markdown")) {
    return "report";
  }
  if (haystack.includes("log") || haystack.includes("txt") || haystack.includes("trace")) {
    return "log";
  }
  if (haystack.includes("handoff") || haystack.includes("交接")) {
    return "handoff";
  }
  return "all";
}

function artifactCategoryLabel(artifact: ArtifactManifestRow): string {
  const category = artifactCategory(artifact);
  return artifactTabs.find((tab) => tab.key === category)?.label || artifact.type || "产物";
}

function durableArtifactToRow(
  artifact: OperationsProjection["artifacts"][number],
): ArtifactManifestRow {
  return {
    artifactId: artifact.id,
    runId: artifact.runId,
    taskId: artifact.taskId,
    agentId: artifact.owner,
    type: artifact.kind,
    title: artifact.summary || artifact.kind || artifact.id,
    path: artifact.path,
    createdAt: artifact.createdAt,
    summary: artifact.summary,
    sizeBytes: null,
    contentType: "",
    previewUrl: artifact.path.startsWith("/api/") ? artifact.path : "",
    downloadUrl: artifact.path.startsWith("/api/") ? artifact.path : "",
  };
}

function mergeArtifactRows(
  manifestRows: ArtifactManifestRow[],
  durableRows: ArtifactManifestRow[],
): ArtifactManifestRow[] {
  const byId = new Map<string, ArtifactManifestRow>();
  for (const row of durableRows) {
    byId.set(row.artifactId, row);
  }
  for (const row of manifestRows) {
    byId.set(row.artifactId, row);
  }
  return Array.from(byId.values()).sort((left, right) =>
    (right.createdAt || "").localeCompare(left.createdAt || ""),
  );
}

function previewSource(artifact: ArtifactManifestRow): string {
  return artifact.previewUrl || "";
}

function isImageArtifact(artifact: ArtifactManifestRow): boolean {
  const haystack = `${artifact.contentType} ${artifact.path}`.toLowerCase();
  return /image\/|\.png|\.jpg|\.jpeg|\.webp|\.gif/.test(haystack);
}

function isTextArtifact(artifact: ArtifactManifestRow): boolean {
  const haystack = `${artifact.contentType} ${artifact.path}`.toLowerCase();
  return /text\/|json|markdown|\.md|\.txt|\.log|\.json/.test(haystack);
}

function isToday(value: string): boolean {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return date.toDateString() === new Date().toDateString();
}

function formatDateTime(value: string): string {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
