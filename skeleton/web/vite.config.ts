import { defineConfig, type Plugin } from "vite";

// Same policy as CONTENT_SECURITY_POLICY in skeleton/src/nightaudit/api.py, for static hosting that cannot send headers.
// frame-ancestors cannot be set from a meta tag, so it is left to the header. Only the built page carries it: the dev
// server injects inline styles.
const CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; " +
  "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'";

function cspMeta(): Plugin {
  return {
    name: "nightaudit-csp-meta",
    apply: "build",
    transformIndexHtml: (html) =>
      html.replace(
        '<meta charset="utf-8" />',
        `<meta charset="utf-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`,
      ),
  };
}

export default defineConfig({
  base: "./",
  plugins: [cspMeta()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        // The browser verifier is a stable, readable chunk so the e2e parity test imports the exact shipped code.
        manualChunks: (id) => (/[\\/]src[\\/](verify|canonical)\.ts$/.test(id) ? "verify" : undefined),
        chunkFileNames: (chunk) => (chunk.name === "verify" ? "assets/verify.js" : "assets/[name]-[hash].js"),
        minifyInternalExports: false,
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
