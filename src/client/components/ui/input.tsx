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
      "h-[52px] w-full rounded-[10px] border border-gold/30 bg-white/5 px-4 text-[15px] text-cream shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] outline-none transition placeholder:text-cream/35 focus:border-gold focus:bg-white/10 focus:ring-4 focus:ring-gold/15 disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-red aria-invalid:bg-red/5",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";
