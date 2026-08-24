import { useEffect, useRef, type ReactNode } from "react";
import type { BirthTimePrecision } from "../../shared/domain";
import { Clock3, MapPin } from "lucide-react";

type BirthInputTheme = "classic" | "cosmic";
type AstroVisualPlacement = "default" | "right";

const ZODIAC = ["♈︎", "♉︎", "♊︎", "♋︎", "♌︎", "♍︎", "♎︎", "♏︎", "♐︎", "♑︎", "♒︎", "♓︎"];
const TAU = Math.PI * 2;
type ColorTriplet = [number, number, number];

function timeOfDayPalette(hour: number): { inner: ColorTriplet; outer: ColorTriplet } {
  if (hour >= 5 && hour < 8) return { inner: [96, 68, 42], outer: [18, 13, 10] };
  if (hour >= 8 && hour < 17) return { inner: [120, 92, 50], outer: [20, 15, 10] };
  if (hour >= 17 && hour < 20) return { inner: [110, 62, 34], outer: [20, 11, 8] };
  return { inner: [36, 30, 26], outer: [10, 8, 7] };
}

function blendColor(current: ColorTriplet, target: ColorTriplet, amount: number): ColorTriplet {
  return current.map((channel, index) =>
    Math.round(channel + (target[index] - channel) * amount)
  ) as ColorTriplet;
}

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

