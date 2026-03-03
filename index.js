const { spawn } = require("child_process");

const py = spawn("python", ["main.py"], {
  stdio: "inherit",
  env: process.env,
});

py.on("exit", (code, signal) => {
  if (signal) process.exit(1);
  process.exit(code ?? 1);
});

process.on("SIGTERM", () => py.kill("SIGTERM"));
process.on("SIGINT", () => py.kill("SIGINT"));
