import { SproutHero } from "../components/home/SproutHero";
import "../components/home/BlankPage.css";
export function SproutPage() {
	return (
		<div className="home-page">
			<div className="home-ambient-sun" aria-hidden="true" />
			<div className="home-paper-canvas" aria-hidden="true" />
			<SproutHero />
		</div>
	);
}
