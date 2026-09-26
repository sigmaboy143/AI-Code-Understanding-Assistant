import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
export default defineConfig({
    plugins: [react()],
    build: {
        outDir: "dist",
        rollupOptions: {
            output: {
                // Flat asset paths so the extension can rewrite them easily
                entryFileNames: "assets/[name].js",
                chunkFileNames: "assets/[name].js",
                assetFileNames: "assets/[name].[ext]",
            },
        },
    },
    resolve: {
        alias: {
            "@shared": path.resolve(__dirname, "../src/types"),
        },
    },
    // Prevents Vite from trying to open a browser during dev in extension context
    server: {
        open: false,
        port: 3001,
    },
});
//# sourceMappingURL=vite.config.js.map