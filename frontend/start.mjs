import { cpSync } from "node:fs";

// Standalone bundles intentionally omit browser assets. The Docker build
// copies these during packaging; local starts copy them after next build.
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
process.env.HOSTNAME = "127.0.0.1";
await import("./.next/standalone/server.js");
