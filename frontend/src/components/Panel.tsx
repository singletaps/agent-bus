import React, { type ReactNode } from "react";

export type PanelProps = {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
};

export function Panel({ title, meta, children, className = "" }: PanelProps) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panelHeader">
        <h3>{title}</h3>
        {meta ? <span>{meta}</span> : null}
      </header>
      {children}
    </section>
  );
}
