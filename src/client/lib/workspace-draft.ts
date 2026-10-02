import { createContext, useContext, useEffect } from "react";
export const DraftContext = createContext<{
  setDirty: (dirty: boolean) => void;
  confirmLeave: () => boolean;
}>({
  setDirty: (_dirty: boolean) => {
    void _dirty;
  },
  confirmLeave: () => true
});
export function useWorkspaceDraft(dirty: boolean) {
  const { setDirty } = useContext(DraftContext);
  useEffect(() => {
    setDirty(dirty);
    return () => setDirty(false);
  }, [dirty, setDirty]);
}
