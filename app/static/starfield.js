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

    // Keep the orbit centre outside the bottom-right corner. Only the enlarged
    // upper-left quarter of each orbit crosses the viewport, avoiding the
    // hypnotic full-circle pattern of the previous design.
    const cx = w * 1.1;
    const cy = h * 1.14;
    const nearR = Math.hypot(cx - w, cy - h) * 0.78;
    const farR = Math.hypot(cx, cy);
    const trailCount = Math.max(280, Math.min(720, Math.round(area / 2600)));
    trailStars = Array.from({ length: trailCount }, () => {
      const radius = nearR + Math.pow(Math.random(), 0.82) * (farR - nearR);
      return {
        radius,
        theta: rand(0, Math.PI * 2),
        r: rand(0.45, 1.45),
        alpha: rand(0.34, 0.88),
        angularSpeed: rand(0.000012, 0.000058),
        pulsePhase: rand(0, Math.PI * 2),
        pulseSpeed: rand(0.00035, 0.0011),
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

    // A translucent dark overlay only hides old pixels; it never clears their
    // alpha, so orbit marks accumulate until a canvas resize resets the buffer.
    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0, 0, 0, 0.062)';
    ctx.fillRect(0, 0, w, h);
    ctx.restore();

    const cx = w * 1.1;
    const cy = h * 1.14;
    for (const s of trailStars) {
      s.theta = (s.theta + dt * s.angularSpeed) % (Math.PI * 2);
      const x = cx + Math.cos(s.theta) * s.radius;
      const y = cy + Math.sin(s.theta) * s.radius;
      if (x < -20 || x > w + 20 || y < -20 || y > h + 20) continue;
      const [r, g, b] = s.color;
      const pulse = 0.72 + Math.sin(ts * s.pulseSpeed + s.pulsePhase) * 0.28;
      ctx.beginPath();
      ctx.fillStyle = `rgba(${r},${g},${b},${s.alpha * pulse})`;
      ctx.arc(x, y, s.r * (0.82 + pulse * 0.22), 0, Math.PI * 2);
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
