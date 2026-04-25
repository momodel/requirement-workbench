import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from '@radix-ui/react-slot';

import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 rounded-[10px] text-sm font-medium tracking-tightish transition-[background-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focusBlue/60 focus-visible:ring-offset-2 focus-visible:ring-offset-parchment disabled:pointer-events-none disabled:opacity-55 active:scale-[0.99]',
  {
    variants: {
      variant: {
        default:
          'bg-terracotta text-ivory shadow-ringTerracotta hover:bg-[#b95a39] hover:shadow-[0_0_0_1px_#b95a39,0_8px_24px_-12px_rgba(201,100,66,0.55)]',
        secondary:
          'bg-sand text-charcoal shadow-ringWarm hover:bg-[#dcd9cd] hover:shadow-ringDeep',
        ghost:
          'bg-transparent text-charcoal hover:bg-sand/70 hover:text-nearBlack',
        subtle:
          'bg-accentSoft text-terracotta shadow-[0_0_0_1px_rgba(201,100,66,0.18)] hover:bg-[#eed4c2] hover:text-[#a14e30]',
        outline:
          'bg-ivory text-nearBlack shadow-ringWarm hover:bg-sand/70',
        dark:
          'bg-warmDark text-ivory shadow-ringDark hover:bg-[#3a3a37]',
        danger:
          'bg-errorWarm text-ivory shadow-[0_0_0_1px_#9a2a2a] hover:bg-[#9c2a2a]',
      },
      size: {
        default: 'h-9 px-3.5 py-2',
        sm: 'h-8 px-3 text-[13px]',
        lg: 'h-11 px-5 text-[15px]',
        icon: 'h-9 w-9 rounded-[10px]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
