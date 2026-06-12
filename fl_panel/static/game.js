const canvas = document.getElementById("space");
const ctx = canvas.getContext("2d");
const state = {
  data: null,
  objects: [],
  keys: new Set(),
  ship: { x: 0, z: 0, angle: -Math.PI / 2, speed: 0 },
  target: 0,
  stars: [],
  toastTimer: 0,
};
const colors = {
  base: "#7af4ff",
  planet: "#ffd166",
  sun: "#fff3a0",
  trade_lane: "#58f0a7",
  jump: "#d48cff",
  object: "#9fb6c9",
};

function resize() {
  canvas.width = innerWidth * devicePixelRatio;
  canvas.height = innerHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  makeStars();
}

function hash(value) {
  let result = 2166136261;
  for (const char of value) {
    result ^= char.charCodeAt(0);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}

function rand(seed) {
  let x = seed || 1;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return ((x >>> 0) % 10000) / 10000;
  };
}

function makeStars() {
  const random = rand(42);
  state.stars = Array.from({ length: 420 }, () => ({
    x: random() * innerWidth,
    y: random() * innerHeight,
    d: 0.25 + random() * 1.8,
    p: 0.25 + random() * 1.4,
  }));
}

async function load(system = "Li01") {
  const response = await fetch(`/api/game-data?system=${encodeURIComponent(system)}`);
  state.data = await response.json();
  state.objects = state.data.objects.map((object) => ({
    ...object,
    r: 8 + (hash(object.nickname) % 18),
  }));
  document.getElementById("system-name").textContent = `${state.data.system.name} · ${state.objects.length} объектов из INI`;
  fillSelects();
  state.ship.x = 0;
  state.ship.z = 0;
  state.ship.speed = 0;
  state.target = 0;
  updateTarget();
}

function fillSelects() {
  const systems = document.getElementById("system-select");
  systems.innerHTML = state.data.systems
    .map((system) => `<option value="${system.code}" ${system.code === state.data.system.code ? "selected" : ""}>${system.name}</option>`)
    .join("");

  const ships = document.getElementById("ship-select");
  ships.innerHTML = state.data.ships.map((ship) => `<option>${ship.name}</option>`).join("");
  document.getElementById("sources").textContent = `Данные: ${state.data.source_files.filter(Boolean).join(", ")}`;
}

function project(x, z) {
  const sx = (x - state.ship.x) / 150;
  const sz = (z - state.ship.z) / 150;
  const ca = Math.cos(-state.ship.angle);
  const sa = Math.sin(-state.ship.angle);
  return {
    x: innerWidth / 2 + sx * ca - sz * sa,
    y: innerHeight / 2 + sx * sa + sz * ca,
  };
}

function drawGrid() {
  ctx.strokeStyle = "rgba(73,223,255,.08)";
  ctx.lineWidth = 1;
  for (let i = -12; i <= 12; i += 1) {
    const a = project(i * 6000, -72000);
    const b = project(i * 6000, 72000);
    const c = project(-72000, i * 6000);
    const d = project(72000, i * 6000);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.moveTo(c.x, c.y);
    ctx.lineTo(d.x, d.y);
    ctx.stroke();
  }
}

