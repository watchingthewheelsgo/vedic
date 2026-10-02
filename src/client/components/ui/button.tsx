import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "press-feedback inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-[background,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cream/20 disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        gold: "border border-paper bg-paper text-[#16130e] shadow-[0_10px_30px_rgba(0,0,0,0.35)] hover:bg-white",
        outline:
          "border border-white/15 bg-transparent text-cream/80 hover:border-white/30 hover:bg-white/[0.05] hover:text-cream",
        ghost:
          "border border-transparent bg-transparent text-cream/60 hover:bg-white/[0.06] hover:text-cream",
        dark: "border border-white/10 bg-night-3 text-cream hover:bg-night-2",
        tab: "rounded-full border border-transparent bg-transparent px-4 py-2 text-cream/50 hover:text-cream data-[active=true]:border-paper data-[active=true]:bg-paper data-[active=true]:text-[#16130e]"
      },
      size: {
        sm: "h-9 px-3.5 text-xs",
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
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
