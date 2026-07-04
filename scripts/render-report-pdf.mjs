#!/usr/bin/env node

import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

function readArgs(argv) {
  const args = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for --${key}`);
    }
    args.set(key, value);
    index += 1;
  }
  const input = args.get("input");
  const output = args.get("output");
  if (!input || !output) {
    throw new Error("Usage: node scripts/render-report-pdf.mjs --input report.html --output report.pdf");
  }
  return {
    input: resolve(input),
    output: resolve(output),
  };
}

function footerTemplate() {
  return `
    <div style="
      width: 100%;
      margin: 0 16mm;
      padding-top: 5px;
      border-top: 1px solid rgba(23,32,31,.18);
      color: #65716f;
      font-family: Avenir Next, Helvetica Neue, Arial, sans-serif;
      font-size: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      -webkit-print-color-adjust: exact;
    ">
      <span>Vedic Report</span>
      <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
    </div>
  `;
}

async function main() {
  const { input, output } = readArgs(process.argv.slice(2));
  if (!existsSync(input)) {
    throw new Error(`Input HTML not found: ${input}`);
  }
  mkdirSync(dirname(output), { recursive: true });

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1240, height: 1754 },
      deviceScaleFactor: 1,
    });
    await page.emulateMedia({ media: "print" });
    await page.goto(pathToFileURL(input).toString(), { waitUntil: "networkidle" });
    await page.pdf({
      path: output,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: "<div></div>",
      footerTemplate: footerTemplate(),
      margin: {
        top: "16mm",
        right: "16mm",
        bottom: "20mm",
        left: "16mm",
      },
    });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
