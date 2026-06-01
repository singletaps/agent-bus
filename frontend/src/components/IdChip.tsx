import React from "react";

export type IdChipProps = {
  value: string;
  label?: string;
};

export function IdChip({ value, label }: IdChipProps) {
  const short = value.length > 14 ? `${value.slice(0, 10)}...` : value;

  return (
    <code className="idChip" title={value}>
      {label ? `${label} ` : ""}
      {short}
    </code>
  );
}
