import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useState,
} from "react";
import { AUTH_INVALID_EVENT } from "../api/http";
import type { AuthResponse, AuthUser } from "../types/auth";

interface AuthState {
	user: AuthUser | null;
	token: string | null;
	isAuthReady: boolean;
	login(authResponse: AuthResponse): void;
	logout(): void;
}

const AuthContext = createContext<AuthState | null>(null);

const STORAGE_KEY = "mutiagent-auth";

function normalizeUser(user: AuthUser): AuthUser {
	const normalized = {
		...user,
		school: typeof user.school === "string" ? user.school : "",
		major: typeof user.major === "string" ? user.major : "",
		class_name: typeof user.class_name === "string" ? user.class_name : "",
	};
	const role =
		(normalized.role as string) === "teacher" || normalized.role === "admin"
			? "admin"
			: "student";
	return { ...normalized, role };
}

function loadAuth(): { user: AuthUser; token: string } | null {
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			const parsed = JSON.parse(stored) as { user: AuthUser; token: string };
			if (parsed.user?.uid && parsed.token) {
				return { user: normalizeUser(parsed.user), token: parsed.token };
			}
		}
	} catch {
		/* corrupted data — treat as logged out */
	}
	return null;
}

function saveAuth(user: AuthUser | null, token: string | null) {
	if (user && token) {
		localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, token }));
	} else {
		localStorage.removeItem(STORAGE_KEY);
	}
}

export function AuthProvider({ children }: { children: ReactNode }) {
	const [user, setUser] = useState<AuthUser | null>(null);
	const [token, setToken] = useState<string | null>(null);
	const [isAuthReady, setIsAuthReady] = useState(false);

	useEffect(() => {
		const stored = loadAuth();
		if (stored) {
			setUser(stored.user);
			setToken(stored.token);
		}
		setIsAuthReady(true);
	}, []);

	useEffect(() => {
		if (typeof window === "undefined") {
			return undefined;
		}

		const handleAuthInvalid = () => {
			setUser(null);
			setToken(null);
			saveAuth(null, null);
		};

		window.addEventListener(AUTH_INVALID_EVENT, handleAuthInvalid);
		return () =>
			window.removeEventListener(AUTH_INVALID_EVENT, handleAuthInvalid);
	}, []);

	const login = useCallback((authResponse: AuthResponse) => {
		const user = normalizeUser(authResponse.user);
		setUser(user);
		setToken(authResponse.access_token);
		saveAuth(user, authResponse.access_token);
	}, []);

	const logout = useCallback(() => {
		setUser(null);
		setToken(null);
		saveAuth(null, null);
	}, []);

	return (
		<AuthContext.Provider value={{ user, token, isAuthReady, login, logout }}>
			{children}
		</AuthContext.Provider>
	);
}

export function useAuth(): AuthState {
	const context = useContext(AuthContext);
	if (!context) {
		throw new Error("useAuth must be used within an AuthProvider");
	}
	return context;
}
