import * as React from 'react';

import { cn } from '../../lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          'flex h-10 w-full rounded-[12px] border border-borderWarm bg-ivory px-3.5 py-2 text-sm text-nearBlack outline-none transition-[border-color,box-shadow] placeholder:text-stone focus-visible:border-focusBlue focus-visible:ring-2 focus-visible:ring-focusBlue/30',
          className
        )}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';
