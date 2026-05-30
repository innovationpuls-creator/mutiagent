import React, { useRef, useState, useEffect } from 'react';
import { motion, useMotionValue, useTransform, animate } from 'framer-motion';
import '../../styles/icebreaker.css';

export interface PebbleSliderProps {
  options: string[];
  value: string;
  onChange: (val: string) => void;
}

export function PebbleSlider({ options, value, onChange }: PebbleSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<HTMLDivElement>(null);
  
  const [constraints, setConstraints] = useState({ left: 0, right: 0 });
  const x = useMotionValue(0);
  
  // Calculate snap points and constraints
  useEffect(() => {
    if (trackRef.current && handleRef.current) {
      const trackWidth = trackRef.current.offsetWidth - 12; // 6px padding on each side
      const handleWidth = handleRef.current.offsetWidth;
      const maxTravel = trackWidth - handleWidth;
      
      setConstraints({ left: 0, right: maxTravel });
      
      // Initial position
      const initialIndex = Math.max(0, options.indexOf(value));
      const step = maxTravel / (options.length - 1);
      x.set(initialIndex * step);
    }
  }, [options, value, x]);

  // When drag ends, snap to closest option
  const handleDragEnd = () => {
    const currentX = x.get();
    const maxTravel = constraints.right;
    const step = maxTravel / (options.length - 1);
    
    // Find closest snap point
    const closestIndex = Math.round(currentX / step);
    const snapX = closestIndex * step;
    
    // Animate to snap point with a spring
    animate(x, snapX, {
      type: "spring",
      stiffness: 400,
      damping: 30
    });
    
    // Update value if changed
    onChange(options[closestIndex]);
  };

  return (
    <div className="pebble-slider-track" ref={trackRef}>
      <div className="pebble-slider-bg-labels">
        {options.map((opt, i) => (
          <span key={i} className="pebble-bg-label">{opt}</span>
        ))}
      </div>
      
      <motion.div
        className="pebble-slider-handle"
        ref={handleRef}
        drag="x"
        dragConstraints={constraints}
        dragElastic={0.05} // Very slight physical tug when hitting edges
        dragMomentum={false} // Prevents sliding too far past constraints
        onDragEnd={handleDragEnd}
        whileHover={{ scale: 1.02 }}
        whileDrag={{ scale: 0.95, backdropFilter: 'blur(32px)' }} // Haptic push-in
        style={{ x }}
      >
        <span className="pebble-slider-label">{value}</span>
      </motion.div>
    </div>
  );
}
