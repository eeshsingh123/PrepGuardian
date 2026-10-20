import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createConnection } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BACKEND_DIR = join(ROOT, "backend");
const FRONTEND_DIR = join(ROOT, "frontend");

const SERVICES = [
  { name: "mongo", port: 27017 },
  { name: "redis", port: 6379 },
];

const APPS = [
  { name: "backend", color: 36, cwd: BACKEND_DIR, cmd: "uv run python -m uvicorn main:app --reload --port 8000" },
  { name: "frontend", color: 35, cwd: FRONTEND_DIR, cmd: "npm run dev" },
];

const log = (msg) => console.log(`\x1b[1m[dev]\x1b[0m ${msg}`);

function fail(msg) {
  console.error(`\x1b[31m[dev] ${msg}\x1b[0m`);
  process.exit(1);
}

function isPortOpen(port) {
  return new Promise((resolve) => {
    const socket = createConnection({ host: "127.0.0.1", port });
    socket.setTimeout(1000);
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("timeout", () => { socket.destroy(); resolve(false); });
    socket.once("error", () => resolve(false));
  });
}

async function waitForPort(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isPortOpen(port)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

const DOCKER_DESKTOP_EXE = "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe";

function runOnce(cmd, cwd, stdio = "inherit") {
  return spawnSync(cmd, { cwd, shell: true, stdio }).status === 0;
}

const isDockerUp = () => runOnce("docker info", ROOT, "ignore");

async function ensureDocker() {
  if (isDockerUp()) return true;
  if (process.platform !== "win32" || !existsSync(DOCKER_DESKTOP_EXE)) return false;
  log("starting Docker Desktop (first start can take a minute)");
  spawn(DOCKER_DESKTOP_EXE, { detached: true, stdio: "ignore" }).unref();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 3000));
    if (isDockerUp()) return true;
  }
  return false;
}

async function ensureServices() {
  const missing = [];
  for (const service of SERVICES) {
    if (await isPortOpen(service.port)) log(`${service.name} already running on :${service.port}`);
    else missing.push(service);
  }
  if (missing.length === 0) return;

  const names = missing.map((s) => s.name).join(" ");
  if (!(await ensureDocker())) {
    fail(`${names} not running and Docker is unavailable. Start Docker Desktop (or run ${names} locally) and retry.`);
  }
  log(`starting ${names} with docker compose`);
  if (!runOnce(`docker compose up -d ${names}`, ROOT)) fail("docker compose failed.");
  for (const service of missing) {
    if (!(await waitForPort(service.port))) fail(`${service.name} did not open :${service.port} in time.`);
    log(`${service.name} ready on :${service.port}`);
  }
}

function ensureDependencies() {
  if (!existsSync(join(BACKEND_DIR, ".venv"))) {
    log("installing backend dependencies (uv sync)");
    if (!runOnce("uv sync", BACKEND_DIR)) fail("uv sync failed.");
  }
  if (!existsSync(join(FRONTEND_DIR, "node_modules"))) {
    log("installing frontend dependencies (npm install)");
    if (!runOnce("npm install", FRONTEND_DIR)) fail("npm install failed.");
  }
}

function checkEnvironment() {
  if (!process.env.GOOGLE_CLOUD_PROJECT && !existsSync(join(BACKEND_DIR, ".env"))) {
    fail("GOOGLE_CLOUD_PROJECT is not set. Copy backend/.env.example to backend/.env and fill it in.");
  }
}

function prefixStream(stream, app) {
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop();
    for (const line of lines) console.log(`\x1b[${app.color}m[${app.name}]\x1b[0m ${line}`);
  });
}

function startApps() {
  const children = APPS.map((app) => {
    const child = spawn(app.cmd, { cwd: app.cwd, shell: true });
    prefixStream(child.stdout, app);
    prefixStream(child.stderr, app);
    child.on("exit", (code) => {
      log(`${app.name} exited (code ${code}); stopping everything`);
      shutdown(code ?? 1);
    });
    return child;
  });

  let stopping = false;
  function shutdown(code) {
    if (stopping) return;
    stopping = true;
    for (const child of children) {
      if (child.exitCode !== null) continue;
      if (process.platform === "win32") spawnSync(`taskkill /pid ${child.pid} /T /F`, { shell: true, stdio: "ignore" });
      else child.kill("SIGTERM");
    }
    process.exit(code);
  }

  process.on("SIGINT", () => shutdown(0));
  process.on("SIGTERM", () => shutdown(0));
  log("backend → http://127.0.0.1:8000   frontend → http://localhost:5173   (Ctrl+C stops both)");
}

checkEnvironment();
await ensureServices();
ensureDependencies();
startApps();
