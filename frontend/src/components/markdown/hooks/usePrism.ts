import { useCallback, useState, useEffect } from 'react';
import type * as PrismJS from 'prismjs';

export function usePrism() {
  const [Prism, setPrism] = useState<typeof PrismJS | null>(null);

  useEffect(() => {
    import('prismjs').then((module) => {
      setPrism(module);
    });
  }, []);

  const highlight = useCallback(
    async (code: string, language: string): Promise<string> => {
      if (!Prism) return code;

      try {
        await import(`prismjs/components/prism-${language}`);
        if (Prism.languages[language]) {
          return Prism.highlight(code, Prism.languages[language], language);
        }
      } catch (error) {
        console.warn(`Failed to load language: ${language}`, error);
      }

      return code;
    },
    [Prism]
  );

  return { highlight, isLoaded: !!Prism };
}
