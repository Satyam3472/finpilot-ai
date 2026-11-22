"use client";

import { Activity, ChartNoAxesCombined, CircleHelp, Lightbulb, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { CashFlowChart, CategoryChart } from "@/components/charts";
import { SelectControl } from "@/components/select-field";
import { Badge, Empty, ErrorState, MonthField, PageTitle, Panel, Skeleton } from "@/components/shared";
import { useApi } from "@/hooks/use-api";
import { query, type Anomalies, type Comparison, type Dashboard, type Savings, type Trends } from "@/lib/api";
import { displayDate, money, monthName, percent, priorMonth, titleCase } from "@/lib/format";

function SpendingComparison({ item }: { item: Comparison }) {
  if (item.status === "insufficient_data") {
    return <Empty icon={ChartNoAxesCombined} title="Comparison unavailable"
      text={`No imported records for ${item.missing_months.map(monthName).join(" and ")}. Import both periods to compare them.`} />;
  }
  return <div className="comparison-result">
    <dl className="budget-stats comparison-stats">
      <div><dt>{monthName(item.month1)}</dt><dd>{money(item.month1_expenses_minor)}</dd></div>
      <div><dt>{monthName(item.month2)}</dt><dd>{money(item.month2_expenses_minor)}</dd></div>
    </dl>
    <div className="notice"><Activity size={16} /><span>
      {item.status === "unchanged" ? "Imported expenses were unchanged." :
        `${titleCase(item.status)} of ${money(item.absolute_difference_minor)}.`}
      {" "}{item.change_percent == null ? "Percentage change is undefined for a zero baseline." :
        `${percent(item.change_percent)} change from the baseline.`}
    </span></div>
  </div>;
}

export default function AnalyticsPage() {
  const [selected, setSelected] = useState("");
  const [baselineMonth, setBaselineMonth] = useState("");
  const [windowMonths, setWindowMonths] = useState(6);
  const dashboard = useApi<Dashboard>(query("/dashboard/summary", { month: selected }));
  const month = selected || dashboard.data?.month || "";
  const baseline = baselineMonth || (month && month !== "0001-01" ? priorMonth(month) : "");
  const history = useApi<Trends>(query("/analytics/trends", { months: windowMonths }));
  const compare = useApi<Comparison>(baseline && month ? query("/analytics/comparison", { month1: baseline, month2: month }) : null);
  const anomalies = useApi<Anomalies>(month ? query("/analytics/anomalies", { month }) : null);
  const savings = useApi<Savings>(month ? query("/insights/savings", { month }) : null);
  const trendRows = history.data?.months ?? [];

  return <div className="page">
    <PageTitle title="Analytics" description="Explore spending patterns, month-to-month changes, and expenses worth reviewing."
      actions={<MonthField label="Analytics month" value={month} onChange={setSelected} />} />
    {dashboard.error && <ErrorState message={dashboard.error} retry={dashboard.refresh} />}
    <div className="split-grid">
      <Panel title="Income vs. expenses" description="Imported cash flow ending at the latest recorded month."
        action={<SelectControl aria-label="Trend range" value={windowMonths} onChange={(event) => setWindowMonths(Number(event.target.value))}>
          <option value={3}>3 months</option><option value={6}>6 months</option><option value={12}>12 months</option><option value={24}>24 months</option>
        </SelectControl>}>
        {history.loading ? <Skeleton className="skeleton-chart" /> : history.error ? <ErrorState message={history.error} retry={history.refresh} /> : <>
          <CashFlowChart rows={trendRows} bars />
          {trendRows.some((item) => item.status === "no_records") && <p className="chart-footnote">Periods without imported records are left blank.</p>}
        </>}
      </Panel>
      <Panel title="Category breakdown" description={month ? monthName(month) : "Selected month"}>
        {dashboard.loading ? <Skeleton className="skeleton-chart" /> : dashboard.data ?
          <CategoryChart categories={dashboard.data.category_totals_minor} total={dashboard.data.total_expenses_minor} /> :
          <p className="muted text-sm">Category results are unavailable.</p>}
      </Panel>
    </div>
    <div className="split-grid even-grid">
      <Panel title="Compare expenses" description="Compare the selected month with a baseline month.">
        <div className="filter-bar">
          <div className="field"><span>Baseline month</span><MonthField value={baseline} onChange={setBaselineMonth} label="Baseline month" /></div>
          {month && <span className="comparison-target">Compare with <strong>{monthName(month)}</strong></span>}
        </div>
        {(dashboard.loading && !month) || compare.loading ? <Skeleton /> : compare.error ?
          <ErrorState message={compare.error} retry={compare.refresh} /> : compare.data ? <SpendingComparison item={compare.data} /> :
          <p className="muted text-sm">Choose two months to compare.</p>}
      </Panel>
      <Panel title="Savings opportunities" description="Observations from spending history and saved budgets.">
        {(dashboard.loading && !month) || savings.loading ? <Skeleton /> : savings.error ?
          <ErrorState message={savings.error} retry={savings.refresh} /> : savings.data && <>
          {savings.data.observations.length ? <ul className="observation-list">
            {savings.data.observations.map((item) => <li key={`${item.category}-${item.type}`}>
              <span className="observation-icon"><Lightbulb size={18} /></span>
              <div><strong>{titleCase(item.category)}</strong> <Badge tone={item.type === "over_budget" ? "red" : "amber"}>{titleCase(item.type)}</Badge>
                <p>{item.evidence.spent_minor != null && `${money(item.evidence.spent_minor)} spent`}
                  {item.evidence.budget_minor != null && ` · ${money(item.evidence.budget_minor)} budget`}
                  {item.evidence.previous_spent_minor != null && ` · ${money(item.evidence.previous_spent_minor)} previous month`}</p>
                <p>{item.suggested_action}</p>
              </div>
            </li>)}
          </ul> : <Empty icon={Lightbulb} title={savings.data.status === "insufficient_data" ? "Not enough records" : "No savings observations"}
            text={savings.data.status === "insufficient_data" ? "Import transactions for this month to receive evidence-based observations." :
              "No qualifying budget or discretionary-spending changes were found in the available records."} />}
          {savings.data.status !== "insufficient_data" && savings.data.comparison_status === "insufficient_data" &&
            <p className="chart-footnote">The preceding month has no imported records to compare.</p>}
        </>}
      </Panel>
    </div>
    <Panel title="Unusual expense candidates" description={month ? `Expenses worth reviewing in ${monthName(month)}.` : "Statistical review of large expenses."}>
      {(dashboard.loading && !month) || anomalies.loading ? <Skeleton /> : anomalies.error ?
        <ErrorState message={anomalies.error} retry={anomalies.refresh} /> : anomalies.data && <>
        {anomalies.data.unusual_transactions.length ? <div className="scroll-table" tabIndex={0} aria-label="Scrollable unusual expenses">
          <table className="data-table">
            <thead><tr><th scope="col">Date</th><th scope="col">Category</th><th scope="col">Score</th><th scope="col" className="amount-column">Expense</th></tr></thead>
            <tbody>{anomalies.data.unusual_transactions.map((item, index) => <tr key={`${item.date}-${item.category}-${index}`}>
              <td className="date-column">{displayDate(item.date)}</td><td>{titleCase(item.category)}</td>
              <td><Badge tone="amber">{item.score.toFixed(2)}</Badge></td><td className="amount-column">{money(item.amount_minor)}</td>
            </tr>)}</tbody>
          </table>
          {anomalies.data.flagged_count > anomalies.data.unusual_transactions.length &&
            <p className="chart-footnote">Showing {anomalies.data.unusual_transactions.length} of {anomalies.data.flagged_count} candidates.</p>}
        </div> : <Empty icon={TriangleAlert} title={anomalies.data.status === "insufficient_data" ? "Insufficient comparable history" : "No expenses flagged"}
          text={anomalies.data.reason ?? "The available category history did not produce a flag for this month."} />}
        <div className="notice anomaly-note"><CircleHelp size={18} /><span>
          The detector uses a modified Z-score above {anomalies.data.threshold} based on at least {anomalies.data.minimum_history} prior same-category expenses.
          {" "}{anomalies.data.note}
        </span></div>
        {Object.entries(anomalies.data.categories).some(([, item]) => item.status !== "evaluated") &&
          <details className="coverage"><summary>Category coverage and limitations</summary><ul>
            {Object.entries(anomalies.data.categories).filter(([, item]) => item.status !== "evaluated").map(([name, item]) =>
              <li key={name}><strong>{titleCase(name)}</strong> · {item.reason} ({item.history_count} prior expenses)</li>)}
          </ul></details>}
      </>}
    </Panel>
  </div>;
}
