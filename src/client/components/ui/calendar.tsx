import * as React from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { DayPicker, type DayPickerProps } from "react-day-picker";
import { cn } from "../../lib/cn";

export function Calendar({ className, classNames, ...props }: DayPickerProps) {
  return (
    <DayPicker
      className={cn("p-1 text-ink [--rdp-accent-color:theme(colors.gold)]", className)}
      classNames={{
        root: "w-fit",
        months: "flex flex-col gap-4",
        month: "space-y-4",
        nav: "pointer-events-none absolute inset-x-0 top-2 z-10 flex items-center justify-between px-2",
        button_previous:
          "pointer-events-auto inline-flex size-8 items-center justify-center rounded-md text-gold-dim transition hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 aria-disabled:cursor-not-allowed aria-disabled:opacity-40 aria-disabled:hover:bg-transparent disabled:cursor-not-allowed disabled:opacity-40",
        button_next:
          "pointer-events-auto inline-flex size-8 items-center justify-center rounded-md text-gold-dim transition hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 aria-disabled:cursor-not-allowed aria-disabled:opacity-40 aria-disabled:hover:bg-transparent disabled:cursor-not-allowed disabled:opacity-40",
        month_caption: "relative flex h-9 items-center justify-center px-9 text-sm font-semibold",
        caption_label: "sr-only",
        month_grid: "w-full border-collapse",
        dropdowns: "flex items-center gap-2",
        dropdown:
          "rounded-md border border-gold/25 bg-white px-2 py-1 text-xs text-ink outline-none transition focus:border-gold focus:ring-4 focus:ring-gold/15",
        weekdays: "flex",
        weekday: "w-9 rounded-md text-[11px] font-medium uppercase tracking-wide text-muted",
        week: "mt-1 flex w-full",
        day: "size-9 p-0 text-center text-sm",
        day_button:
          "size-9 rounded-md text-sm transition hover:bg-gold/10 hover:text-ink focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 aria-selected:bg-gold aria-selected:text-white aria-selected:hover:bg-gold-dim",
        selected:
          "text-white [&_button]:bg-gold [&_button]:text-white [&_button]:shadow-sm [&_button]:hover:bg-gold-dim [&_button]:focus-visible:ring-gold/25",
        today: "[&_button]:border [&_button]:border-gold/45 [&_button]:text-gold-dim",
        outside: "text-muted/45",
        disabled: "pointer-events-none text-muted/35",
        ...classNames
      }}
      components={{
        Chevron: ({ orientation, className }) => {
          const iconClassName = cn("size-4", className);
          if (orientation === "left") return <ChevronLeft className={iconClassName} />;
          if (orientation === "right") return <ChevronRight className={iconClassName} />;
          if (orientation === "up") return <ChevronUp className={iconClassName} />;
          return <ChevronDown className={iconClassName} />;
        }
      }}
      {...props}
    />
  );
}
