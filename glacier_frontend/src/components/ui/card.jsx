import * as React from 'react';
import { cn } from '@/lib/utils';

// Liquid-glass card. The glass material (tint + blur + border) lives on an
// absolutely-positioned backdrop layer so the user's transparency setting can
// never bleed into the text/content — children always render at full opacity.
export function Card({ className, ...props }) {
  return (
    <div
      data-slot="card"
      className={cn(
        'glass-card relative flex flex-col gap-6 py-6 text-card-foreground',
        className,
      )}
      {...props}
    >
      {props.children}
    </div>
  );
}

export function CardHeader({ className, ...props }) {
  return <div data-slot="card-header" className={cn('grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6', className)} {...props} />;
}
export function CardTitle({ className, ...props }) {
  return <div data-slot="card-title" className={cn('leading-none font-semibold', className)} {...props} />;
}
export function CardDescription({ className, ...props }) {
  return <div data-slot="card-description" className={cn('text-muted-foreground text-sm', className)} {...props} />;
}
export function CardAction({ className, ...props }) {
  return <div data-slot="card-action" className={cn('col-start-2 row-span-2 row-start-1 self-start justify-self-end', className)} {...props} />;
}
export function CardContent({ className, ...props }) {
  return <div data-slot="card-content" className={cn('relative z-10 px-6', className)} {...props} />;
}
export function CardFooter({ className, ...props }) {
  return <div data-slot="card-footer" className={cn('flex items-center px-6 [.border-t]:pt-6', className)} {...props} />;
}
