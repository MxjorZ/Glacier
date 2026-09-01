import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Select = SelectPrimitive.Root;
export const SelectGroup = SelectPrimitive.Group;
export const SelectValue = SelectPrimitive.Value;

export function SelectTrigger({ className, size = 'default', children, ...props }) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      data-size={size}
      className={cn(
        "glass-surface flex w-fit items-center justify-between gap-2 rounded-xl px-3 py-2 text-sm whitespace-nowrap transition-all outline-none",
        "hover:border-primary/40 focus-visible:border-primary/60 focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--primary)_25%,transparent)]",
        "disabled:cursor-not-allowed disabled:opacity-50 data-[size=default]:h-9 data-[size=sm]:h-8",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg]:transition-transform",
        "group-data-[state=open]/trigger:[&_svg]:rotate-180",
        "data-placeholder:text-muted-foreground [&_svg:not([class*='text-'])]:text-muted-foreground",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDownIcon className="size-4 opacity-70 transition-transform duration-300 [[data-state=open]>&]:rotate-180" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({ className, children, position = 'popper', align = 'center', ...props }) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        className={cn(
          'glass-surface-strong z-50 max-h-[var(--radix-select-content-available-height)] min-w-32 overflow-x-hidden overflow-y-auto rounded-xl',
          'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2',
          'relative origin-[var(--radix-select-content-transform-origin)]',
          position === 'popper' && 'data-[side=bottom]:translate-y-1.5 data-[side=left]:-translate-x-1.5 data-[side=right]:translate-x-1.5 data-[side=top]:-translate-y-1.5',
          className,
        )}
        position={position}
        align={align}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport
          className={cn('p-1.5', position === 'popper' && 'h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)] scroll-my-1')}
        >
          {children}
        </SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectLabel({ className, ...props }) {
  return <SelectPrimitive.Label data-slot="select-label" className={cn('text-muted-foreground px-2 py-1.5 text-xs font-medium uppercase tracking-wide', className)} {...props} />;
}

export function SelectItem({ className, children, ...props }) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "group relative flex w-full cursor-default items-center gap-2.5 rounded-lg py-2 pl-3 pr-9 text-sm outline-none select-none",
        "transition-all data-highlighted:bg-primary/15 data-highlighted:text-primary data-highlighted:translate-x-0.5",
        "data-disabled:pointer-events-none data-disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        '[&_svg:not([class*="text-"])]:text-muted-foreground group-data-[highlighted]:[&_svg]:scale-110 group-data-[highlighted]:[&_svg]:text-primary',
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <span className="absolute right-2.5 flex size-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <CheckIcon className="size-4 text-primary animate-in zoom-in-50 duration-200" />
        </SelectPrimitive.ItemIndicator>
      </span>
    </SelectPrimitive.Item>
  );
}

export function SelectSeparator({ className, ...props }) {
  return <SelectPrimitive.Separator data-slot="select-separator" className={cn('pointer-events-none -mx-1.5 my-1 h-px bg-white/10', className)} {...props} />;
}

function SelectScrollUpButton({ className, ...props }) {
  return (
    <SelectPrimitive.ScrollUpButton data-slot="select-scroll-up-button" className={cn('flex cursor-pointer items-center justify-center py-1', className)} {...props}>
      <ChevronUpIcon className="size-3.5 text-muted-foreground" />
    </SelectPrimitive.ScrollUpButton>
  );
}
function SelectScrollDownButton({ className, ...props }) {
  return (
    <SelectPrimitive.ScrollDownButton data-slot="select-scroll-down-button" className={cn('flex cursor-pointer items-center justify-center py-1', className)} {...props}>
      <ChevronDownIcon className="size-3.5 text-muted-foreground" />
    </SelectPrimitive.ScrollDownButton>
  );
}
