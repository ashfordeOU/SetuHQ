// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// A static server that serves a built site at the domain root the way GitHub Pages does: /a/b/ serves
// a/b/index.html, /a/b (no slash) redirects to /a/b/, and any unknown address gets 404.html with status 404.
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, resolve } from "node:path";

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
  ".csv": "text/csv; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".xml": "application/xml" };

export function serve(root, port = 0) {
  root = resolve(root);
  const server = createServer((req, res) => {
    let path;
    try { path = decodeURIComponent(new URL(req.url, "http://x").pathname); } catch (e) { res.writeHead(400); res.end(); return; }
    let file = join(root, path);
    if (!file.startsWith(root)) { res.writeHead(403); res.end(); return; }
    if (existsSync(file) && statSync(file).isDirectory()) {
      if (!path.endsWith("/")) { res.writeHead(301, { location: path + "/" + (new URL(req.url, "http://x").search) }); res.end(); return; }
      file = join(file, "index.html");
    }
    if (existsSync(file) && statSync(file).isFile()) {
      res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
      res.end(readFileSync(file));
      return;
    }
    const nf = join(root, "404.html");
    res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
    res.end(existsSync(nf) ? readFileSync(nf) : "not found");
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(server)));
}

if (process.argv[1] && process.argv[1].endsWith("server.mjs")) {
  const root = process.argv[2] || "site", port = Number(process.argv[3] || 8765);
  serve(root, port).then((s) => console.log(`serving ${root} at http://127.0.0.1:${s.address().port}/`));
}
