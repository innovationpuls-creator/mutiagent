import type { ButtonHTMLAttributes, ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = 'primary',
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...buttonProps
}: ButtonProps) {
  const classes = ['button', `button-${variant}`, className].filter(Boolean).join(' ');

  return (
    <button className={classes} disabled={disabled || loading} {...buttonProps}>
      {icon ? (
        <span className="button-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <span>{loading ? '处理中' : children}</span>
    </button>
  );
}
