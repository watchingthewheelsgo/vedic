import * as React from "react";
import { cn } from "../../lib/cn";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type = "text", ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "h-[52px] w-full rounded-[9px] border border-white/12 bg-white/[0.035] px-4 text-[15px] text-cream shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] outline-none transition placeholder:text-cream/30 focus:border-gold/70 focus:bg-white/[0.055] focus:ring-2 focus:ring-gold/15 disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-red aria-invalid:bg-red/5",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";
