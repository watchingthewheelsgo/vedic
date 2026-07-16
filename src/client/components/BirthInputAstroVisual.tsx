import { useEffect, useRef } from "react";

type BirthInputTheme = "classic" | "cosmic";

const ZODIAC = "♈♉♊♋♌♍♎♏♐♑♒♓".split("");
const TAU = Math.PI * 2;

type Star = {
  x: number;
  y: number;
  z: number;
  radius: number;
  alpha: number;
  phase: number;
  speed: number;
  tone: string;
};

type Meteor = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
};

type CityInfo = {
  latitude: number;
  longitude: number;
  label?: string | null;
  exact?: boolean;
};

export function BirthInputAstroVisual({ theme }: { theme: BirthInputTheme }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const canvasElement = canvas;
    const ctx = context;

    let animation = 0;
    let width = 0;
    let height = 0;
    let dpr = 1;
    let last = performance.now();
    let time = 0;
    let stars: Star[] = [];
    let edges: Array<[Star, Star]> = [];
    const meteors: Meteor[] = [];
    const globePoints: Array<[number, number]> = [];
    let cityInfo: CityInfo | null = null;
    const motion = {
      spin: 0,
      cityAngle: 0,
      cityAngleTarget: 0,
      panX: 0,
      panY: 0,
      panXTarget: 0,
      panYTarget: 0,
      warp: 0,
      marker: 0,
      yaw: 0,
      yawTarget: 0,
      pitch: -0.32,
      pitchTarget: -0.32,
      globe: 0,
      globeTarget: 0
    };

    for (let lat = -80; lat <= 80; lat += 10) {
      for (let lon = 0; lon < 360; lon += 10) globePoints.push([lat, lon]);
    }

    function rebuild() {
      const rect = canvasElement.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(320, rect.width) * dpr;
      height = Math.max(460, rect.height) * dpr;
      canvasElement.width = width;
      canvasElement.height = height;
      canvasElement.style.width = `${rect.width}px`;
      canvasElement.style.height = `${rect.height}px`;

      const count = Math.round((width * height) / 9000);
      stars = Array.from({ length: count }, () => {
        const toneRoll = Math.random();
        const cosmicTone =
          toneRoll < 0.16 ? "237,217,163" : toneRoll < 0.26 ? "176,146,224" : "245,239,230";
        const classicTone =
          toneRoll < 0.22 ? "201,169,110" : toneRoll < 0.36 ? "154,122,74" : "112,94,70";
        return {
          x: Math.random() * width,
          y: Math.random() * height,
          z: 0.3 + Math.random() * 0.7,
          radius: (0.4 + Math.random() * 1.7) * dpr,
          alpha: 0.4 + Math.random() * 0.6,
          phase: Math.random() * TAU,
          speed: 0.5 + Math.random() * 1.5,
          tone: theme === "cosmic" ? cosmicTone : classicTone
        };
      });

      const bright = stars.filter((star) => star.radius > 1.25 * dpr).slice(0, 42);
      edges = [];
      for (let index = 0; index < bright.length; index += 1) {
        let best = -1;
        let bestDistance = Infinity;
        for (let target = 0; target < bright.length; target += 1) {
          if (index === target) continue;
          const dx = bright[index].x - bright[target].x;
          const dy = bright[index].y - bright[target].y;
          const distance = dx * dx + dy * dy;
          if (distance < bestDistance) {
            bestDistance = distance;
            best = target;
          }
        }
        if (best >= 0 && bestDistance < (240 * dpr) ** 2) edges.push([bright[index], bright[best]]);
      }
    }

    function onCity(event: Event) {
      const detail = (event as CustomEvent<CityInfo | null>).detail;
      if (!detail || !Number.isFinite(detail.latitude) || !Number.isFinite(detail.longitude)) {
        cityInfo = null;
        motion.globeTarget = 0;
        return;
      }

      cityInfo = detail;
      motion.cityAngleTarget = (detail.longitude / 180) * Math.PI;
      motion.yawTarget = (-detail.longitude * Math.PI) / 180;
      motion.pitchTarget = Math.max(-0.85, Math.min(0.85, (detail.latitude * Math.PI) / 180));
      motion.globeTarget = 1;
      motion.warp = 1;
      motion.marker = 1;
      for (let index = 0; index < 3; index += 1) {
        meteors.push({
          x: Math.random() * width,
          y: Math.random() * height * 0.5,
          vx: (250 + Math.random() * 260) * dpr,
          vy: (100 + Math.random() * 110) * dpr,
          life: 1,
          maxLife: 1
        });
      }
    }

    function draw(now: number) {
      animation = requestAnimationFrame(draw);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      time += dt;

      const dark = theme === "cosmic";
      const wide = width / dpr > 980;
      const centerX = wide ? width * 0.71 : width * 0.5;
      const centerY = height * 0.5;
      const globeRadius = Math.min(width * (wide ? 0.22 : 0.32), height * 0.32);
      const ringRadius = globeRadius * 1.6;
      const ease = Math.min(dt * 2, 1);

      motion.spin += dt * 0.02;
      motion.yawTarget += dt * 0.05;
      motion.cityAngle += (motion.cityAngleTarget - motion.cityAngle) * ease;
      motion.yaw += (motion.yawTarget - motion.yaw) * Math.min(dt * 1.4, 1);
      motion.pitch += (motion.pitchTarget - motion.pitch) * Math.min(dt * 1.4, 1);
      motion.globe += (motion.globeTarget - motion.globe) * Math.min(dt * 2, 1);
      motion.panX += (motion.panXTarget - motion.panX) * ease;
      motion.panY += (motion.panYTarget - motion.panY) * ease;
      motion.warp += (0 - motion.warp) * Math.min(dt * 1.6, 1);
      motion.marker += (0 - motion.marker) * Math.min(dt * 1.1, 1);

      ctx.clearRect(0, 0, width, height);

      ctx.lineWidth = dpr * 0.5;
      for (const [a, b] of edges) {
        const ax = a.x + motion.panX * a.z;
        const ay = a.y + motion.panY * a.z;
        const bx = b.x + motion.panX * b.z;
        const by = b.y + motion.panY * b.z;
        ctx.strokeStyle = dark
          ? `rgba(201,169,110,${0.06 + 0.05 * Math.sin(time + a.phase)})`
          : `rgba(154,122,74,${0.04 + 0.04 * Math.sin(time + a.phase)})`;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }

      for (const star of stars) {
        const px = star.x + motion.panX * star.z;
        const py = star.y + motion.panY * star.z;
        const twinkle = 0.5 + 0.5 * Math.sin(time * star.speed + star.phase);
        const alpha = star.alpha * (0.4 + 0.6 * twinkle) * (dark ? 1 : 0.48);
        if (motion.warp > 0.02) {
          const dx = px - centerX;
          const dy = py - centerY;
          const length = motion.warp * 0.3;
          ctx.strokeStyle = `rgba(237,217,163,${alpha * 0.85})`;
          ctx.lineWidth = star.radius;
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(px + dx * length, py + dy * length);
          ctx.stroke();
        } else {
          ctx.fillStyle = `rgba(${star.tone},${alpha})`;
          ctx.beginPath();
          ctx.arc(px, py, star.radius, 0, TAU);
          ctx.fill();
          if (star.radius > 1.3 * dpr) {
            ctx.fillStyle = `rgba(${star.tone},${alpha * 0.18})`;
            ctx.beginPath();
            ctx.arc(px, py, star.radius * 2.6, 0, TAU);
            ctx.fill();
          }
        }
      }

      const cosPitch = Math.cos(motion.pitch);
      const sinPitch = Math.sin(motion.pitch);
      ctx.save();
      ctx.translate(centerX, centerY);
      const halo = ctx.createRadialGradient(0, 0, globeRadius * 0.15, 0, 0, globeRadius * 1.2);
      halo.addColorStop(0, dark ? "rgba(120,90,180,0.12)" : "rgba(201,169,110,0.10)");
      halo.addColorStop(0.65, dark ? "rgba(201,169,110,0.05)" : "rgba(154,122,74,0.04)");
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(0, 0, globeRadius * 1.2, 0, TAU);
      ctx.fill();

      for (const [lat, lon] of globePoints) {
        const phi = (lat * Math.PI) / 180;
        const theta = (lon * Math.PI) / 180 + motion.yaw;
        const x = Math.cos(phi) * Math.sin(theta);
        const y = Math.sin(phi);
        const z = Math.cos(phi) * Math.cos(theta);
        const rotatedY = y * cosPitch - z * sinPitch;
        const rotatedZ = y * sinPitch + z * cosPitch;
        const front = rotatedZ > 0;
        const alpha = front
          ? 0.55 * (0.35 + 0.65 * rotatedZ) * (dark ? 1 : 0.78)
          : 0.1 * (0.5 + 0.5 * (rotatedZ + 1));
        ctx.fillStyle = front
          ? `rgba(201,169,110,${alpha})`
          : `rgba(${dark ? "128,108,150" : "154,122,74"},${alpha})`;
        ctx.beginPath();
        ctx.arc(x * globeRadius, -rotatedY * globeRadius, (front ? 1.5 : 1.0) * dpr, 0, TAU);
        ctx.fill();
      }

      ctx.strokeStyle = dark ? "rgba(201,169,110,0.32)" : "rgba(154,122,74,0.24)";
      ctx.lineWidth = dpr * 1.1;
      ctx.beginPath();
      ctx.arc(0, 0, globeRadius, 0, TAU);
      ctx.stroke();
      ctx.restore();

      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(motion.spin + motion.cityAngle);
      ctx.strokeStyle = dark ? "rgba(201,169,110,0.18)" : "rgba(154,122,74,0.16)";
      ctx.lineWidth = dpr;
      ctx.beginPath();
      ctx.arc(0, 0, ringRadius, 0, TAU);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, 0, ringRadius * 0.93, 0, TAU);
      ctx.stroke();
      ctx.font = `${18 * dpr}px Georgia, serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (let index = 0; index < 12; index += 1) {
        const angle = (index / 12) * TAU;
        const x = Math.cos(angle);
        const y = Math.sin(angle);
        ctx.strokeStyle = dark ? "rgba(201,169,110,0.22)" : "rgba(154,122,74,0.16)";
        ctx.beginPath();
        ctx.moveTo(x * ringRadius, y * ringRadius);
        ctx.lineTo(x * ringRadius * 0.93, y * ringRadius * 0.93);
        ctx.stroke();
        ctx.fillStyle = dark ? "rgba(222,192,132,0.55)" : "rgba(154,122,74,0.36)";
        ctx.save();
        ctx.translate(x * ringRadius * 0.85, y * ringRadius * 0.85);
        ctx.rotate(-(motion.spin + motion.cityAngle));
        ctx.fillText(ZODIAC[index], 0, 0);
        ctx.restore();
      }
      ctx.restore();

      if (cityInfo) {
        const phi = (cityInfo.latitude * Math.PI) / 180;
        const theta = (cityInfo.longitude * Math.PI) / 180 + motion.yaw;
        const x = Math.cos(phi) * Math.sin(theta);
        const y = Math.sin(phi);
        const z = Math.cos(phi) * Math.cos(theta);
        const rotatedY = y * cosPitch - z * sinPitch;
        const rotatedZ = y * sinPitch + z * cosPitch;
        if (rotatedZ > -0.05) {
          const visible = Math.max(0, Math.min(1, (rotatedZ + 0.05) / 0.3)) * motion.globe;
          const pulse = 0.5 + 0.5 * Math.sin(time * 3);
          const markerX = centerX + x * globeRadius;
          const markerY = centerY - rotatedY * globeRadius;
          ctx.strokeStyle = `rgba(237,217,163,${0.5 * visible})`;
          ctx.lineWidth = dpr * 1.4;
          ctx.beginPath();
          ctx.moveTo(markerX, markerY);
          ctx.lineTo(markerX, markerY - (22 + 8 * pulse) * dpr);
          ctx.stroke();
          ctx.strokeStyle = `rgba(237,217,163,${0.6 * visible * (1 - pulse)})`;
          ctx.beginPath();
          ctx.arc(markerX, markerY, (4 + 11 * pulse) * dpr, 0, TAU);
          ctx.stroke();
          ctx.fillStyle = `rgba(237,217,163,${0.22 * visible})`;
          ctx.beginPath();
          ctx.arc(markerX, markerY, 9 * dpr, 0, TAU);
          ctx.fill();
          ctx.fillStyle = `rgba(255,242,205,${visible})`;
          ctx.beginPath();
          ctx.arc(markerX, markerY, 3.2 * dpr, 0, TAU);
          ctx.fill();
          if (cityInfo.exact && cityInfo.label) {
            ctx.fillStyle = `rgba(245,239,230,${0.85 * visible})`;
            ctx.font = `${12.5 * dpr}px -apple-system, BlinkMacSystemFont, sans-serif`;
            ctx.textAlign = "center";
            ctx.fillText(cityInfo.label, markerX, markerY - (34 + 8 * pulse) * dpr);
          }
        }
      }

      if (motion.marker > 0.01) {
        ctx.strokeStyle = `rgba(237,217,163,${motion.marker * 0.5})`;
        ctx.lineWidth = dpr * 1.6;
        ctx.beginPath();
        ctx.arc(centerX, centerY, (1 - motion.marker) * ringRadius, 0, TAU);
        ctx.stroke();
      }

      for (let index = meteors.length - 1; index >= 0; index -= 1) {
        const meteor = meteors[index];
        meteor.x += meteor.vx * dt;
        meteor.y += meteor.vy * dt;
        meteor.life -= dt;
        if (meteor.life <= 0 || meteor.x > width + 50 || meteor.y > height + 50) {
          meteors.splice(index, 1);
          continue;
        }
        const alpha = Math.max(0, meteor.life / meteor.maxLife);
        ctx.strokeStyle = `rgba(245,239,230,${alpha * 0.8})`;
        ctx.lineWidth = dpr * 1.2;
        ctx.beginPath();
        ctx.moveTo(meteor.x, meteor.y);
        ctx.lineTo(meteor.x - meteor.vx * 0.12, meteor.y - meteor.vy * 0.12);
        ctx.stroke();
      }

      if (Math.random() < 0.004) {
        meteors.push({
          x: Math.random() * width,
          y: Math.random() * height * 0.5,
          vx: (200 + Math.random() * 200) * dpr,
          vy: (80 + Math.random() * 90) * dpr,
          life: 1.2,
          maxLife: 1.2
        });
      }
    }

    const observer = new ResizeObserver(rebuild);
    observer.observe(canvasElement);
    window.addEventListener("birth-place-coordinates", onCity);
    rebuild();
    animation = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animation);
      observer.disconnect();
      window.removeEventListener("birth-place-coordinates", onCity);
    };
  }, [theme]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0 h-screen w-screen"
      aria-hidden
    />
  );
}
