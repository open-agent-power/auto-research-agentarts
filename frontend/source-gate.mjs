#!/usr/bin/env node
/** Whitespace-only formatter for this compact frontend; no third-party toolchain. */
import { lstatSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { extname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const [command, ...args] = process.argv.slice(2);
if (command !== "format" || args.some(arg => arg !== "--check")) {
  process.stderr.write("Usage: node source-gate.mjs format [--check]\n");
  process.exit(2);
}
const checking = args.includes("--check");
const files = ["package.json", "tsconfig.json", "index.html", "build.mjs", "source-gate.mjs"];
function visit(directory) {
  for (const name of readdirSync(directory).sort()) {
    const path = resolve(directory, name), metadata = lstatSync(path);
    if (metadata.isSymbolicLink()) throw Error("Frontend format inputs must not be symbolic links.");
    if (metadata.isDirectory()) visit(path);
    else if (metadata.isFile() && [".ts", ".css"].includes(extname(path))) files.push(relative(root, path));
  }
}
visit(resolve(root, "src"));
let changed = 0;
for (const name of files) {
  const path = resolve(root, name);
  if (!lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) throw Error("Format inputs must be regular frontend files.");
  const raw = readFileSync(path), value = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(raw);
  // Keep each file's existing LF/CRLF convention, normalize mixed EOLs and
  // normalize trailing horizontal whitespace and extra final empty lines.
  const ending = value.includes("\r\n") ? "\r\n" : "\n";
  const formatted = (value.replace(/\r\n?/g, "\n").replace(/[\t ]+$/gm, "").replace(/\n*$/, "") + "\n").replace(/\n/g, ending);
  if (formatted !== value) {
    changed += 1;
    process.stdout.write((checking ? "Needs formatting: " : "Formatted: ") + name + "\n");
    if (!checking) writeFileSync(path, formatted, "utf8");
  }
}
process.stdout.write(`Whitespace ${checking ? "check" : "format"}: ${files.length} files, ${changed} ${checking ? "requiring changes" : "changed"}.\n`);
if (checking && changed) process.exitCode = 1;
