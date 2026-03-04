const { spawn } = require('child_process');

const child = spawn('python', ['main.py'], {
  env: process.env,
  stdio: 'inherit',
});

let shuttingDown = false;

const forwardSignal = (signal) => {
  if (!shuttingDown) {
    shuttingDown = true;
    child.kill(signal);
  }
};

process.on('SIGTERM', () => forwardSignal('SIGTERM'));
process.on('SIGINT', () => forwardSignal('SIGINT'));

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

child.on('error', (err) => {
  console.error('Failed to start python main.py:', err);
  process.exit(1);
});
