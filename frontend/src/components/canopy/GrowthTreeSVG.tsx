interface GrowthTreeSVGProps {
  stage: number;
}

function stageVisible(stage: number, requiredStage: number): string {
  return stage >= requiredStage ? 'is-visible' : '';
}

export function GrowthTreeSVG({ stage }: GrowthTreeSVGProps) {
  const visibleStage = Math.min(Math.max(Math.round(stage), 1), 6);

  return (
    <svg
      className="growth-tree-svg"
      viewBox="0 0 240 240"
      role="img"
      aria-label={`成森成长阶段 ${visibleStage}`}
      data-stage={visibleStage}
    >
      <defs>
        <radialGradient id="tree-ground-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="oklch(84% 0.08 58 / 0.48)" />
          <stop offset="100%" stopColor="oklch(84% 0.08 58 / 0)" />
        </radialGradient>
        <linearGradient id="tree-trunk" x1="100" y1="210" x2="138" y2="70" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="oklch(50% 0.08 58)" />
          <stop offset="100%" stopColor="oklch(64% 0.09 65)" />
        </linearGradient>
      </defs>

      <circle className="tree-stage layer-ground is-visible" cx="120" cy="168" r="78" fill="url(#tree-ground-glow)" />
      <ellipse className="tree-stage layer-ground is-visible" cx="120" cy="188" rx="62" ry="18" fill="oklch(72% 0.08 66 / 0.46)" />
      <ellipse className="tree-stage layer-ground is-visible" cx="120" cy="190" rx="42" ry="10" fill="oklch(58% 0.07 62 / 0.34)" />

      <g className={`tree-stage layer-seed ${stageVisible(visibleStage, 1)}`}>
        <ellipse
          cx="120"
          cy="180"
          rx="12"
          ry="8"
          transform="rotate(-18 120 180)"
          fill="oklch(56% 0.08 58)"
        />
        <path
          d="M112 181 C117 174 125 172 130 177"
          fill="none"
          stroke="oklch(75% 0.08 72 / 0.62)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>

      <g className={`tree-stage layer-sprout ${stageVisible(visibleStage, 2)}`}>
        <path
          d="M118 183 C114 164 116 145 132 132"
          fill="none"
          stroke="oklch(54% 0.11 132)"
          strokeWidth="9"
          strokeLinecap="round"
        />
        <path
          d="M130 134 C117 128 107 130 99 139 C113 143 124 142 130 134Z"
          fill="oklch(75% 0.09 135)"
        />
      </g>

      <g className={`tree-stage layer-branches ${stageVisible(visibleStage, 3)}`}>
        <path
          d="M120 185 C118 154 122 124 132 82"
          fill="none"
          stroke="url(#tree-trunk)"
          strokeWidth="14"
          strokeLinecap="round"
        />
        <path
          d="M130 116 C105 106 90 91 80 73"
          fill="none"
          stroke="oklch(55% 0.08 62)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path
          d="M132 104 C154 94 170 78 180 58"
          fill="none"
          stroke="oklch(58% 0.08 62)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path
          d="M126 139 C102 137 82 128 66 112"
          fill="none"
          stroke="oklch(56% 0.08 62)"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d="M128 132 C152 132 172 122 188 106"
          fill="none"
          stroke="oklch(56% 0.08 62)"
          strokeWidth="6"
          strokeLinecap="round"
        />
      </g>

      <g className={`tree-stage layer-leaves canopy-breathe ${stageVisible(visibleStage, 4)}`}>
        <ellipse cx="82" cy="74" rx="24" ry="16" fill="oklch(74% 0.09 135)" />
        <ellipse cx="65" cy="113" rx="22" ry="15" fill="oklch(78% 0.08 132)" />
        <ellipse cx="101" cy="105" rx="24" ry="17" fill="oklch(70% 0.1 138)" />
        <ellipse cx="143" cy="83" rx="26" ry="17" fill="oklch(76% 0.09 135)" />
        <ellipse cx="176" cy="59" rx="23" ry="15" fill="oklch(80% 0.08 132)" />
        <ellipse cx="184" cy="105" rx="25" ry="16" fill="oklch(72% 0.1 138)" />
        <ellipse cx="146" cy="127" rx="29" ry="18" fill="oklch(77% 0.08 132)" />
        <ellipse cx="112" cy="70" rx="22" ry="15" fill="oklch(82% 0.07 130)" />
      </g>

      <g className={`tree-stage layer-grove ${stageVisible(visibleStage, 5)}`}>
        <path d="M48 186 C46 167 48 150 54 131" fill="none" stroke="oklch(57% 0.07 62 / 0.58)" strokeWidth="8" strokeLinecap="round" />
        <ellipse cx="54" cy="126" rx="24" ry="22" fill="oklch(75% 0.08 135 / 0.58)" />
        <path d="M198 188 C198 168 202 151 208 134" fill="none" stroke="oklch(57% 0.07 62 / 0.52)" strokeWidth="8" strokeLinecap="round" />
        <ellipse cx="209" cy="128" rx="25" ry="22" fill="oklch(73% 0.08 135 / 0.52)" />
      </g>

      <g className={`tree-stage layer-bloom canopy-breathe ${stageVisible(visibleStage, 6)}`}>
        <circle cx="75" cy="70" r="5" fill="oklch(72% 0.13 28)" />
        <circle cx="105" cy="102" r="5" fill="oklch(76% 0.12 55)" />
        <circle cx="143" cy="75" r="5" fill="oklch(72% 0.13 28)" />
        <circle cx="171" cy="101" r="5" fill="oklch(76% 0.12 55)" />
        <circle cx="132" cy="126" r="5" fill="oklch(72% 0.13 28)" />
        <path d="M61 52 L64 59 L71 62 L64 65 L61 72 L58 65 L51 62 L58 59Z" fill="oklch(84% 0.08 58)" />
        <path d="M189 45 L192 51 L198 54 L192 57 L189 63 L186 57 L180 54 L186 51Z" fill="oklch(84% 0.08 58)" />
        <path d="M201 137 L204 143 L210 146 L204 149 L201 155 L198 149 L192 146 L198 143Z" fill="oklch(84% 0.08 58)" />
      </g>
    </svg>
  );
}
