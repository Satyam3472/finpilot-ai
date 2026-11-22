"use client";

import { FileUp, ReceiptText, Search } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { SelectControl } from "@/components/select-field";
import { Empty, ErrorState, MonthField, PageTitle, Panel, Skeleton } from "@/components/shared";
import { TransactionsTable } from "@/components/transactions-table";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { query, type TransactionPage } from "@/lib/api";
import { titleCase } from "@/lib/format";

const categories = ["bills", "entertainment", "food", "healthcare", "income", "rent", "shopping", "travel", "uncategorized"];

export function TransactionsView({ initialMonth }: { initialMonth: string }) {
  const [month, setMonth] = useState(initialMonth);
  const [category, setCategory] = useState("");
  const [type, setType] = useState("");
  const [sort, setSort] = useState("desc");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const settledSearch = useDeferredValue(search);
  const records = useApi<TransactionPage>(query("/transactions", {
    month, category, type, sort, search: settledSearch, page, page_size: 15,
  }));
  const data = records.data;
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;
  const filtered = Boolean(month || category || type || settledSearch);

  function clear() {
    setMonth(""); setCategory(""); setType(""); setSearch(""); setSort("desc"); setPage(1);
  }

  return <div className="page">
    <PageTitle title="Transactions" description="Search and review the records imported from your statements."
      actions={<Button asChild><Link href="/imports"><FileUp size={16} /> Import statement</Link></Button>} />
    <Panel title="Transaction history" description={data ? `${data.total} ${data.total === 1 ? "record" : "records"}` : undefined}>
      <div className="filter-bar">
        <label className="field grow">Search<span className="search-control"><Search size={16} />
          <input className="control" value={search} maxLength={120} placeholder="Merchant or description"
            onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
        </span></label>
        <div className="field"><span aria-hidden="true">Month</span><MonthField label="Transaction month" value={month}
          onChange={(value) => { setMonth(value); setPage(1); }} /></div>
        <label className="field">Category<SelectControl value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}>
          <option value="">All categories</option>
          {categories.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
        </SelectControl></label>
        <label className="field">Type<SelectControl value={type} onChange={(event) => { setType(event.target.value); setPage(1); }}>
          <option value="">All types</option><option value="expense">Expense</option><option value="income">Income</option>
        </SelectControl></label>
        <label className="field">Date order<SelectControl value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
          <option value="desc">Newest first</option><option value="asc">Oldest first</option>
        </SelectControl></label>
        {filtered && <Button variant="ghost" onClick={clear}>Clear filters</Button>}
      </div>
      {records.loading && <Skeleton className="skeleton-chart" />}
      {records.error && <ErrorState message={records.error} retry={records.refresh} />}
      {data && (data.items.length ? <TransactionsTable rows={data.items} /> :
        <Empty icon={ReceiptText} title={filtered ? "No matching transactions" : "No transactions yet"}
          text={filtered ? "Try changing the filters or selecting another month." : "Import a CSV or XLSX statement to see records here."}
          action={filtered ? <Button variant="outline" onClick={clear}>Clear filters</Button> :
            <Button asChild><Link href="/imports">Import a statement</Link></Button>} />)}
      {data && totalPages > 1 && <div className="pagination">
        <span>Page {data.page} of {totalPages}</span><div>
          <Button variant="outline" size="small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button variant="outline" size="small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      </div>}
    </Panel>
  </div>;
}
