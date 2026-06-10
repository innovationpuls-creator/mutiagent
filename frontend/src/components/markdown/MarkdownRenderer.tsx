import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { usePrism } from './hooks/usePrism';
import { useMathJax } from './hooks/useMathJax';
import { useMermaid } from './hooks/useMermaid';
import { extractLanguage } from './utils/highlight';
import { copyToClipboard } from './utils/clipboard';
import './markdown-styles.css';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  variant?: 'default' | 'editorial' | 'compact';
  enableSyntaxHighlight?: boolean;
  enableMath?: boolean;
  enableMermaid?: boolean;
}

interface CheckboxInputProps {
  type?: string;
  checked?: boolean;
}

interface MarkdownCodeElementProps extends React.HTMLAttributes<HTMLElement> {
  node?: unknown;
}

function getTextContent(children: React.ReactNode): string {
  let text = '';
  React.Children.forEach(children, (child) => {
    if (typeof child === 'string' || typeof child === 'number') {
      text += child;
    } else if (React.isValidElement(child) && child.props && child.props.children) {
      text += getTextContent(child.props.children);
    }
  });
  return text;
}

function cleanAlertPrefix(children: React.ReactNode): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === 'string') {
      return child.replace(/\[!(NOTE|IMPORTANT|WARNING|TIP|CAUTION)\]/g, '').trim();
    }
    if (React.isValidElement(child) && child.props && child.props.children) {
      return React.cloneElement(child as React.ReactElement<{ children?: React.ReactNode }>, {
        children: cleanAlertPrefix(child.props.children),
      });
    }
    return child;
  });
}

function isMarkdownCodeElement(
  child: React.ReactNode,
): child is React.ReactElement<MarkdownCodeElementProps> {
  return React.isValidElement<MarkdownCodeElementProps>(child);
}

function getCodeBlockText(children: React.ReactNode): string {
  return getTextContent(children).replace(/\n$/, '');
}

function renderCodeBlockFrame(
  language: string,
  codeText: string,
  content: React.ReactNode,
  copyAriaLabel = 'Copy code to clipboard',
) {
  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-lang">{language || 'code'}</span>
        <button
          className="code-block-copy"
          aria-label={copyAriaLabel}
          onClick={(e) => copyToClipboard(codeText, e.currentTarget)}
        >
          COPY
        </button>
      </div>
      {content}
    </div>
  );
}

const markdownComponents: Components = {
  h1: ({ node, ...props }) => <h1 {...props} />,
  h2: ({ node, ...props }) => <h2 {...props} />,
  h3: ({ node, ...props }) => <h3 {...props} />,
  h4: ({ node, ...props }) => <h4 {...props} />,
  h5: ({ node, ...props }) => <h5 {...props} />,
  h6: ({ node, ...props }) => <h6 {...props} />,
  p: ({ node, ...props }) => <p {...props} />,
  a: ({ node, ...props }) => <a {...props} />,
  strong: ({ node, ...props }) => <strong {...props} />,
  em: ({ node, ...props }) => <em {...props} />,
  ul: ({ node, ...props }) => <ul {...props} />,
  ol: ({ node, ...props }) => <ol {...props} />,
  li: ({ node, children, ...props }) => {
    let isCheckbox = false;
    let isChecked = false;

    const cleanChildren = React.Children.map(children, (child) => {
      if (
        React.isValidElement(child) &&
        child.type === 'input' &&
        (child.props as CheckboxInputProps).type === 'checkbox'
      ) {
        isCheckbox = true;
        isChecked = !!(child.props as CheckboxInputProps).checked;
        return null;
      }
      return child;
    });

    if (isCheckbox) {
      return (
        <li className="task-list-item" {...props}>
          <input type="checkbox" checked={isChecked} readOnly />
          <span style={isChecked ? { textDecoration: 'line-through', opacity: 0.65 } : undefined}>
            {cleanChildren}
          </span>
        </li>
      );
    }
    return <li {...props}>{children}</li>;
  },
  blockquote: ({ node, children, ...props }) => {
    const contentText = getTextContent(children);
    const match = contentText.match(/\[!(NOTE|IMPORTANT|WARNING|TIP|CAUTION)\]/);

    if (!match) {
      return <blockquote {...props}>{children}</blockquote>;
    }

    const alertType = match[1].toLowerCase();
    const alertClass = `alert-${alertType}`;
    const cleanChildren = cleanAlertPrefix(children);

    return (
      <blockquote className={alertClass} {...props}>
        <div className="alert-label">{match[1]}</div>
        <div>{cleanChildren}</div>
      </blockquote>
    );
  },
  table: ({ node, ...props }) => (
    <div className="table-wrapper">
      <table {...props} />
    </div>
  ),
  th: ({ node, ...props }) => <th {...props} />,
  td: ({ node, ...props }) => <td {...props} />,
  code: ({ node, ...props }) => <code {...props} />,
  pre: ({ node, children, ...props }) => {
    const codeChild = React.Children.toArray(children).find(isMarkdownCodeElement);
    if (!codeChild) {
      return <pre {...props}>{children}</pre>;
    }

    const language = extractLanguage(codeChild.props.className);
    const codeText = getCodeBlockText(codeChild.props.children);
    return renderCodeBlockFrame(
      language,
      codeText,
      <pre {...props}>
        <code {...codeChild.props}>{codeChild.props.children}</code>
      </pre>,
    );
  },
  hr: ({ node, ...props }) => <hr {...props} />,
  img: ({ node, ...props }) => <img {...props} />,
  dl: ({ node, ...props }) => <dl {...props} />,
  dt: ({ node, ...props }) => <dt {...props} />,
  dd: ({ node, ...props }) => <dd {...props} />,
};

