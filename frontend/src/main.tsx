import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { ModelConfigProvider } from "./contexts/ModelConfigContext";
import "@fontsource/caveat/600.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/auth.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
	<React.StrictMode>
		<AuthProvider>
			<ModelConfigProvider>
				<App />
			</ModelConfigProvider>
		</AuthProvider>
	</React.StrictMode>,
);
