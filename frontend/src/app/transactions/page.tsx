import { TransactionsView } from "./transactions-view";

export const metadata = { title: "Transactions" };

export default async function TransactionsPage({ searchParams }: { searchParams: Promise<{ month?: string }> }) {
  const { month } = await searchParams;
  return <TransactionsView initialMonth={typeof month === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(month) ? month : ""} />;
}
