import * as React from "react";
import { cn } from "../../lib/cn";

function Badge({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.12em]", className)}
      {...props}
    />
  );
}

export { Badge };
