import { useCallback, useState, useEffect, useRef } from 'react';
import type * as PrismJS from 'prismjs';

export function usePrism(enabled = true) {
  const [Prism, setPrism] = useState<typeof PrismJS | null>(null);
  const prismRef = useRef<typeof PrismJS | null>(null);
  const loadedLanguages = useRef(new Set<string>());

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    import('prismjs').then((module) => {
      if (!active) return;
      module.manual = true;
      prismRef.current = module;
      setPrism(module);
    });
    return () => { active = false; };
  }, [enabled]);

  const highlight = useCallback(
    async (code: string, language: string): Promise<string> => {
      const prism = prismRef.current;
      if (!prism) return code;

      try {
        if (!loadedLanguages.current.has(language)) {
          await import(/* @vite-ignore */ `prismjs/components/prism-${language}`);
          loadedLanguages.current.add(language);
        }
        if (prism.languages[language]) {
          return prism.highlight(code, prism.languages[language], language);
        }
      } catch (error) {
        console.warn(`Failed to load language: ${language}`, error);
      }

      return code;
    },
    []
  );

  return { highlight, isLoaded: !!Prism };
}
