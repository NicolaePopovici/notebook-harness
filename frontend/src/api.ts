// Types mirror the Pydantic models in backend/parsing/models.py, backend/pipeline/models.py and backend/api/schemas.py.

export type Audience = "manager" | "developer" | "agent";
export const AUDIENCES: Audience[] = ["manager", "developer", "agent"];

export interface Line {
  cell_line: number;
  file_line: number | null;
  text: string;
}

export interface Cell {
  index: number;
  lang: string;
  title: string | null;
  lines: Line[];
}

export interface Notebook {
  id: string;
  path: string;
  name: string;
  format: string;
  sha256: string;
  cells: Cell[];
}

export interface Citation {
  cell: number;
  quote: string;
  status: "verified" | "relocated" | "not_found";
  cell_lines: [number, number] | null;
  file_lines: [number, number] | null;
  match_count: number;
  claimed_cell: number | null;
}

export interface Claim {
  id: string;
  text: string;
  kind: "fact" | "inference";
  status: "verified" | "partial" | "unverified";
  citations: Citation[];
  repaired: boolean;
}

export interface ValidationReport {
  claims_total: number;
  claims_verified: number;
  claims_partial: number;
  claims_unverified: number;
  missing_sections: string[];
}

export interface Document {
  audience: Audience;
  title: string;
  sections: { heading: string; claims: Claim[] }[];
  validation: ValidationReport;
  model: string;
}

export interface RunEvent {
  seq: number;
  type: "run_started" | "progress" | "document_ready" | "document_failed" | "run_finished";
  audience: Audience | null;
  message: string;
}

export interface Run {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  model: string;
  documents: Partial<Record<Audience, Document>>;
  errors: Partial<Record<Audience, string>>;
}

export interface Provider {
  name: string;
  model: string;
  default: boolean;
  configured: boolean;
  api_key_env: string | null;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return body as T;
}

export const api = {
  providers: () => request<Provider[]>("/api/providers"),

  async openNotebook(path: string): Promise<Notebook> {
    const { id } = await request<{ id: string }>("/api/notebooks", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    return request<Notebook>(`/api/notebooks/${id}`);
  },

  // Always regenerates: pressing Generate never returns cached documents.
  startRun: (notebookId: string, provider: string, audiences: Audience[]) =>
    request<{ run_id: string }>(`/api/notebooks/${notebookId}/runs`, {
      method: "POST",
      body: JSON.stringify({ provider, audiences, force: true }),
    }),

  run: (runId: string) => request<Run>(`/api/runs/${runId}`),

  /** Calls onEvent for every run event until the run finishes. Returns a function that stops listening. */
  followRun(runId: string, onEvent: (event: RunEvent) => void): () => void {
    const source = new EventSource(`/api/runs/${runId}/events`);
    const types: RunEvent["type"][] = ["run_started", "progress", "document_ready", "document_failed", "run_finished"];
    for (const type of types) {
      source.addEventListener(type, (e) => {
        const event = JSON.parse((e as MessageEvent).data) as RunEvent;
        // The server ends the stream after run_finished; close so the browser doesn't reconnect.
        if (event.type === "run_finished") source.close();
        onEvent(event);
      });
    }
    return () => source.close();
  },
};
