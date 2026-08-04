import * as React from 'react';
import { cn } from '@/lib/utils';

export function Table({ className, ...props }) {
  return <div data-slot="table-container" className={cn('relative w-full overflow-auto', className)}><table data-slot="table" className="w-full caption-bottom text-sm" {...props} /></div>;
}
export function TableHeader({ className, ...props }) {
  return <thead data-slot="table-header" className={cn('[&_tr]:border-b', className)} {...props} />;
}
export function TableBody({ className, ...props }) {
  return <tbody data-slot="table-body" className={cn('[&_tr:last-child]:border-0', className)} {...props} />;
}
export function TableRow({ className, ...props }) {
  return <tr data-slot="table-row" className={cn('hover:bg-muted/50 data-[state=selected]:bg-muted border-b transition-colors', className)} {...props} />;
}
export function TableHead({ className, ...props }) {
  return <th data-slot="table-head" className={cn('text-muted-foreground h-10 px-3 text-left align-middle font-medium whitespace-nowrap [&:has([role=checkbox])]:pr-0', className)} {...props} />;
}
export function TableCell({ className, ...props }) {
  return <td data-slot="table-cell" className={cn('p-3 align-middle [&:has([role=checkbox])]:pr-0', className)} {...props} />;
}
