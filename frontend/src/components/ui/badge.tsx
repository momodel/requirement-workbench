import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-[3px] text-[11px] font-medium tracking-[0.01em]',
  {
    variants: {
      variant: {
        default: 'border-borderWarm bg-ivory text-olive',
        accent: 'border-transparent bg-accentSoft text-terracotta',
        success: 'border-transparent bg-[#e1ecdf] text-[#3f7a5b]',
        warning: 'border-transparent bg-[#f3e7d1] text-[#8a5a1d]',
        danger: 'border-transparent bg-[#f3d8d4] text-errorWarm',
        outline: 'border-borderWarm bg-transparent text-charcoal',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
