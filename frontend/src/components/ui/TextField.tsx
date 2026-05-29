import type { InputHTMLAttributes } from 'react';

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  helperText?: string;
}

export function TextField({ label, helperText, id, ...inputProps }: TextFieldProps) {
  const inputId = id ?? inputProps.name;
  const helperId = helperText && inputId ? `${inputId}-helper` : undefined;

  return (
    <div className="text-field">
      <label className="text-field-label" htmlFor={inputId}>
        {label}
      </label>
      <input id={inputId} aria-describedby={helperId} {...inputProps} />
      {helperText ? (
        <span className="text-field-helper" id={helperId}>
          {helperText}
        </span>
      ) : null}
    </div>
  );
}
