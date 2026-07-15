import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { BirthInputAstroVisual } from "./BirthInputAstroVisual";

export function CosmicBackdrop() {
  const { pathname } = useLocation();
  const prefersReducedMotion = usePrefersReducedMotion();
  const showAnimatedScene = useMemo(
    () => !prefersReducedMotion && isImmersiveRoute(pathname),
    [pathname, prefersReducedMotion]
  );

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-night">
      {showAnimatedScene ? <BirthInputAstroVisual theme="cosmic" /> : null}
      <div className="pointer-events-none fixed inset-0 z-[1] bg-[radial-gradient(ellipse_90%_55%_at_50%_-5%,rgba(110,82,170,0.34),transparent_60%),radial-gradient(ellipse_70%_50%_at_82%_96%,rgba(201,169,110,0.18),transparent_60%),radial-gradient(circle_at_15%_78%,rgba(130,90,185,0.16),transparent_55%)]" />
      <div
        className={
          "pointer-events-none fixed inset-[-25%] z-[1] bg-[conic-gradient(from_0deg_at_50%_50%,transparent_0deg,rgba(201,169,110,0.06)_40deg,transparent_95deg,rgba(130,90,185,0.07)_185deg,transparent_265deg,rgba(201,169,110,0.05)_320deg,transparent_360deg)] blur-[34px]" +
          (prefersReducedMotion ? "" : " animate-[spin_55s_linear_infinite]")
        }
      />
    </div>
  );
}

function isImmersiveRoute(pathname: string) {
  return pathname === "/" || pathname === "/new" || pathname === "/bazi";
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false
  );

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
