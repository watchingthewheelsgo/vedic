import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker, type DayPickerProps } from "react-day-picker";
import { cn } from "../../lib/cn";
import { Button } from "./button";

export function Calendar({ className, classNames, ...props }: DayPickerProps) {
  return (
    <DayPicker
      className={cn("p-1 text-ink", className)}
      classNames={{
        root: "w-fit",
        months: "flex flex-col gap-4",
        month: "space-y-4",
        nav: "absolute inset-x-0 top-2 flex items-center justify-between px-2",
        button_previous:
          "inline-flex size-8 items-center justify-center rounded-md text-gold-dim hover:bg-gold/10 disabled:opacity-40",
        button_next:
          "inline-flex size-8 items-center justify-center rounded-md text-gold-dim hover:bg-gold/10 disabled:opacity-40",
        month_caption: "relative flex h-9 items-center justify-center px-9 text-sm font-semibold",
        caption_label: "sr-only",
        month_grid: "w-full border-collapse",
        dropdowns: "flex items-center gap-2",
        dropdown:
          "rounded-md border border-gold/25 bg-white px-2 py-1 text-xs text-ink outline-none focus:border-gold",
        weekdays: "flex",
        weekday: "w-9 rounded-md text-[11px] font-medium uppercase tracking-wide text-muted",
        week: "mt-1 flex w-full",
        day: "size-9 p-0 text-center text-sm",
        day_button:
          "size-9 rounded-md text-sm transition hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/30",
        selected: "[&_button]:bg-gold [&_button]:text-white [&_button]:hover:bg-gold-dim",
        today: "[&_button]:border [&_button]:border-gold/40",
        outside: "text-muted/45",
        disabled: "pointer-events-none text-muted/35",
        ...classNames
      }}
      components={{
        Chevron: ({ orientation }) =>
          orientation === "left" ? <ChevronLeft className="size-4" /> : <ChevronRight className="size-4" />
      }}
      {...props}
    />
  );
}

export function CalendarButton({
  children,
  className,
  ...props
}: React.ComponentProps<typeof Button>) {
  return (
    <Button
      type="button"
      variant="outline"
      size="lg"
      className={cn("w-full justify-start border-gold/30 bg-white px-4 text-left font-normal text-ink hover:bg-white", className)}
      {...props}
    >
      {children}
    </Button>
  );
}
