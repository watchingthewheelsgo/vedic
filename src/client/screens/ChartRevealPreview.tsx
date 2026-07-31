import { useEffect, useMemo, useState } from "react";
import { ChartRevealProgress } from "../components/ChartRevealProgress";
import { deriveChartRevealState } from "../lib/chartRevealMapping";
import type { PipelineData, PipelineNode } from "../lib/pipeline";

/**
 * Dev-only preview route for the ChartRevealProgress prototype.
 * Not linked from any nav — visit /dev/chart-reveal directly.
 *
 * The "real pipeline simulation" panel below feeds deriveChartRevealState()
 * a synthetic PipelineData built from the native VedicDust node IDs so
 * this is the same code path Session.tsx will use once phase 3 wires it to
 * the real getCoreJob poll — only the data source changes, not the mapping.
 */

function buildSimulatedNodeOrder(): string[] {
  return ["chart_facts", "reader_prevalidation", "vedicdust_judgement", "vedicdust_consultation"];
}

const SIMULATED_ORDER = buildSimulatedNodeOrder();

function pipelineDataAtStep(step: number): PipelineData {
  const nodes: PipelineNode[] = SIMULATED_ORDER.map((id, index) => ({
    id,
    label: id,
    wave: 1,
    status: index < step ? "completed" : index === step ? "running" : "pending",
    files: [],
    dependencies: []
  }));
  const completed = nodes.filter((n) => n.status === "completed").length;
  return {
    nodes,
    status: step >= SIMULATED_ORDER.length - 1 ? "completed" : "running",
    percent: Math.round((completed / SIMULATED_ORDER.length) * 100),
    completed,
    total: SIMULATED_ORDER.length,
    failed: 0,
    durationSeconds: step * 4
  };
}

export function ChartRevealPreview() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setStep((prev) => (prev + 1) % SIMULATED_ORDER.length);
    }, 1400);
    return () => window.clearInterval(id);
  }, []);

  const pipelineData = useMemo(() => pipelineDataAtStep(step), [step]);
  const state = useMemo(() => deriveChartRevealState(pipelineData), [pipelineData]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 py-16">
      <div className="text-[10px] uppercase tracking-[3px] text-gold/70">
        Driven by deriveChartRevealState() + simulated real node IDs
      </div>
      <h1 className="text-xl font-semibold text-cream">命盘揭示 · 接真实节点结构的模拟</h1>
      <div className="text-[11px] text-cream/40">
        当前节点：{SIMULATED_ORDER[Math.min(step, SIMULATED_ORDER.length - 1)]}
      </div>
      <ChartRevealProgress state={state} />

      <div className="mt-10 text-[10px] uppercase tracking-[3px] text-gold/40">
        Below: original fixed-caption demo (no real data)
      </div>
      <ChartRevealProgress demo demoIntervalMs={2600} />
    </div>
  );
}
