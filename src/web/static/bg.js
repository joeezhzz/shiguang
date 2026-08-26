/* 拾光 · 背景氛围动画：白天落花 / 夜里流星 + 星空（极淡，纯装饰，不挡内容） */
(function () {
  const canvas = document.createElement("canvas");
  canvas.id = "bg-canvas";
  document.body.insertBefore(canvas, document.body.firstChild);
  const ctx = canvas.getContext("2d");
  const DPR = window.devicePixelRatio || 1;

  let W = 0, H = 0, particles = [], stars = [];
  let mode = "flower"; // flower | meteor
  let frame = 0;

  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * DPR; canvas.height = H * DPR;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    initStars();
  }
  window.addEventListener("resize", resize);

  /* ---------- 星空（深色主题，营造深邃感） ---------- */
  const STAR_COLORS = ["#dbe4ff", "#c4d4ff", "#ffffff", "#e8dcf0", "#ffe0b8"];
  function initStars() {
    stars = [];
    const n = Math.round((W * H) / 11000); // 自适应密度（比之前更密）
    for (let i = 0; i < n; i++) {
      stars.push({
        x: Math.random() * W, y: Math.random() * H,
        r: 0.5 + Math.random() * 1.1,
        base: 0.12 + Math.random() * 0.4,
        phase: Math.random() * Math.PI * 2,
        speed: 0.02 + Math.random() * 0.05,
        color: STAR_COLORS[(Math.random() * STAR_COLORS.length) | 0],
      });
    }
  }

  function drawStars() {
    for (const s of stars) {
      const tw = 0.6 + 0.4 * Math.sin(frame * s.speed + s.phase);
      ctx.globalAlpha = s.base * tw;
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  /* ---------- 落花（浅色主题） ---------- */
  const FLOWER_COLORS = ["#e6b4c0", "#eccda4", "#f0dcc8", "#e9c0c9"];

  function spawnFlower() {
    return {
      baseX: Math.random() * W, y: -24,
      size: 5 + Math.random() * 6,
      vy: 0.35 + Math.random() * 0.55,
      sway: Math.random() * Math.PI * 2,
      swaySpeed: 0.008 + Math.random() * 0.02,
      swayAmp: 14 + Math.random() * 26,
      rot: Math.random() * Math.PI,
      rotSpeed: (Math.random() - 0.5) * 0.018,
      color: FLOWER_COLORS[(Math.random() * FLOWER_COLORS.length) | 0],
      alpha: 0.15 + Math.random() * 0.18,
    };
  }

  function drawFlower(p) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.rot);
    ctx.globalAlpha = p.alpha;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.ellipse(0, 0, p.size, p.size * 0.55, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  /* ---------- 流星（深色主题，贯穿视野不中途消失） ---------- */
  function spawnMeteor() {
    return {
      // 从屏幕外右上方进入，向左下贯穿整屏
      x: W * (0.5 + Math.random() * 0.7),   // 右半 ~ 屏幕外右侧
      y: -40 - Math.random() * H * 0.2,      // 屏幕外上方
      vx: -(4 + Math.random() * 2.5),        // 向左
      vy: 2.4 + Math.random() * 1.8,         // 向下
      alpha: 0.35 + Math.random() * 0.2,
      len: 90 + Math.random() * 70,
    };
  }

  function drawMeteor(p) {
    const h = Math.hypot(p.vx, p.vy);
    const tx = p.x - (p.vx / h) * p.len;
    const ty = p.y - (p.vy / h) * p.len;
    const grad = ctx.createLinearGradient(p.x, p.y, tx, ty);
    grad.addColorStop(0, `rgba(232,240,255,${p.alpha})`);
    grad.addColorStop(0.25, `rgba(210,225,255,${p.alpha * 0.5})`);
    grad.addColorStop(1, "rgba(210,225,255,0)");
    ctx.save();
    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.3;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(tx, ty);
    ctx.stroke();
    // 头部亮点（冷白光，宇宙感）
    ctx.globalAlpha = Math.min(1, p.alpha + 0.3);
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 1.7, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  /* ---------- 主循环 ---------- */
  function step() {
    frame += 1;
    ctx.clearRect(0, 0, W, H);

    if (mode === "flower") {
      if (particles.length < 34 && Math.random() < 0.2) particles.push(spawnFlower());
      particles = particles.filter((p) => p.y < H + 30);
      for (const p of particles) {
        p.sway += p.swaySpeed;
        p.x = p.baseX + Math.sin(p.sway) * p.swayAmp;
        p.y += p.vy;
        p.rot += p.rotSpeed;
        drawFlower(p);
      }
    } else {
      drawStars();
      if (particles.length < 4 && Math.random() < 0.02) particles.push(spawnMeteor());
      // 只有完全飞出屏幕（左侧/下方）才移除，保证贯穿整屏
      particles = particles.filter((p) => p.x > -p.len - 60 && p.y < H + 120);
      for (const p of particles) {
        p.x += p.vx; p.y += p.vy;
        drawMeteor(p);
      }
    }
    requestAnimationFrame(step);
  }

  resize();
  requestAnimationFrame(step);

  // 供主题切换调用：flower（浅色）/ meteor（深色）
  window.__setBgMode = function (m) {
    if (mode === m) return;
    mode = m;
    particles = [];
  };
})();
