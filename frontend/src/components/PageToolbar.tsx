import React from "react";
import { Clock3, RefreshCw } from "lucide-react";

export type PageToolbarProps = {
  lastLoadedAt: string;
  onRefresh?: () => void;
  refreshLabel?: string;
};

export function PageToolbar({
  lastLoadedAt,
  onRefresh,
  refreshLabel = "自动刷新：5秒",
}: PageToolbarProps) {
  return (
    <div className="pageToolbar" aria-label="页面同步状态">
      <button className="toolbarButton" onClick={onRefresh} type="button">
        <RefreshCw size={14} strokeWidth={2.2} />
        {refreshLabel}
      </button>
      <span className="toolbarSync">
        <Clock3 size={14} strokeWidth={2.2} />
        上次同步：{lastLoadedAt || "等待同步"}
      </span>
    </div>
  );
}
