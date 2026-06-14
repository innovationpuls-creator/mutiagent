import { useCallback, useState, useEffect } from 'react';
import PrismJS from 'prismjs';
import 'prismjs/components/prism-clike';
import 'prismjs/components/prism-c';
import 'prismjs/components/prism-cpp';
import 'prismjs/components/prism-java';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-json';

// Set manual mode statically
PrismJS.manual = true;

export function usePrism(enabled = true) {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    if (enabled) {
      setIsLoaded(true);
    }
  }, [enabled]);

  const highlight = useCallback(
    async (code: string, language: string): Promise<string> => {
      try {
        const lang = language.toLowerCase();
        if (PrismJS.languages[lang]) {
          return PrismJS.highlight(code, PrismJS.languages[lang], lang);
        }
      } catch (error) {
        console.warn(`Failed to highlight language: ${language}`, error);
      }

      return code;
    },
    []
  );

  return { highlight, isLoaded };
}
