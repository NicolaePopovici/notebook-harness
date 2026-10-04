import { useEffect } from "react";
import type { Notebook } from "./api";
import type { Selection } from "./DocumentView";

export function NotebookView(props: { notebook: Notebook; selection: Selection | null }) {
  const { notebook, selection } = props;

  useEffect(() => {
    if (!selection) return;
    document
      .getElementById(`line-${selection.cell}-${selection.start}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selection]);

  return (
    <section className="notebook">
      <h1 title={notebook.path}>{notebook.name}</h1>
      {notebook.cells.map((cell) => {
        const first = cell.lines[0].file_line;
        const last = cell.lines[cell.lines.length - 1].file_line;
        return (
          <div key={cell.index} className={`cell ${selection?.cell === cell.index ? "selected" : ""}`}>
            <div className="cell-header">
              Cell {cell.index} · {cell.lang}
              {cell.title && ` · ${cell.title}`}
              {first !== null && <span className="file-lines">file lines {first}–{last}</span>}
            </div>
            <pre>
              {cell.lines.map((line) => {
                const highlighted =
                  selection?.cell === cell.index && line.cell_line >= selection.start && line.cell_line <= selection.end;
                return (
                  <div
                    key={line.cell_line}
                    id={`line-${cell.index}-${line.cell_line}`}
                    className={highlighted ? "line highlighted" : "line"}
                  >
                    <span className="gutter">{line.cell_line}</span>
                    {line.text || " "}
                  </div>
                );
              })}
            </pre>
          </div>
        );
      })}
    </section>
  );
}
