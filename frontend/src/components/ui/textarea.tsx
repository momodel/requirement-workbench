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
        'flex min-h-[112px] w-full rounded-[24px] border border-line bg-white px-4 py-3 text-sm leading-6 text-ink outline-none ring-offset-white placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-accent',
        className
      )}
      {...props}
    />
  );
});

Textarea.displayName = 'Textarea';
