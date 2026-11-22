import { Badge } from "@/components/shared";
import { displayDate, money, titleCase } from "@/lib/format";
import type { Transaction } from "@/lib/api";

export function TransactionsTable({ rows, compact = false }: { rows: Transaction[]; compact?: boolean }) {
  return <div className="scroll-table" tabIndex={0} aria-label="Scrollable transactions">
    <table className="data-table">
      <thead><tr>
        <th scope="col">Transaction</th><th scope="col">Date</th><th scope="col">Category</th>
        {!compact && <th scope="col">Type</th>}<th scope="col" className="amount-column">Amount</th>
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.id}>
        <td>
          <span className="row-title">{row.merchant ?? row.description}</span>
          {!compact && row.merchant && <span className="row-description">{row.description}</span>}
          {!compact && row.needs_review && <Badge tone="amber">Needs review</Badge>}
        </td>
        <td className="date-column">{displayDate(row.date)}</td>
        <td><Badge>{titleCase(row.category)}</Badge></td>
        {!compact && <td><Badge tone={row.type === "income" ? "green" : "neutral"}>{titleCase(row.type)}</Badge></td>}
        <td className={`amount-column ${row.type === "income" ? "positive" : ""}`}>
          {row.type === "income" ? "+" : "−"}{money(row.amount_minor)}
        </td>
      </tr>)}</tbody>
    </table>
  </div>;
}
