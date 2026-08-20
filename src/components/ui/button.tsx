import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        default: "bg-[var(--ink)] text-[var(--paper)] hover:bg-[var(--ink-soft)]",
        accent: "bg-[var(--accent)] text-white hover:bg-[var(--accent-dark)]",
        outline: "border border-[var(--line-strong)] bg-transparent text-[var(--ink)] hover:bg-white/60",
        secondary: "bg-[var(--panel-muted)] text-[var(--ink)] hover:bg-[var(--line)]",
        ghost: "text-[var(--muted)] hover:bg-black/5 hover:text-[var(--ink)]",
        destructive: "bg-red-50 text-red-700 hover:bg-red-100",
      },
      size: {
        default: "h-11 px-5",
        sm: "h-9 px-3.5 text-xs",
        lg: "h-13 px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
