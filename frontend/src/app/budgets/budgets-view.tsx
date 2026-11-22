"use client";

import { Pencil, Plus, Trash2, WalletCards } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { SelectControl } from "@/components/select-field";
import { Badge, Empty, ErrorState, MonthField, PageTitle, Panel, Skeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useApi } from "@/hooks/use-api";
import { api, jsonBody, query, type Budget, type BudgetSummary, type Dashboard } from "@/lib/api";
import { money, monthName, percent, titleCase, toMinor } from "@/lib/format";

type Editor = { mode: "create" | "edit" | "delete"; month: string; category: string; amount: string };

function BudgetCard({ item, onEdit, onDelete }: { item: Budget; onEdit: () => void; onDelete: () => void }) {
  const over = item.status === "over_budget";
  const configured = item.utilization_percent != null;
  return <Panel title={titleCase(item.category)} className="budget-card" action={
    <Badge tone={over ? "red" : item.status === "insufficient_data" ? "amber" : "teal"}>
      {over ? "Over budget" : item.status === "insufficient_data" ? "No spending data" : "Within budget"}
    </Badge>
  }>
    <div className="budget-allocation tabular">{money(item.budget_minor)}<small>Monthly allocation</small></div>
    <div className="budget-progress">
      <span>{configured ? `${percent(item.utilization_percent)} used` : item.budget_minor === 0 ? "Zero allocation" : "Utilization unavailable"}</span>
      {configured && <div className={`progress-track ${over ? "over" : ""}`} role="progressbar" aria-label={`${titleCase(item.category)} budget used`}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(item.utilization_percent!, 100)}
        aria-valuetext={percent(item.utilization_percent)}>
        <span style={{ width: `${Math.min(item.utilization_percent!, 100)}%` }} />
      </div>}
    </div>
    <dl className="budget-stats"><div><dt>Spent</dt><dd>{money(item.spent_minor)}</dd></div>
      <div><dt>Remaining</dt><dd className={over ? "negative" : ""}>{money(item.remaining_minor)}</dd></div></dl>
    <div className="budget-controls">
      <Button size="small" variant="outline" onClick={onEdit} aria-label={`Edit ${item.category} budget`}><Pencil size={15} /> Edit</Button>
      <Button size="small" variant="ghost" onClick={onDelete} aria-label={`Delete ${item.category} budget`}><Trash2 size={16} /></Button>
    </div>
  </Panel>;
}

export function BudgetsView({ initialMonth }: { initialMonth: string }) {
  const [selected, setSelected] = useState(initialMonth);
  const defaultMonth = useApi<Dashboard>(selected ? null : "/dashboard/summary");
  const month = selected || defaultMonth.data?.month || "";
  const summary = useApi<BudgetSummary>(month ? query("/budgets", { month }) : null);
  const [editor, setEditor] = useState<Editor>();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const newBudgetButton = useRef<HTMLButtonElement>(null);
  const data = summary.data;
  const allocated = new Set(data?.budgets.map((item) => item.category));
  const choices = data?.categories.filter((name) => !allocated.has(name)) ?? [];
  const canCreate = Boolean(month && choices.length);

  function open(mode: Editor["mode"], item?: Budget) {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setError("");
    setEditor({
      mode, month, category: item?.category ?? choices[0] ?? "",
      amount: item ? (item.budget_minor / 100).toFixed(2) : "",
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || pending) return;
    const target = `/budgets/${editor.month}/${encodeURIComponent(editor.category)}`;
    const amount = toMinor(editor.amount);
    if (editor.mode !== "delete" && amount === null) {
      setError("Enter a nonnegative amount in INR with up to two decimal places.");
      return;
    }
    setError("");
    setPending(true);
    try {
      if (editor.mode === "delete") {
        await api(target, { method: "DELETE" });
        toast.success(`${titleCase(editor.category)} budget deleted.`);
      } else {
        await api<BudgetSummary>(target, { method: "PUT", ...jsonBody({ amount_minor: amount }) });
        toast.success(`${titleCase(editor.category)} budget saved.`);
      }
      setEditor(undefined);
      summary.refresh();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "The budget could not be updated.");
    } finally {
      setPending(false);
    }
  }

  return <div className="page">
    <PageTitle title="Budgets" description="Plan monthly category allocations and see how much you have used."
      actions={<>
        <MonthField value={month} onChange={setSelected} label="Budget month" />
        <Button ref={newBudgetButton} disabled={!canCreate} onClick={() => open("create")}><Plus size={17} /> New budget</Button>
      </>} />
    {defaultMonth.error && <ErrorState message={defaultMonth.error} retry={defaultMonth.refresh} />}
    {summary.error && <ErrorState message={summary.error} retry={summary.refresh} />}
    {(defaultMonth.loading || summary.loading) && <div className="budget-grid">{[0, 1, 2].map((index) => <Skeleton key={index} className="skeleton-chart" />)}</div>}
    {data && data.budgets.length === 0 && <Panel title={monthName(data.month)}>
      <Empty icon={WalletCards} title="No budgets for this month" text="Set a category allocation to track spending against it."
        action={<Button disabled={!canCreate} onClick={() => open("create")}><Plus size={16} /> Create a budget</Button>} />
    </Panel>}
    {data && data.budgets.length > 0 && <>
      {!data.has_imported_records && <p className="notice">No imported records for {monthName(data.month)}. Spending and remaining amounts are unavailable.</p>}
      <div className="budget-grid">{data.budgets.map((item) => <BudgetCard key={item.category} item={item}
        onEdit={() => open("edit", item)} onDelete={() => open("delete", item)} />)}</div>
    </>}

    <Dialog open={Boolean(editor)} onOpenChange={(value) => { if (!value && !pending) setEditor(undefined); }}>
      {editor && <DialogContent onCloseAutoFocus={(event) => {
        event.preventDefault();
        const target = opener.current?.isConnected ? opener.current : newBudgetButton.current;
        target?.focus();
      }}>
        <DialogTitle>{editor.mode === "delete" ? "Delete budget?" : editor.mode === "edit" ? "Edit budget" : "Create budget"}</DialogTitle>
        <DialogDescription>{editor.mode === "delete" ?
          `Remove the ${titleCase(editor.category)} allocation for ${monthName(editor.month)}. Imported transactions are kept.` :
          `Set the category allocation for ${monthName(editor.month)}.`}</DialogDescription>
        <form onSubmit={submit} className="budget-form">
          {editor.mode !== "delete" && <>
            <label className="field">Category<SelectControl value={editor.category} disabled={editor.mode === "edit" || pending}
              onChange={(event) => setEditor({ ...editor, category: event.target.value })}>
              {(editor.mode === "edit" ? [editor.category] : choices).map((name) => <option key={name} value={name}>{titleCase(name)}</option>)}
            </SelectControl></label>
            <label className="field">Amount (INR)<input className="control" inputMode="decimal" autoComplete="off"
              value={editor.amount} disabled={pending} placeholder="0.00"
              onChange={(event) => setEditor({ ...editor, amount: event.target.value })} /></label>
          </>}
          {error && <ErrorState message={error} />}
          <div className="dialog-actions">
            <Button variant="outline" disabled={pending} onClick={() => setEditor(undefined)}>Cancel</Button>
            <Button variant={editor.mode === "delete" ? "danger" : "default"} type="submit" disabled={pending}>
              {pending ? "Saving…" : editor.mode === "delete" ? "Delete budget" : "Save budget"}
            </Button>
          </div>
        </form>
      </DialogContent>}
    </Dialog>
  </div>;
}
