export interface SemesterStatItem {
	semester: string;
	credits: number;
	hours: number;
	completedCourses: number;
	totalCourses: number;
}

interface SemesterBarChartProps {
	data: SemesterStatItem[];
	type: "credits" | "hours";
}

export function SemesterBarChart({ data, type }: SemesterBarChartProps) {
	const maxValue = Math.max(
		...data.map((d) => (type === "credits" ? d.credits : d.hours)),
		1,
	);

	return (
		<svg viewBox="0 0 400 150" className="chart-svg-container">
			{/* 坐标轴 */}
			<line x1="30" y1="120" x2="380" y2="120" className="chart-axis-line" />

			{data.map((d, index) => {
				const val = type === "credits" ? d.credits : d.hours;
				// 高度映射
				const barHeight = (val / maxValue) * 90;
				const x = 40 + index * 42;
				const y = 120 - barHeight;
				const barWidth = 24;

				const isCompleted =
					d.totalCourses > 0 && d.completedCourses === d.totalCourses;

				return (
					<g key={d.semester} className="chart-bar-group">
						{barHeight > 0 && (
							<rect
								x={x}
								y={y}
								width={barWidth}
								height={barHeight}
								rx={4}
								className={`chart-bar ${isCompleted ? "chart-bar-completed" : ""}`}
							/>
						)}
						<text x={x + 12} y={135} textAnchor="middle" className="chart-text">
							T{d.semester}
						</text>
						<text
							x={x + 12}
							y={y - 6}
							textAnchor="middle"
							className="chart-text"
							style={{ fontSize: "9px" }}
						>
							{val}
						</text>
					</g>
				);
			})}
		</svg>
	);
}
