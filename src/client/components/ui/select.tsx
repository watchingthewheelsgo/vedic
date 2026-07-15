import * as SelectPrimitive from "@radix-ui/react-select";
import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-[52px] w-full items-center justify-between gap-3 rounded-[10px] border border-gold/30 bg-white/5 px-4 text-left text-[15px] text-cream shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] outline-none transition placeholder:text-cream/35 focus:border-gold focus:bg-white/10 focus:ring-4 focus:ring-gold/15 disabled:cursor-not-allowed disabled:opacity-60 data-[placeholder]:text-cream/40 aria-invalid:border-red aria-invalid:bg-red/5",
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="size-4 shrink-0 text-gold-dim" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

export const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      position={position}
      className={cn(
        "cosmic-floating-surface z-50 max-h-80 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[10px] border border-gold/25 bg-[rgba(16,12,22,0.96)] p-1 text-cream shadow-[0_24px_70px_rgba(0,0,0,0.46)] backdrop-blur-xl",
        className
      )}
      {...props}
    >
      <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

export const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex cursor-default select-none items-center rounded-lg py-2.5 pl-9 pr-3 text-sm text-cream/58 outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-gold/15 data-[highlighted]:text-cream data-[state=checked]:text-cream",
      className
    )}
    {...props}
  >
    <span className="absolute left-3 flex size-4 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="size-4 text-gold-dim" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;