export function BirthInputAstroVisual({
  theme,
  placement = "default",
  embedded = false,
  birthDate = null,
  birthTime = null,
  timePrecision = "exact",
  location = null,
  timeTitle,
  locationTitle,
  timeLabel,
  locationLabel
}: {
  theme: BirthInputTheme;
  placement?: AstroVisualPlacement;
  embedded?: boolean;
  birthDate?: Date | null;
  birthTime?: Date | null;
  timePrecision?: BirthTimePrecision;
  location?: CityInfo | null;
  timeTitle?: string;
  locationTitle?: string;
  timeLabel?: string;
  locationLabel?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timeMotionRef = useRef({ angle: 0, velocity: 0, hasTarget: false });
  const birthDateRef = useRef(birthDate);
  const birthTimeRef = useRef(birthTime);
  const timePrecisionRef = useRef(timePrecision);

  useEffect(() => {
    birthDateRef.current = birthDate;
    birthTimeRef.current = birthTime;
    timePrecisionRef.current = timePrecision;
  }, [birthDate, birthTime, timePrecision]);

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
    let timeReveal = 0;
    let phaseInner: ColorTriplet = [42, 32, 24];
    let phaseOuter: ColorTriplet = [15, 12, 9];
    let stars: Star[] = [];
    let edges: Array<[Star, Star]> = [];
    const meteors: Meteor[] = [];
    const globePoints: Array<[number, number]> = [];
    const timeMotion = timeMotionRef.current;
    let cityInfo: CityInfo | null = location;
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
      globeTarget: cityInfo ? 1 : 0
    };

    if (cityInfo) {
      motion.cityAngle = (cityInfo.longitude / 180) * Math.PI;
      motion.cityAngleTarget = motion.cityAngle;
      motion.yaw = (-cityInfo.longitude * Math.PI) / 180;
      motion.yawTarget = motion.yaw;
      motion.pitch = Math.max(-0.85, Math.min(0.85, (cityInfo.latitude * Math.PI) / 180));
      motion.pitchTarget = motion.pitch;
    }

    for (let lat = -80; lat <= 80; lat += 10) {
      for (let lon = 0; lon < 360; lon += 10) globePoints.push([lat, lon]);
    }

    function rebuild() {
      canvasElement.style.width = embedded ? "100%" : "100vw";
      canvasElement.style.height = embedded ? "100%" : "100vh";
      const rect = canvasElement.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(320, rect.width) * dpr;
      height = Math.max(460, rect.height) * dpr;
      canvasElement.width = width;
      canvasElement.height = height;

      const count = Math.round((width * height) / 9000);
      stars = Array.from({ length: count }, () => {
        const toneRoll = Math.random();
        const cosmicTone =
          toneRoll < 0.16 ? "237,217,163" : toneRoll < 0.28 ? "188,181,169" : "245,239,230";
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
      const centerX = embedded
        ? width * 0.5
        : wide
          ? width * (placement === "right" ? 0.78 : 0.71)
          : width * 0.5;
      const centerY = height * (embedded ? 0.47 : 0.5);
      const globeRadius = embedded
        ? Math.min(width * 0.31, height * 0.29)
        : Math.min(width * (wide ? 0.22 : 0.32), height * 0.32);
      const ringRadius = globeRadius * (embedded ? 1.58 : 1.6);
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
      const currentBirthDate = birthDateRef.current;
      const currentBirthTime = birthTimeRef.current;
      const currentTimePrecision = timePrecisionRef.current;
      const timeIsKnown = Boolean(currentBirthTime && currentTimePrecision !== "unknown");
      timeReveal += ((timeIsKnown ? 1 : 0) - timeReveal) * Math.min(dt * 4.8, 1);

      let timeSeeking = false;
      if (currentBirthTime && currentTimePrecision !== "unknown") {
        const minutes = currentBirthTime.getHours() * 60 + currentBirthTime.getMinutes();
        const targetAngle = (minutes / 1440) * TAU - Math.PI / 2;
        if (!timeMotion.hasTarget) timeMotion.hasTarget = true;
        let difference = targetAngle - timeMotion.angle;
        difference = ((((difference + Math.PI) % TAU) + TAU) % TAU) - Math.PI;
        timeMotion.velocity += difference * 38 * dt;
        timeMotion.velocity *= Math.pow(0.05, dt);
        timeMotion.angle += timeMotion.velocity * dt;
        timeSeeking = Math.abs(timeMotion.velocity) > 0.04 || Math.abs(difference) > 0.01;

        const palette = timeOfDayPalette(minutes / 60);
        const paletteEase = Math.min(dt * 1.2, 1);
        phaseInner = blendColor(phaseInner, palette.inner, paletteEase);
        phaseOuter = blendColor(phaseOuter, palette.outer, paletteEase);
      } else {
        timeMotion.hasTarget = false;
        timeMotion.velocity *= Math.pow(0.05, dt);
        const paletteEase = Math.min(dt * 1.2, 1);
        phaseInner = blendColor(phaseInner, [42, 32, 24], paletteEase);
        phaseOuter = blendColor(phaseOuter, [15, 12, 9], paletteEase);
      }

      ctx.clearRect(0, 0, width, height);

      if (currentBirthDate) {
        const phaseGlow = ctx.createRadialGradient(
          centerX,
          centerY,
          ringRadius * 0.08,
          centerX,
          centerY,
          ringRadius * 1.32
        );
        phaseGlow.addColorStop(
          0,
          `rgba(${phaseInner[0]},${phaseInner[1]},${phaseInner[2]},${dark ? 0.72 : 0.34})`
        );
        phaseGlow.addColorStop(
          0.72,
          `rgba(${phaseOuter[0]},${phaseOuter[1]},${phaseOuter[2]},${dark ? 0.62 : 0.24})`
        );
        phaseGlow.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = phaseGlow;
        ctx.beginPath();
        ctx.arc(centerX, centerY, ringRadius * 1.32, 0, TAU);
        ctx.fill();
      }

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
      halo.addColorStop(0, dark ? "rgba(201,169,110,0.08)" : "rgba(201,169,110,0.10)");
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
          : `rgba(${dark ? "126,120,111" : "154,122,74"},${alpha})`;
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

      if (currentBirthDate) {
        const outerRadius = ringRadius * 1.08;
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.lineCap = "round";

        const sunriseAngle = (6 / 24) * TAU - Math.PI / 2;
        const sunsetAngle = (18 / 24) * TAU - Math.PI / 2;
        ctx.strokeStyle = dark ? "rgba(237,217,163,0.17)" : "rgba(154,122,74,0.15)";
        ctx.lineWidth = 0.8 * dpr;
        ctx.beginPath();
        ctx.moveTo(Math.cos(sunriseAngle) * outerRadius, Math.sin(sunriseAngle) * outerRadius);
        ctx.lineTo(Math.cos(sunsetAngle) * outerRadius, Math.sin(sunsetAngle) * outerRadius);
        ctx.stroke();

        for (let hour = 0; hour < 24; hour += 1) {
          const angle = (hour / 24) * TAU - Math.PI / 2;
          const major = hour % 6 === 0;
          const inner = outerRadius - (major ? 10 : 5) * dpr;
          ctx.strokeStyle = dark
            ? `rgba(237,217,163,${major ? 0.55 : 0.22})`
            : `rgba(154,122,74,${major ? 0.42 : 0.18})`;
          ctx.lineWidth = (major ? 1.2 : 0.7) * dpr;
          ctx.beginPath();
          ctx.moveTo(Math.cos(angle) * inner, Math.sin(angle) * inner);
          ctx.lineTo(Math.cos(angle) * outerRadius, Math.sin(angle) * outerRadius);
          ctx.stroke();
        }

        if (currentBirthTime && currentTimePrecision !== "unknown") {
          const minutes = currentBirthTime.getHours() * 60 + currentBirthTime.getMinutes();
          const angle = timeMotion.angle;
          const hour = minutes / 60;
          const isDay = hour >= 6 && hour < 18;
          const tone = isDay ? "245,220,158" : "190,190,205";
          const pulse =
            (timeSeeking ? 0.85 + Math.sin(time * 10) * 0.15 : 0.75 + Math.sin(time * 2.4) * 0.2) *
            timeReveal;
          const tipX = Math.cos(angle) * outerRadius * 0.98;
          const tipY = Math.sin(angle) * outerRadius * 0.98;
          const perpendicularX = -Math.sin(angle);
          const perpendicularY = Math.cos(angle);

          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          const beamGlow = ctx.createLinearGradient(0, 0, tipX, tipY);
          beamGlow.addColorStop(0, `rgba(${tone},0)`);
          beamGlow.addColorStop(0.58, `rgba(${tone},${0.08 * pulse})`);
          beamGlow.addColorStop(1, `rgba(${tone},${0.34 * pulse})`);
          ctx.fillStyle = beamGlow;
          ctx.beginPath();
          ctx.moveTo(perpendicularX * dpr, perpendicularY * dpr);
          ctx.lineTo(tipX + perpendicularX * 8 * dpr, tipY + perpendicularY * 8 * dpr);
          ctx.lineTo(tipX - perpendicularX * 8 * dpr, tipY - perpendicularY * 8 * dpr);
          ctx.lineTo(-perpendicularX * dpr, -perpendicularY * dpr);
          ctx.closePath();
          ctx.fill();
          ctx.restore();

          const beam = ctx.createLinearGradient(0, 0, tipX, tipY);
          beam.addColorStop(0, `rgba(${tone},${0.04 * timeReveal})`);
          beam.addColorStop(0.55, `rgba(${tone},${0.5 * pulse})`);
          beam.addColorStop(1, `rgba(${tone},${pulse})`);
          const hubWidth = 0.5 * dpr;
          const tipWidth = (isDay ? 3.3 : 1.9) * dpr;
          ctx.fillStyle = beam;
          ctx.beginPath();
          ctx.moveTo(perpendicularX * hubWidth, perpendicularY * hubWidth);
          ctx.lineTo(tipX + perpendicularX * tipWidth, tipY + perpendicularY * tipWidth);
          ctx.lineTo(tipX - perpendicularX * tipWidth, tipY - perpendicularY * tipWidth);
          ctx.lineTo(-perpendicularX * hubWidth, -perpendicularY * hubWidth);
          ctx.closePath();
          ctx.fill();

          for (let mote = 0; mote < 3; mote += 1) {
            const progress = (time * 0.32 + mote / 3) % 1;
            const alpha = Math.sin(progress * Math.PI) * 0.55 * pulse;
            ctx.fillStyle = `rgba(${tone},${alpha})`;
            ctx.beginPath();
            ctx.arc(tipX * progress, tipY * progress, (1.2 - progress * 0.5) * dpr, 0, TAU);
            ctx.fill();
          }

          ctx.strokeStyle = `rgba(237,217,163,${0.28 * timeReveal})`;
          ctx.lineWidth = dpr;
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(-tipX * 0.24, -tipY * 0.24);
          ctx.stroke();

          ctx.fillStyle = `rgba(237,217,163,${0.96 * timeReveal})`;
          ctx.beginPath();
          ctx.arc(0, 0, 3.2 * dpr, 0, TAU);
          ctx.fill();

          const haloRadius = (10 + Math.sin(time * 3) * 2) * dpr * timeReveal;
          ctx.fillStyle = `rgba(${tone},${0.2 * pulse})`;
          ctx.beginPath();
          ctx.arc(tipX, tipY, haloRadius, 0, TAU);
          ctx.fill();

          ctx.save();
          ctx.translate(tipX, tipY);
          const iconRadius = 4.2 * dpr * timeReveal;
          if (isDay) {
            ctx.fillStyle = `rgba(${tone},${0.98 * timeReveal})`;
            ctx.beginPath();
            ctx.arc(0, 0, iconRadius, 0, TAU);
            ctx.fill();
            ctx.strokeStyle = `rgba(${tone},${0.8 * timeReveal})`;
            ctx.lineWidth = dpr;
            for (let ray = 0; ray < 8; ray += 1) {
              const rayAngle = (ray / 8) * TAU + time * 0.45;
              ctx.beginPath();
              ctx.moveTo(
                Math.cos(rayAngle) * iconRadius * 1.5,
                Math.sin(rayAngle) * iconRadius * 1.5
              );
              ctx.lineTo(
                Math.cos(rayAngle) * iconRadius * 2.2,
                Math.sin(rayAngle) * iconRadius * 2.2
              );
              ctx.stroke();
            }
          } else {
            ctx.fillStyle = `rgba(${tone},${0.98 * timeReveal})`;
            ctx.beginPath();
            ctx.arc(0, 0, iconRadius * 1.12, 0, TAU);
            ctx.fill();
            ctx.globalCompositeOperation = "destination-out";
            ctx.beginPath();
            ctx.arc(iconRadius * 0.62, -iconRadius * 0.15, iconRadius, 0, TAU);
            ctx.fill();
          }
          ctx.restore();
        }
        ctx.restore();
      }

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
      ctx.font = `${18 * dpr}px "Times New Roman", "Noto Serif Symbols", serif`;
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
    window.addEventListener("resize", rebuild);
    window.addEventListener("birth-place-coordinates", onCity);
    rebuild();
    animation = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animation);
      observer.disconnect();
      window.removeEventListener("resize", rebuild);
      window.removeEventListener("birth-place-coordinates", onCity);
    };
  }, [embedded, location, placement, theme]);

  const canvas = (
    <canvas
      ref={canvasRef}
      className={
        embedded
          ? "pointer-events-none absolute inset-0 size-full"
          : "pointer-events-none fixed inset-0 z-0 h-screen w-screen"
      }
      aria-hidden
    />
  );

  if (!embedded) return canvas;

  return (
    <div className="relative h-full min-h-[620px] w-full" aria-live="polite">
      {canvas}
      <div className="pointer-events-none absolute inset-x-8 top-7 flex items-center justify-between text-[11px] font-medium text-cream/36">
        <span>01 · {timeTitle || "Time"}</span>
        <span>02 · {locationTitle || "Place"}</span>
      </div>
      <div className="pointer-events-none absolute inset-x-8 bottom-8 flex items-end justify-between gap-6">
        <VisualReadout
          icon={<Clock3 size={14} />}
          active={Boolean(timeLabel)}
          label={timeTitle}
          value={timeLabel}
        />
        <VisualReadout
          icon={<MapPin size={14} />}
          active={Boolean(location)}
          label={locationTitle}
          value={locationLabel}
          align="right"
        />
      </div>
    </div>
  );
}

function VisualReadout({
  icon,
  active,
  label,
  value,
  align = "left"
}: {
  icon: ReactNode;
  active: boolean;
  label?: string;
  value?: string;
  align?: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "min-w-0 text-right" : "min-w-0 text-left"}>
      <div
        className={
          "mb-1 flex items-center gap-1.5 text-[11px] font-medium " +
          (active ? "text-gold-light" : "text-cream/30") +
          (align === "right" ? " justify-end" : "")
        }
      >
        {icon}
        <span>{label}</span>
      </div>
      <div
        className={
          active ? "max-w-[190px] truncate text-xs text-cream/72" : "text-xs text-cream/28"
        }
      >
        {active && value ? value : "—"}
      </div>
    </div>
  );
}
