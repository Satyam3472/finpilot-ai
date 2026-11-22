import { CircleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function PageTitle({ label, title, description, actions }: {
  label?: string; title: string; description: string; actions?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {label && <div className="eyebrow">{label}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function MonthField({ value, onChange, label = "Month" }: {
  value: string; onChange: (value: string) => void; label?: string;
}) {
  return (
    <label className="month-field">
      <span className="sr-only">{label}</span>
      <input type="month" min="0001-01" max="9999-12" value={value}
        onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function Panel({ title, description, action, children, className }: {
  title: string; description?: string; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("panel", className)}>
      <div className="panel-heading">
        <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Empty({ icon: Icon, title, text, action }: {
  icon: LucideIcon; title: string; text: string; action?: ReactNode;
}) {
  return <div className="empty-state">
    <span className="empty-icon"><Icon size={22} aria-hidden="true" /></span>
    <h3>{title}</h3><p>{text}</p>{action}
  </div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state" role="alert">
    <CircleAlert size={19} aria-hidden="true" /><div>{message}</div>
    {retry && <Button size="small" variant="outline" onClick={retry}>Try again</Button>}
  </div>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} role="status" aria-label="Loading" />;
}

export function Badge({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "green" | "amber" | "red" | "teal";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
