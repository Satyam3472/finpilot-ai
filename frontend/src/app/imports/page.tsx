"use client";

import { CheckCircle2, FileSpreadsheet, FileUp, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { Badge, Empty, ErrorState, PageTitle, Panel, Skeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { api, type ImportBatch, type ImportResult } from "@/lib/api";
import { displayDate, titleCase } from "@/lib/format";

const FILE_LIMIT = 5 * 1024 * 1024;

export default function ImportsPage() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [dragOver, setDragOver] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult>();
  const history = useApi<ImportBatch[]>("/imports");

  function choose(value?: File) {
    setError("");
    setResult(undefined);
    setFile(undefined);
    if (!value) return;
    if (!/\.(csv|xlsx)$/i.test(value.name)) setError("Choose a CSV or XLSX file.");
    else if (value.size > FILE_LIMIT) setError("The file exceeds the 5 MiB limit.");
    else if (value.size === 0) setError("The selected file is empty.");
    else setFile(value);
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragOver(false);
    if (pending) return;
    if (event.dataTransfer.files.length !== 1) {
      choose();
      setError("Choose one statement at a time.");
      return;
    }
    choose(event.dataTransfer.files[0]);
  }

  async function upload() {
    if (!file || pending) return;
    setPending(true);
    setError("");
    setResult(undefined);
    const body = new FormData();
    body.set("file", file);
    try {
      const outcome = await api<ImportResult>("/statements/upload", { method: "POST", body });
      setResult(outcome);
      history.refresh();
      setFile(undefined);
      if (outcome.already_imported) toast.info("This statement was already imported.");
      else if (outcome.imported_rows) toast.success(`${outcome.imported_rows} transactions imported.`);
      else toast.warning("No transactions were imported. Review the row errors.");
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "The statement could not be imported.");
    } finally {
      setPending(false);
    }
  }

  return <div className="page">
    <PageTitle title="Import statements" description="Add CSV or Excel statements to your local transaction history." />
    <div className="split-grid import-grid">
      <Panel title="Upload a statement" description="Choose one file up to 5 MiB.">
        <input ref={input} type="file" className="sr-only" aria-label="Statement file" tabIndex={-1} accept=".csv,.xlsx"
          onChange={(event) => { choose(event.target.files?.[0]); event.target.value = ""; }} />
        <div className={`drop-zone ${dragOver ? "is-dragging" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)} onDrop={drop}>
          <span className="drop-icon"><UploadCloud size={26} /></span>
          <strong>Drag a statement here</strong>
          <span>CSV or XLSX · 5 MiB maximum</span>
          <Button variant="outline" disabled={pending} onClick={() => input.current?.click()}>Choose file</Button>
        </div>
        {file && <div className="selected-file"><FileSpreadsheet size={20} />
          <span><strong>{file.name}</strong><small>{Math.ceil(file.size / 1024)} KB</small></span>
          <Button size="icon" variant="ghost" disabled={pending} aria-label="Remove selected file" onClick={() => choose()}><X size={17} /></Button>
        </div>}
        {error && <ErrorState message={error} />}
        {file && <div className="upload-footer">
          <Button onClick={upload} disabled={pending}><FileUp size={16} /> Import statement</Button>
          {pending && <span role="status"><LoaderCircle size={16} className="animate-spin" /> Uploading and processing…</span>}
        </div>}
      </Panel>
      <Panel title="Statement format" description="Use the first worksheet for XLSX files.">
        <dl className="format-list">
          <div><dt>Date</dt><dd>Use an unambiguous date such as 2026-10-02.</dd></div>
          <div><dt>Description</dt><dd>Enter a short transaction description.</dd></div>
          <div><dt>Debit or credit</dt><dd>Enter an INR amount in one column and leave the other blank or zero.</dd></div>
        </dl>
        <p className="notice"><FileSpreadsheet size={17} /> Required headers are date, description, debit, and credit. Excel formulas are rejected.</p>
      </Panel>
    </div>
    {result && <Panel title={result.already_imported ? "Statement already imported" : "Import summary"}
      description={result.already_imported ? "This file matches a previously imported statement. No records were added." : `${result.total_rows} statement rows processed.`}>
      {!result.already_imported && <>
        <dl className="result-grid" aria-label="Import counts">
          {[
            ["Imported", result.imported_rows], ["Rejected", result.rejected_rows],
            ["Uncategorized", result.uncategorized_transactions], ["Potential overlaps", result.potential_duplicates],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
        {result.errors.length > 0 && <details className="row-errors" open>
          <summary>Rejected-row details ({result.errors.length})</summary>
          <ul>{result.errors.map((item) => <li key={item.row}>Row {item.row} · {item.error}</li>)}</ul>
        </details>}
      </>}
    </Panel>}
    <Panel title="Import history" description="The 100 most recent import batches.">
      {history.loading && <Skeleton />}
      {history.error && <ErrorState message={history.error} retry={history.refresh} />}
      {history.data?.length ? <div className="scroll-table" tabIndex={0} aria-label="Scrollable import history">
        <table className="data-table">
          <thead><tr><th scope="col">Statement</th><th scope="col">Imported on</th><th scope="col">Status</th><th scope="col">Imported</th><th scope="col">Rejected</th></tr></thead>
          <tbody>{history.data.map((batch) => <tr key={batch.id}>
            <td className="row-title">{batch.file_name}</td><td className="date-column">{displayDate(batch.imported_at)}</td>
            <td><Badge tone={batch.status === "imported" ? "green" : batch.status === "partial" ? "amber" : "red"}>{titleCase(batch.status)}</Badge></td>
            <td>{batch.imported_rows}</td><td>{batch.rejected_rows}</td>
          </tr>)}</tbody>
        </table>
      </div> : history.data && <Empty icon={CheckCircle2} title="No import history" text="Previous imports and their results will be listed here." />}
    </Panel>
  </div>;
}
