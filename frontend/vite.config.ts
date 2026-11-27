import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const aiGatewayTarget =
	process.env.VITE_AI_GATEWAY_PROXY_TARGET ?? "http://127.0.0.1:8100";

export default defineConfig({
	plugins: [react()],
	server: {
		port: 5173,
		proxy: {
			"^/api/ai(/|$)": {
				target: aiGatewayTarget,
				changeOrigin: true,
			},
			"/api": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true,
			},
		},
	},
});
