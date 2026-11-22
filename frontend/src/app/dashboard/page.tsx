"use client";

import {
  ArrowDownLeft, ArrowUpRight, Banknote, CircleAlert, FileUp, ReceiptText, Sparkles, WalletCards,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CashFlowChart, CategoryChart } from "@/components/charts";
import { Badge, Empty, ErrorState, MonthField, PageTitle, Panel, Skeleton } from "@/components/shared";
import { TransactionsTable } from "@/components/transactions-table";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { query, type Dashboard, type TransactionPage, type Trends } from "@/lib/api";
import { money, monthName, percent, titleCase } from "@/lib/format";

function Metric({ title, value, note, icon: Icon, tone = "" }: {
  title: string; value: string; note: string; icon: LucideIcon; tone?: string;
}) {
  return <article className="metric">
    <div className="metric-head"><span>{title}</span><span className={`metric-icon ${tone}`}><Icon size={18} /></span></div>
    <strong className="tabular">{value}</strong><small>{note}</small>
  </article>;
}

export default function DashboardPage() {
  const [selected, setSelected] = useState("");
  const summary = useApi<Dashboard>(query("/dashboard/summary", { month: selected }));
  const data = summary.data;
  const month = selected || data?.month || "";
  const trends = useApi<Trends>("/analytics/trends");
  const recent = useApi<TransactionPage>(month ? query("/transactions", { month, page_size: 5 }) : null);
  const alerts = data?.budget_summary.budgets.filter((item) =>
    item.status === "over_budget" || (item.utilization_percent ?? 0) >= 80) ?? [];
  return <div className="page">
    <PageTitle label="FINANCIAL OVERVIEW" title="Dashboard" description="Track cash flow, spending, and budgets from your imported statements."
      actions={<>
        <MonthField value={month} onChange={setSelected} label="Dashboard month" />
        <Button variant="outline" asChild><Link href="/assistant"><Sparkles size={16} /> Ask FinPilot</Link></Button>
        <Button asChild><Link href="/imports"><FileUp size={16} /> Import statement</Link></Button>
      </>} />
    {summary.error && <ErrorState message={summary.error} retry={summary.refresh} />}
    {summary.loading && <div className="metric-grid">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="skeleton-metric" />)}</div>}
    {data && <>
      <div className="metric-grid">
        <Metric title="Total income" value={money(data.total_income_minor)} note="Imported credits" icon={ArrowDownLeft} />
        <Metric title="Total expenses" value={money(data.total_expenses_minor)} note="Imported debits" icon={ArrowUpRight} tone="blue" />
        <Metric title="Net cash flow" value={money(data.net_cash_flow_minor)} note="Income less expenses" icon={Banknote} />
        <Metric title="Budget utilization" value={percent(data.budget_summary.overall_utilization_percent)}
          note={data.budget_summary.budgets.length ? "Across allocated categories" : "No allocations configured"} icon={WalletCards} tone="amber" />
      </div>
      {data.availability === "no_records" && <div className="notice">
        <CircleAlert size={17} /><span>No imported records for {monthName(data.month)}. Import a statement or choose another month.</span>
      </div>}
    </>}
    <div className="split-grid">
      <Panel title="Cash flow history" description="Six months ending at the latest import.">
        {trends.loading ? <Skeleton className="skeleton-chart" /> : trends.error ? <ErrorState message={trends.error} retry={trends.refresh} /> :
          <CashFlowChart rows={trends.data?.months ?? []} />}
      </Panel>
      <Panel title="Spending by category" description={data ? monthName(data.month) : "Selected month"}>
        {summary.loading ? <Skeleton className="skeleton-chart" /> : data ?
          <CategoryChart categories={data.category_totals_minor} total={data.total_expenses_minor} /> :
          <p className="muted text-sm">Select a month to view spending.</p>}
      </Panel>
    </div>
    <div className="split-grid">
      <Panel title="Recent transactions" description={data ? `${data.transaction_count} imported records in ${monthName(data.month)}` : undefined}
        action={<Link className="text-link" href={query("/transactions", { month })}>View transactions</Link>}>
        {recent.loading ? <Skeleton /> : recent.error ? <ErrorState message={recent.error} retry={recent.refresh} /> :
          recent.data?.items.length ? <TransactionsTable rows={recent.data.items} compact /> :
          <Empty icon={ReceiptText} title="No recent transactions" text="Imported transactions for the selected month will appear here." />}
      </Panel>
      <Panel title="Budget alerts" description="Categories at 80% utilization or above."
        action={<Link className="text-link" href={query("/budgets", { month })}>Manage budgets</Link>}>
        {summary.loading ? <Skeleton /> : alerts.length ?
          <ul className="alert-list">{alerts.map((item) => <li key={item.category} className="alert-item">
            <span><strong>{titleCase(item.category)}</strong><small>{money(item.spent_minor)} spent of {money(item.budget_minor)}</small></span>
            <Badge tone={item.status === "over_budget" ? "red" : "amber"}>{item.status === "over_budget" ? "Over budget" : percent(item.utilization_percent)}</Badge>
          </li>)}</ul> :
          <Empty icon={WalletCards} title={data?.budget_summary.budgets.length && data.availability === "has_records" ? "No budget alerts" : "No alerts available"}
            text={data?.budget_summary.budgets.length ? "Alerts use spending from imported records for this month." : "Set a budget to track how much of your allocation you have used."} />}
      </Panel>
    </div>
  </div>;
}
