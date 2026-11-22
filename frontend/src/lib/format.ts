const currency = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", minimumFractionDigits: 0, maximumFractionDigits: 2,
});
const monthLabel = new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
const dateLabel = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function money(minor: number | null | undefined) {
  return minor == null ? "—" : currency.format(minor / 100);
}
export function percent(value: number | null | undefined) {
  return value == null ? "—" : `${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value)}%`;
}
export function monthName(month: string) {
  return monthLabel.format(new Date(`${month}-01T00:00:00Z`));
}
export function shortMonth(month: string) {
  return new Intl.DateTimeFormat("en-IN", { month: "short", timeZone: "UTC" })
    .format(new Date(`${month}-01T00:00:00Z`));
}
export function displayDate(date: string) {
  return dateLabel.format(new Date(`${date.slice(0, 10)}T00:00:00Z`));
}
export function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/^\p{L}/u, (char) => char.toUpperCase());
}
export function toMinor(value: string) {
  if (!/^\d{1,13}(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, decimal = ""] = value.trim().split(".");
  const result = Number(whole) * 100 + Number(decimal.padEnd(2, "0"));
  return Number.isSafeInteger(result) && result <= 100_000_000_000_000 ? result : null;
}
export function priorMonth(month: string) {
  const date = new Date(`${month}-01T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() - 1);
  return date.toISOString().slice(0, 7);
}
