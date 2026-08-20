import * as React from "react";
import { cn } from "../../lib/cn";

function Progress({ value, className, ...props }: React.HTMLAttributes<HTMLDivElement> & { value?: number }) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-[var(--line)]", className)} {...props}>
      <div
        className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-500"
        style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }}
      />
    </div>
  );
}

export { Progress };
