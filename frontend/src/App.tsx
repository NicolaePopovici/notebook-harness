import { useEffect, useRef, useState } from "react";
import { api, AUDIENCES, type Audience, type Notebook, type Provider, type Run } from "./api";
import { DocumentView, type Selection } from "./DocumentView";
import { NotebookView } from "./NotebookView";

export const AUDIENCE_LABELS: Record<Audience, string> = {
  manager: "Manager",
  developer: "Developer",
  agent: "AI agent",
};

export function App() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [path, setPath] = useState("");
  const [provider, setProvider] = useState("");
  const [audiences, setAudiences] = useState<Audience[]>(AUDIENCES);

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [progress, setProgress] = useState<Partial<Record<Audience, string>>>({});
  const [tab, setTab] = useState<Audience>("manager");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const stopFollowing = useRef<() => void>(() => {});

  useEffect(() => {
    api
      .providers()
      .then((list) => {
        setProviders(list);
        setProvider(list.find((p) => p.default)?.name ?? list[0]?.name ?? "");
      })
      .catch((e: Error) => setError(e.message));
    return () => stopFollowing.current();
  }, []);

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    stopFollowing.current();
    setError("");
    setBusy(true);
    setRun(null);
    setProgress({});
    setSelection(null);
    try {
      const opened = await api.openNotebook(path.trim());
      setNotebook(opened);
      const { run_id } = await api.startRun(opened.id, provider, audiences);
      setTab(audiences[0]);
      stopFollowing.current = api.followRun(run_id, (e) => {
        if (e.audience) setProgress((p) => ({ ...p, [e.audience!]: e.message }));
        if (e.type !== "progress") api.run(run_id).then(setRun).catch((err: Error) => setError(err.message));
        if (e.type === "run_finished") setBusy(false);
      });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  function toggleAudience(audience: Audience) {
    setAudiences((current) =>
      current.includes(audience) ? current.filter((a) => a !== audience) : AUDIENCES.filter((a) => a === audience || current.includes(a)),
    );
  }

  const selectedProvider = providers.find((p) => p.name === provider);

  return (
    <div className="app">
      <form className="toolbar" onSubmit={generate}>
        <input
          className="path"
          placeholder="/absolute/path/to/notebook.py"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          required
        />
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p.name} value={p.name} disabled={!p.configured}>
              {p.name} ({p.model}){p.configured ? "" : ` · set ${p.api_key_env}`}
            </option>
          ))}
        </select>
        {AUDIENCES.map((a) => (
          <label key={a}>
            <input type="checkbox" checked={audiences.includes(a)} onChange={() => toggleAudience(a)} />
            {AUDIENCE_LABELS[a]}
          </label>
        ))}
        <button type="submit" disabled={busy || !audiences.length || !selectedProvider?.configured}>
          {busy ? "Generating…" : "Generate"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {notebook ? (
        <main className="workspace">
          <section className="documents">
            <nav className="tabs">
              {AUDIENCES.filter((a) => run?.documents[a] || run?.errors[a] || progress[a]).map((a) => (
                <button key={a} className={a === tab ? "active" : ""} onClick={() => setTab(a)}>
                  {AUDIENCE_LABELS[a]}
                </button>
              ))}
            </nav>
            <TabContent
              run={run}
              audience={tab}
              progress={progress[tab]}
              selection={selection}
              onSelect={setSelection}
            />
          </section>
          <NotebookView notebook={notebook} selection={selection} />
        </main>
      ) : (
        <p className="hint">Enter the full path of a Databricks notebook (.py) or Jupyter notebook (.ipynb) on this machine.</p>
      )}
    </div>
  );
}

function TabContent(props: {
  run: Run | null;
  audience: Audience;
  progress?: string;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  const document = props.run?.documents[props.audience];
  if (document) return <DocumentView document={document} selection={props.selection} onSelect={props.onSelect} />;
  const error = props.run?.errors[props.audience];
  if (error) return <div className="error">{error}</div>;
  return <p className="hint">{props.progress ?? "Starting…"}</p>;
}
