import type { Citation, Claim, Document } from "./api";

export interface Selection {
  cell: number;
  start: number;
  end: number;
}

export function DocumentView(props: {
  document: Document;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  const v = props.document.validation;
  return (
    <article className="document">
      <h1>{props.document.title}</h1>
      <p className="summary">
        {v.claims_verified}/{v.claims_total} claims verified
        {v.claims_partial > 0 && ` · ${v.claims_partial} partly verified`}
        {v.claims_unverified > 0 && ` · ${v.claims_unverified} unverified`}
        {` · ${props.document.model}`}
      </p>
      {v.missing_sections.length > 0 && (
        <p className="error">The model did not write these sections: {v.missing_sections.join(", ")}.</p>
      )}
      {props.document.sections.map((section) => (
        <section key={section.heading}>
          <h2>{section.heading}</h2>
          <ul>
            {section.claims.map((claim) => (
              <ClaimItem key={claim.id} claim={claim} selection={props.selection} onSelect={props.onSelect} />
            ))}
          </ul>
        </section>
      ))}
    </article>
  );
}

function ClaimItem(props: { claim: Claim; selection: Selection | null; onSelect: (s: Selection) => void }) {
  const { claim } = props;
  return (
    <li className={`claim ${claim.status} ${claim.kind}`}>
      {claim.kind === "inference" && <span className="tag">inference</span>}
      {claim.status === "unverified" && <span className="tag warn">unverified</span>}
      {claim.status === "partial" && <span className="tag warn">partly verified</span>}
      {claim.text}{" "}
      {claim.citations.map((c, i) => (
        <CitationChip key={i} citation={c} selection={props.selection} onSelect={props.onSelect} />
      ))}
    </li>
  );
}

function CitationChip(props: { citation: Citation; selection: Selection | null; onSelect: (s: Selection) => void }) {
  const { citation: c, selection } = props;
  if (!c.cell_lines) {
    return (
      <span className="chip missing" title={`Quote not found in the notebook:\n${c.quote}`}>
        cell {c.cell} · not found
      </span>
    );
  }
  const [start, end] = c.cell_lines;
  const lines = start === end ? `L${start}` : `L${start}–${end}`;
  const active = selection?.cell === c.cell && selection.start === start && selection.end === end;
  let title = c.quote;
  if (c.status === "relocated") title = `The model named cell ${c.claimed_cell}; the code is in cell ${c.cell}.\n\n${title}`;
  if (c.match_count > 1) title = `${title}\n\n(matches ${c.match_count} places in this cell; showing the first)`;
  return (
    <button
      className={`chip ${c.status}${active ? " active" : ""}`}
      title={title}
      onClick={() => props.onSelect({ cell: c.cell, start, end })}
    >
      cell {c.cell} · {lines}
    </button>
  );
}
