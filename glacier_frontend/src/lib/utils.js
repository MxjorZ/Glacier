import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

// shadcn-style className merge (from SpotiFLAC's lib/utils.ts).
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
