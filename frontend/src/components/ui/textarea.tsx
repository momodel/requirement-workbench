import * as React from 'react';

import { cn } from '../../lib/utils';

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<'textarea'>
>(({ className, ...props }, ref) => {
  return (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-[112px] w-full rounded-[16px] border border-borderWarm bg-ivory px-4 py-3 text-[15px] leading-[1.6] text-nearBlack outline-none transition-[border-color,box-shadow] placeholder:text-stone focus-visible:border-focusBlue focus-visible:ring-2 focus-visible:ring-focusBlue/30',
        className
      )}
      {...props}
    />
  );
});

Textarea.displayName = 'Textarea';
