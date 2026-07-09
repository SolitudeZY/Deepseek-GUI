'use strict';

const Starfield = (() => {
  const canvas = document.getElementById('starfield-canvas');
  const ctx = canvas ? canvas.getContext('2d', { alpha: true }) : null;
  let raf = 0;
  let running = false;
  let mode = 'twinkle';
  let dpr = 1;
  let w = 0;
  let h = 0;
  let stars = [];
  let trailStars = [];
  let startedAt = 0;
  let lastTs = 0;
  let angle = 0;

  function resize() {
    if (!canvas || !ctx) return;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = Math.max(1, window.innerWidth);
    h = Math.max(1, window.innerHeight);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    buildStars();
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function buildStars() {
    const area = w * h;
    const count = Math.max(90, Math.min(260, Math.round(area / 7200)));
    const colors = [
      [122, 162, 247], // blue
      [125, 207, 255], // cyan
      [167, 139, 250], // violet
      [247, 118, 142], // rose
      [238, 212, 159], // warm gold
      [154, 230, 180], // mint
      [229, 233, 255], // pearl
    ];
    stars = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: rand(0.65, 2.05),
      phase: rand(0, Math.PI * 2),
      speed: rand(0.00045, 0.00125),
      drift: rand(0.04, 0.18),
      color: colors[Math.floor(Math.random() * colors.length)],
      glow: Math.random() > 0.45,
    }));

    const cx = w * 0.58;
    const cy = h * 0.42;
    const maxR = Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
    const trailCount = Math.max(140, Math.min(380, Math.round(area / 5200)));
    trailStars = Array.from({ length: trailCount }, () => {
      const radius = Math.pow(Math.random(), 0.72) * maxR;
      return {
        radius,
        theta: rand(0, Math.PI * 2),
        r: rand(0.45, 1.45),
        alpha: rand(0.34, 0.88),
        color: colors[Math.floor(Math.random() * colors.length)],
      };
    });
  }

  function clear() {
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
  }

  function drawGlow() {
    const grad = ctx.createRadialGradient(w * 0.58, h * 0.42, 0, w * 0.58, h * 0.42, Math.max(w, h) * 0.7);
    grad.addColorStop(0, 'rgba(122,162,247,0.10)');
    grad.addColorStop(0.38, 'rgba(86,95,137,0.035)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
  }

  function drawTwinkle(ts) {
    clear();
    drawGlow();
    for (const s of stars) {
      const pulse = (Math.sin(ts * s.speed + s.phase) + 1) / 2;
      const alpha = 0.2 + pulse * 0.8;
      const driftX = Math.sin(ts * 0.00008 + s.phase) * s.drift;
      const [r, g, b] = s.color;
      if (s.glow) {
        const glow = ctx.createRadialGradient(s.x + driftX, s.y, 0, s.x + driftX, s.y, s.r * 6);
        glow.addColorStop(0, `rgba(${r},${g},${b},${alpha * 0.28})`);
        glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = glow;
        ctx.fillRect(s.x + driftX - s.r * 6, s.y - s.r * 6, s.r * 12, s.r * 12);
      }
      ctx.beginPath();
      ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.arc(s.x + driftX, s.y, s.r * (0.75 + pulse * 0.55), 0, Math.PI * 2);
      ctx.fill();
      if (pulse > 0.86) {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(${r},${g},${b},${(pulse - 0.86) * 0.75})`;
        ctx.lineWidth = 0.6;
        ctx.moveTo(s.x - s.r * 3, s.y);
        ctx.lineTo(s.x + s.r * 3, s.y);
        ctx.moveTo(s.x, s.y - s.r * 3);
        ctx.lineTo(s.x, s.y + s.r * 3);
        ctx.stroke();
      }
    }
  }

  function drawTrails(ts) {
    if (!lastTs) lastTs = ts;
    const dt = Math.min(40, ts - lastTs);
    lastTs = ts;
    ctx.fillStyle = 'rgba(7, 8, 17, 0.062)';
    ctx.fillRect(0, 0, w, h);
    drawGlow();

    const cx = w * 0.58;
    const cy = h * 0.42;
    angle += dt * 0.000045;
    for (const s of trailStars) {
      const t = s.theta + angle * (1 + s.radius / Math.max(w, h));
      const x = cx + Math.cos(t) * s.radius;
      const y = cy + Math.sin(t) * s.radius;
      if (x < -20 || x > w + 20 || y < -20 || y > h + 20) continue;
      const [r, g, b] = s.color;
      ctx.beginPath();
      ctx.fillStyle = `rgba(${r},${g},${b},${s.alpha})`;
      ctx.arc(x, y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function frame(ts) {
    if (!running) return;
    if (!startedAt) startedAt = ts;
    if (mode === 'trails') drawTrails(ts);
    else drawTwinkle(ts);
    raf = requestAnimationFrame(frame);
  }

  function shouldRun(config) {
    const theme = document.documentElement.dataset.theme || 'dark';
    return !!(config && config.starfield_enabled && theme === 'dark' && canvas && ctx);
  }

  function stop() {
    running = false;
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    startedAt = 0;
    lastTs = 0;
    clear();
    if (canvas) canvas.classList.remove('is-active');
    document.documentElement.dataset.starfield = 'off';
  }

  function apply(config) {
    if (!canvas || !ctx) return;
    mode = config && config.starfield_mode === 'trails' ? 'trails' : 'twinkle';
    if (!shouldRun(config)) {
      stop();
      return;
    }
    document.documentElement.dataset.starfield = 'on';
    canvas.classList.add('is-active');
    resize();
    clear();
    running = true;
    if (!raf) raf = requestAnimationFrame(frame);
  }

  window.addEventListener('resize', () => {
    if (!running) return;
    resize();
    if (mode === 'trails') clear();
  });

  return { apply, stop };
})();

function applyStarfieldSettings(config) {
  Starfield.apply(config || {});
}
