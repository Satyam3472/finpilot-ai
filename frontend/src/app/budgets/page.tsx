import { BudgetsView } from "./budgets-view";

export const metadata = { title: "Budgets" };

export default async function BudgetsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const { month } = await searchParams;
  return <BudgetsView initialMonth={typeof month === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(month) ? month : ""} />;
}
