import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-[10.5px] font-bold leading-none",
  {
    variants: {
      variant: {
        neutral: "border-gold/25 bg-cream-2 text-muted",
        gold: "border-gold bg-gold text-night",
        done: "border-gold/35 bg-gold/10 text-gold-dim",
        error: "border-red bg-red text-white"
      }
    },
    defaultVariants: {
      variant: "neutral"
    }
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />;
}
