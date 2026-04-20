import * as React from 'react';

import { cn } from '../../lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'flex h-10 w-full rounded-2xl border border-line bg-white px-4 py-2 text-sm text-ink outline-none ring-offset-white placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-accent',
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';
