import {
  AtlasChartFirst,
  AtlasComposer,
  AtlasConversation,
  AtlasMark,
  useAtlas
} from "../components/Atlas";
import { useI18n } from "../i18n/provider";
import { atlasCopy } from "../lib/atlas";

export function Ask() {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { reading, useNotes, setUseNotes, turns, reset, hasChart } = useAtlas();
  return (
    <div className="mx-auto flex min-h-[calc(100dvh-9rem)] max-w-[760px] flex-col px-5 pt-8 sm:px-8 lg:min-h-[calc(100dvh-3rem)] lg:pt-10">
      <header className="flex items-center gap-3">
        <AtlasMark size={40} />
        <h1 className="min-w-0 flex-1 truncate font-display text-3xl leading-none">
          {copy.name}
          <span className="ml-3 hidden font-sans text-sm text-cream/45 sm:inline">
            {copy.tagline}
          </span>
        </h1>
        {turns.length > 0 && (
          <button
            type="button"
            onClick={reset}
            className="h-9 rounded-full border border-white/12 px-3.5 text-xs text-cream/70 hover:bg-white/[0.06]"
          >
            {copy.newChat}
          </button>
        )}
      </header>
      {hasChart === false ? (
        <AtlasChartFirst />
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-white/12 px-2.5 text-cream/65">
              <span className={`size-1.5 rounded-full ${reading ? "bg-gold" : "bg-white/25"}`} />
              {reading ? copy.chart : copy.noChart}
            </span>
            <label
              className="inline-flex h-7 cursor-pointer items-center gap-2 rounded-full border border-white/12 px-2.5 text-cream/65"
              title={copy.notesHint}
            >
              <input
                type="checkbox"
                checked={useNotes}
                onChange={(event) => setUseNotes(event.target.checked)}
                className="size-3.5 accent-[#f3f0e9]"
              />
              {copy.useNotes}
            </label>
          </div>
          <div className="flex-1 py-6">
            <AtlasConversation />
          </div>
          <div className="sticky bottom-24 space-y-2 bg-gradient-to-t from-night via-night to-transparent pb-3 pt-4 lg:bottom-0">
            <AtlasComposer />
            <p className="text-center text-[11px] text-cream/35">{copy.disclaimer}</p>
          </div>
        </>
      )}
    </div>
  );
}
