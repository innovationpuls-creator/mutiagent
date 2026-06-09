import { useState, useEffect, useRef } from 'react';

export function useMathJax(enabled = true) {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let active = true;

    (window as any).MathJax = {
      startup: {
        typeset: false,
        ready: () => {
          const MathJax = (window as any).MathJax;
          MathJax.startup.defaultReady();
          if (active) {
            setIsLoaded(true);
          }
        },
      },
      tex: {
        inlineMath: [['$', '$']],
        displayMath: [['$$', '$$']],
      },
    };

    import('mathjax').then(() => {
      // MathJax will initialize via the window config
    });

    return () => {
      active = false;
    };
  }, [enabled]);

  return { isLoaded };
}
