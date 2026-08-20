import * as React from "react";
import { cn } from "../../lib/cn";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-12 w-full rounded-xl border border-[var(--line-strong)] bg-white/70 px-4 text-sm text-[var(--ink)] outline-none transition placeholder:text-[var(--muted-light)] focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent)]/10 disabled:cursor-not-allowed disabled:bg-[var(--panel-muted)]",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
