import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps extends HTMLMotionProps<"button"> {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
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
    <motion.button 
      className={classes} 
      disabled={disabled || loading} 
      whileHover={disabled || loading ? undefined : { scale: 1.02, boxShadow: '0 8px 24px oklch(82% 0.08 60 / 0.4)' }}
      whileTap={disabled || loading ? undefined : { scale: 0.98 }}
      {...(buttonProps as any)}
    >
      {icon ? (
        <span className="button-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <span>{loading ? '处理中' : children}</span>
    </motion.button>
  );
}
