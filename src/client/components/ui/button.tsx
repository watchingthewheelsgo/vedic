import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-sm font-medium transition-[background,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        gold: "border border-gold bg-gold text-white shadow-sm hover:bg-gold-dim",
        outline: "border border-gold bg-transparent text-gold hover:bg-gold/10",
        ghost: "border border-transparent bg-transparent text-muted hover:bg-gold/10 hover:text-ink",
        dark: "border border-gold/25 bg-night text-gold hover:bg-night-2",
        tab: "rounded-full border border-transparent bg-transparent px-4 py-2 text-muted hover:text-ink data-[active=true]:border-gold data-[active=true]:bg-gold data-[active=true]:text-white"
      },
      size: {
        sm: "h-9 px-3 text-xs",
        md: "h-11 px-5",
        lg: "h-[52px] px-7 text-[15px]",
        icon: "h-10 w-10 p-0"
      }
    },
    defaultVariants: {
      variant: "gold",
      size: "md"
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { buttonVariants };
