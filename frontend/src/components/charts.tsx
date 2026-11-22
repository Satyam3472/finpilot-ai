"use client";

import { Activity, ChartPie } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Empty } from "@/components/shared";
import { money, shortMonth, titleCase } from "@/lib/format";
import type { TrendRow } from "@/lib/api";

const SERIES = [
  { key: "total_income_minor", name: "Income", color: "var(--chart-teal)" },
  { key: "total_expenses_minor", name: "Expenses", color: "var(--chart-blue)" },
  { key: "net_cash_flow_minor", name: "Net cash flow", color: "var(--chart-slate)" },
];

const CATEGORY_COLORS = [
  "var(--chart-teal)", "var(--chart-blue)", "var(--chart-mint)",
  "var(--chart-amber)", "var(--chart-purple)", "var(--chart-slate)",
];

const axisMoney = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1,
});
const axisStyle = { fill: "var(--muted)", fontSize: 11 };
const tooltipStyle = { border: "1px solid var(--border)", borderRadius: 9, fontSize: 13 };

export function CashFlowChart({ rows, bars = false }: { rows: TrendRow[]; bars?: boolean }) {
  if (!rows.some((row) => row.status === "has_records")) {
    return <Empty icon={Activity} title="No cash-flow history" text="Import a statement to see how income and expenses change over time." />;
  }
  const series = bars ? SERIES.slice(0, 2) : SERIES;
  const Chart = bars ? BarChart : LineChart;
  return <>
    <div className="chart-legend">
      {series.map((item) => <span key={item.key}><i className="chart-dot" style={{ background: item.color }} />{item.name}</span>)}
    </div>
    <div className="chart" role="group" aria-label={bars ? "Income and expenses chart" : "Historical cash flow chart"}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <Chart data={rows} margin={{ top: 8, right: 10, left: 1, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" strokeDasharray="3 4" />
          <XAxis dataKey="month" tickFormatter={shortMonth} tick={axisStyle} axisLine={false} tickLine={false} tickMargin={10} />
          <YAxis tickFormatter={(value: number) => axisMoney.format(value / 100)} width={64} tick={axisStyle} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => typeof value === "number" ? money(value) : "—"} />
          {series.map((item) => bars ?
            <Bar key={item.key} dataKey={item.key} name={item.name} fill={item.color} radius={[4, 4, 0, 0]} maxBarSize={26} isAnimationActive={false} /> :
            <Line key={item.key} type="monotone" dataKey={item.key} name={item.name} stroke={item.color}
              strokeWidth={2.3} strokeDasharray={item.key === "net_cash_flow_minor" ? "5 4" : undefined}
              isAnimationActive={false} connectNulls={false} dot={{ r: 3, fill: item.color, strokeWidth: 0 }} />
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  </>;
}

export function CategoryChart({ categories, total }: { categories: Record<string, number>; total: number | null }) {
  const data = Object.entries(categories).sort((a, b) => b[1] - a[1])
    .map(([key, value], index) => ({ name: titleCase(key), value, color: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }));
  if (!data.length) {
    return <Empty icon={ChartPie} title="No expense categories" text="Expense categories will appear here when the selected month has imported expenses." />;
  }
  return <>
    <div className="donut-wrap" role="group" aria-label="Expense category chart">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={46} outerRadius={71} paddingAngle={3} isAnimationActive={false}>
            {data.map((item) => <Cell key={item.name} fill={item.color} stroke="none" />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => typeof value === "number" ? money(value) : "—"} />
        </PieChart>
      </ResponsiveContainer>
      <div className="donut-center"><small>Total expenses</small><strong className="tabular">{money(total)}</strong></div>
    </div>
    <ul className="category-list">
      {data.map((item) => <li key={item.name}>
        <span className="category-label"><i className="chart-dot" style={{ background: item.color }} />{item.name}</span>
        <strong className="tabular">{money(item.value)}</strong>
      </li>)}
    </ul>
  </>;
}
