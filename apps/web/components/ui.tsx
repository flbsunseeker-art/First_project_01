import type { ReactNode } from "react";

type Tone = "default" | "profit" | "loss" | "info" | "warning";

export function Card({
  children,
  className = "",
}: Readonly<{ children: ReactNode; className?: string }>) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function Badge({
  children,
  tone = "default",
}: Readonly<{ children: ReactNode; tone?: Tone }>) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Button({
  children,
  variant = "primary",
}: Readonly<{ children: ReactNode; variant?: "primary" | "ghost" }>) {
  return <button className={`button button-${variant}`}>{children}</button>;
}

export function DataTable({
  columns,
  rows,
}: Readonly<{ columns: string[]; rows: Array<Array<ReactNode>> }>) {
  return (
    <div className="table-frame">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DialogPanel({
  title,
  children,
}: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <div className="dialog-panel" role="dialog" aria-label={title}>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function Field({
  label,
  placeholder,
}: Readonly<{ label: string; placeholder?: string }>) {
  return (
    <label className="field">
      <span>{label}</span>
      <input placeholder={placeholder} />
    </label>
  );
}
