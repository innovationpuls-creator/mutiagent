import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { usePrism } from './hooks/usePrism';
import { useMathJax } from './hooks/useMathJax';
import { useMermaid } from './hooks/useMermaid';
import { extractLanguage } from './utils/highlight';
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
  code: ({ node, className, children, ...props }) => {
    const inline = !className || !className.includes('language-');
    if (inline) {
      return <code {...props}>{children}</code>;
    }

    const match = /language-(\w+)/.exec(className || '');
    const lang = match ? match[1] : 'code';
    const codeString = String(children).replace(/\n$/, '');

    return (
      <div className="code-block">
        <div className="code-block-header">
          <span className="code-block-lang">{lang}</span>
          <button
            className="code-block-copy"
            aria-label="Copy code to clipboard"
            onClick={(e) => {
              const button = e.currentTarget;
              navigator.clipboard.writeText(codeString).then(() => {
                button.textContent = 'COPIED!';
                button.ariaLabel = 'Code copied';
                setTimeout(() => {
                  button.textContent = 'COPY';
                  button.ariaLabel = 'Copy code to clipboard';
                }, 2000);
              }).catch(() => {
                button.textContent = 'FAILED';
                button.ariaLabel = 'Failed to copy code';
                setTimeout(() => {
                  button.textContent = 'COPY';
                  button.ariaLabel = 'Copy code to clipboard';
                }, 2000);
              });
            }}
          >
            COPY
          </button>
        </div>
        <pre>
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      </div>
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

  useEffect(() => {
    renderDiagram(code).then((result) => {
      setSvg(result);
      setLoading(false);
    });
  }, [code, renderDiagram]);

  if (loading) {
    return <div className="mermaid-container">Loading diagram...</div>;
  }

  return (
    <div className="mermaid-container" dangerouslySetInnerHTML={{ __html: svg }} />
  );
}

function HighlightedCodeBlock({ code, language, highlight }: { code: string; language: string; highlight: (code: string, language: string) => Promise<string> }) {
  const [highlightedCode, setHighlightedCode] = useState<string>(code);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    highlight(code, language).then((result) => {
      setHighlightedCode(result);
      setLoading(false);
    });
  }, [code, language, highlight]);

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-lang">{language}</span>
        <button
          className="code-block-copy"
          onClick={(e) => {
            const button = e.currentTarget;
            navigator.clipboard.writeText(code).then(() => {
              button.textContent = 'COPIED!';
              setTimeout(() => {
                button.textContent = 'COPY';
              }, 2000);
            }).catch(() => {
              button.textContent = 'FAILED';
              setTimeout(() => {
                button.textContent = 'COPY';
              }, 2000);
            });
          }}
        >
          COPY
        </button>
      </div>
      <pre>
        <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
      </pre>
    </div>
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
  const { highlight } = usePrism();
  const { renderMath } = useMathJax();
  const { renderDiagram } = useMermaid();

  const enhancedComponents: Components = {
    ...markdownComponents,
    code: ({ node, className, children, ...props }) => {
      const inline = !className || !className.includes('language-');
      
      if (inline) {
        return <code {...props}>{children}</code>;
      }

      const lang = extractLanguage(className);
      const codeString = String(children).replace(/\n$/, '');

      if (enableMermaid && lang === 'mermaid') {
        return <MermaidDiagram code={codeString} renderDiagram={renderDiagram} />;
      }

      if (enableSyntaxHighlight && lang) {
        return <HighlightedCodeBlock code={codeString} language={lang} highlight={highlight} />;
      }

      return (
        <div className="code-block">
          <div className="code-block-header">
            <span className="code-block-lang">{lang || 'code'}</span>
            <button
              className="code-block-copy"
              onClick={(e) => {
                const button = e.currentTarget;
                navigator.clipboard.writeText(codeString).then(() => {
                  button.textContent = 'COPIED!';
                  button.ariaLabel = 'Code copied';
                  setTimeout(() => {
                    button.textContent = 'COPY';
                    button.ariaLabel = 'Copy code to clipboard';
                  }, 2000);
                }).catch(() => {
                  button.textContent = 'FAILED';
                  button.ariaLabel = 'Failed to copy code';
                  setTimeout(() => {
                    button.textContent = 'COPY';
                    button.ariaLabel = 'Copy code to clipboard';
                  }, 2000);
                });
              }}
            >
              COPY
            </button>
          </div>
          <pre>
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        </div>
      );
    },
  };

  const variantClass = variant !== 'default' ? variant : '';

  return (
    <div className={`markdown-renderer ${variantClass} ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={enhancedComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