function MermaidDiagram({ code, renderDiagram }: { code: string; renderDiagram: (code: string) => Promise<string> }) {
  const [svg, setSvg] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    renderDiagram(code).then((result) => {
      setSvg(result);
      setLoading(false);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to render diagram');
      setLoading(false);
    });
  }, [code, renderDiagram]);

  if (loading) {
    return <div className="mermaid-container">Loading diagram...</div>;
  }

  if (error) {
    return <div className="mermaid-container mermaid-error">Diagram error: {error}</div>;
  }

  return (
    <div className="mermaid-container" dangerouslySetInnerHTML={{ __html: svg }} />
  );
}

function HighlightedCodeBlock({ code, language, highlight }: { code: string; language: string; highlight: (code: string, language: string) => Promise<string> }) {
  const [highlightedCode, setHighlightedCode] = useState<string>(code);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    highlight(code, language).then((result) => {
      setHighlightedCode(result);
      setLoading(false);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to highlight code');
      setLoading(false);
    });
  }, [code, language, highlight]);

  if (error) {
    return renderCodeBlockFrame(
      language,
      code,
      <pre>
        <code>{code}</code>
      </pre>,
    );
  }

  return renderCodeBlockFrame(
    language,
    code,
    <pre>
      <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
    </pre>,
  );
}

function renderEnhancedCodeBlock(
  codeChild: React.ReactElement<MarkdownCodeElementProps>,
  options: {
    enableMermaid: boolean;
    enableSyntaxHighlight: boolean;
    highlight: (code: string, language: string) => Promise<string>;
    renderDiagram: (code: string) => Promise<string>;
  },
  preProps: React.HTMLAttributes<HTMLPreElement>,
) {
  const language = extractLanguage(codeChild.props.className);
  const codeText = getCodeBlockText(codeChild.props.children);

  if (options.enableMermaid && language === 'mermaid') {
    return <MermaidDiagram code={codeText} renderDiagram={options.renderDiagram} />;
  }

  if (options.enableSyntaxHighlight && language) {
    return <HighlightedCodeBlock code={codeText} language={language} highlight={options.highlight} />;
  }

  return renderCodeBlockFrame(
    language,
    codeText,
    <pre {...preProps}>
      <code {...codeChild.props}>{codeChild.props.children}</code>
    </pre>,
  );
}

export function MarkdownRenderer({
  content,
  className = '',
  variant = 'default',
  enableSyntaxHighlight = false,
  enableMath = false,
  enableMermaid = false,
}: MarkdownRendererProps) {
  const { highlight } = usePrism(enableSyntaxHighlight);
  const { isLoaded: isMathJaxLoaded } = useMathJax(enableMath);
  const { renderDiagram } = useMermaid(enableMermaid);

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (enableMath && isMathJaxLoaded && containerRef.current) {
      const MathJax = (window as any).MathJax;
      if (MathJax && MathJax.typesetPromise) {
        MathJax.typesetPromise([containerRef.current]).catch((err: any) => {
          console.warn('MathJax typeset failed', err);
        });
      }
    }
  }, [content, enableMath, isMathJaxLoaded]);

  const enhancedComponents: Components = {
    ...markdownComponents,
    pre: ({ node, children, ...props }) => {
      const codeChild = React.Children.toArray(children).find(isMarkdownCodeElement);
      if (!codeChild) {
        return <pre {...props}>{children}</pre>;
      }

      return renderEnhancedCodeBlock(
        codeChild,
        { enableMermaid, enableSyntaxHighlight, highlight, renderDiagram },
        props,
      );
    },
  };

  const variantClass = variant !== 'default' ? variant : '';

  return (
    <div ref={containerRef} className={`markdown-renderer ${variantClass} ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={enhancedComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