function drawObjects() {
  if (!state.data) {
    return;
  }
  for (const object of state.objects) {
    const point = project(object.x, object.z);
    if (point.x < -80 || point.x > innerWidth + 80 || point.y < -80 || point.y > innerHeight + 80) {
      continue;
    }
    const color = colors[object.kind] || colors.object;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = object.kind === "trade_lane" ? 1 : 2;
    ctx.beginPath();
    ctx.arc(point.x, point.y, object.r, 0, Math.PI * 2);
    ctx.stroke();

    if (object.kind === "sun" || object.kind === "planet") {
      ctx.globalAlpha = 0.25;
      ctx.beginPath();
      ctx.arc(point.x, point.y, object.r * 2.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    if (object === state.objects[state.target]) {
      ctx.strokeStyle = "#fff";
      ctx.beginPath();
      ctx.arc(point.x, point.y, object.r + 8, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (object.kind !== "trade_lane") {
      ctx.fillText(object.name, point.x + object.r + 6, point.y - 4);
    }
  }
}

function drawShip() {
  const x = innerWidth / 2;
  const y = innerHeight / 2;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(state.ship.angle + Math.PI / 2);
  ctx.strokeStyle = "#fff";
  ctx.fillStyle = "rgba(73,223,255,.18)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, -18);
  ctx.lineTo(13, 16);
  ctx.lineTo(0, 9);
  ctx.lineTo(-13, 16);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  if (state.keys.has("Shift")) {
    ctx.strokeStyle = "#ffd166";
    ctx.beginPath();
    ctx.moveTo(-7, 17);
    ctx.lineTo(0, 38);
    ctx.lineTo(7, 17);
    ctx.stroke();
  }
  ctx.restore();
}

function draw() {
  ctx.clearRect(0, 0, innerWidth, innerHeight);
  ctx.fillStyle = "#020611";
  ctx.fillRect(0, 0, innerWidth, innerHeight);
  for (const star of state.stars) {
    ctx.globalAlpha = star.p;
    ctx.fillStyle = "#dff8ff";
    ctx.fillRect(
      (star.x - state.ship.x * 0.004 * star.p + innerWidth) % innerWidth,
      (star.y - state.ship.z * 0.004 * star.p + innerHeight) % innerHeight,
      star.d,
      star.d,
    );
  }
  ctx.globalAlpha = 1;
  drawGrid();
  drawObjects();
  drawShip();
  requestAnimationFrame(draw);
}

function tick() {
  const thrust = state.keys.has("Shift") ? 42 : 22;
  if (state.keys.has("a") || state.keys.has("A")) state.ship.angle -= 0.045;
  if (state.keys.has("d") || state.keys.has("D")) state.ship.angle += 0.045;
  if (state.keys.has("w") || state.keys.has("W")) state.ship.speed += thrust;
  if (state.keys.has("s") || state.keys.has("S")) state.ship.speed -= 18;
  state.ship.speed *= 0.985;
  state.ship.speed = Math.max(-450, Math.min(1450, state.ship.speed));
  state.ship.x += Math.cos(state.ship.angle) * state.ship.speed * 0.016;
  state.ship.z += Math.sin(state.ship.angle) * state.ship.speed * 0.016;
  document.getElementById("speed-bar").style.width = `${Math.min(100, Math.abs(state.ship.speed) / 14.5)}%`;
  document.getElementById("speed-readout").textContent = `${Math.round(state.ship.speed)} m/s`;
  checkDock();
  setTimeout(tick, 16);
}

function nearestIndex() {
  let best = 0;
  let bestDistance = Infinity;
  state.objects.forEach((object, index) => {
    const distance = Math.hypot(object.x - state.ship.x, object.z - state.ship.z);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

function updateTarget() {
  const object = state.objects[state.target];
  document.getElementById("target-name").textContent = object ? `${object.name} (${object.kind})` : "нет цели";
  document.getElementById("target-distance").textContent = object
    ? `${Math.round(Math.hypot(object.x - state.ship.x, object.z - state.ship.z))} м`
    : "Tab выберет ближайший объект";
}

function checkDock() {
  const object = state.objects[state.target];
  if (!object) {
    return;
  }
  const distance = Math.hypot(object.x - state.ship.x, object.z - state.ship.z);
  document.getElementById("target-distance").textContent = `${Math.round(distance)} м`;
  if (distance < 850 && (object.kind === "base" || object.kind === "planet")) {
    showToast(`Стыковка доступна: ${object.name}`);
  }
}

function showToast(text) {
  const element = document.getElementById("dock-toast");
  element.hidden = false;
  element.textContent = text;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 900);
}

addEventListener("resize", resize);
addEventListener("keydown", (event) => {
  state.keys.add(event.key);
  if (event.key === "Tab") {
    event.preventDefault();
    state.target = nearestIndex();
    updateTarget();
  }
  if (event.key === " ") {
    state.ship.speed += 650;
    showToast("Cruise impulse");
  }
  if (event.key === "m" || event.key === "M") {
    document.getElementById("map-panel").classList.toggle("hidden");
  }
});
addEventListener("keyup", (event) => state.keys.delete(event.key));
document.getElementById("jump-button").onclick = () => load(document.getElementById("system-select").value);

resize();
load().then(() => {
  tick();
  draw();
});
