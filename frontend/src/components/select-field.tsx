import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function SelectControl({ className, children, ...props }: ComponentProps<"select">) {
  return <span className="select-wrap"><select className={cn("control", className)} {...props}>{children}</select><ChevronDown size={15} aria-hidden="true" /></span>;
}
