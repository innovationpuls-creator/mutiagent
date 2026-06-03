import { motion } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';

interface Props {
  options: string[];
  active: string;
  onChange: (val: string) => void;
}

export function SegmentedControl({ options, active, onChange }: Props) {
  return (
    <div 
      style={{ 
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        padding: 'var(--space-4)',
        gap: 'var(--space-4)',
        background: 'var(--color-pebble-matte)',
        backdropFilter: 'var(--glass-pebble-blur-matte)',
        WebkitBackdropFilter: 'var(--glass-pebble-blur-matte)',
        borderRadius: 'var(--radius-full)',
        height: 'calc(var(--height-groove-track) + 8px)'
      }}
    >
      {options.map((option) => {
        const isActive = active === option;
        return (
          <button
            key={option}
            onClick={() => onChange(option)}
            style={{ 
              position: 'relative',
              zIndex: 10,
              padding: '0 var(--space-24)',
              height: '100%',
              borderRadius: 'var(--radius-full)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              border: 'none',
              background: 'transparent',
              color: isActive ? 'var(--color-text-inverse)' : 'var(--color-text-whisper)',
              fontFamily: 'var(--font-heading)',
              fontWeight: 'var(--font-weight-medium)',
              transition: 'color 300ms ease'
            }}
          >
            {isActive && (
              <motion.div
                layoutId="branch-slider-pebble"
                style={{
                  position: 'absolute',
                  inset: 0,
                  zIndex: -1,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--color-secondary)',
                  boxShadow: 'inset 0 1px 1px oklch(100% 0 0 / 0.25), 0 4px 12px oklch(49% 0.05 235 / 0.2)'
                }}
                transition={motionTokens.lazy}
              />
            )}
            <span style={{ position: 'relative', zIndex: 10, fontSize: 'var(--text-body-sm)' }}>{option}</span>
          </button>
        );
      })}
    </div>
  );
}
