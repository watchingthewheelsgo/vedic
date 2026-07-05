#!/usr/bin/env node

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const backendUrl =
  process.env.CREEM_TUNNEL_TARGET_URL || `http://127.0.0.1:${process.env.PORT || "8787"}`;
const protocol = process.env.CLOUDFLARED_PROTOCOL || "http2";
const outputPath = resolve(process.cwd(), "tmp", "creem-webhook-url.txt");
const urlPattern = /https:\/\/[-a-zA-Z0-9.]+\.trycloudflare\.com/;

let publishedUrl = "";

function log(message) {
  process.stdout.write(`[creem-webhook] ${message}\n`);
}

function publishUrl(baseUrl) {
  if (publishedUrl === baseUrl) return;
  publishedUrl = baseUrl;
  const webhookUrl = `${baseUrl}/api/webhooks/creem`;
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${webhookUrl}\n`);
  log(`Webhook URL: ${webhookUrl}`);
  log(`Saved to ${outputPath}`);
  log("Create or update the Creem Dashboard webhook with that URL.");
}

log(`Starting Cloudflare quick tunnel -> ${backendUrl}`);

const child = spawn(
  "cloudflared",
  ["tunnel", "--url", backendUrl, "--protocol", protocol, "--loglevel", "info"],
  {
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"]
  }
);

child.stdout.on("data", (chunk) => {
  const text = chunk.toString();
  process.stdout.write(text);
  const match = text.match(urlPattern);
  if (match) publishUrl(match[0]);
});

child.stderr.on("data", (chunk) => {
  const text = chunk.toString();
  process.stderr.write(text);
  const match = text.match(urlPattern);
  if (match) publishUrl(match[0]);
});

child.on("error", (error) => {
  if (error.code === "ENOENT") {
    log("cloudflared is not installed. Install it with `brew install cloudflared`.");
    process.exit(1);
  }
  log(error.message);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    log(`cloudflared stopped by ${signal}`);
    process.exit(0);
  }
  if (code === 0) {
    log("cloudflared stopped");
    process.exit(0);
  }
  log(`cloudflared exited with code ${code}`);
  process.exit(code ?? 1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    child.kill(signal);
  });
}
