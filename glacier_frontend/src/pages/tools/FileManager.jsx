import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card.jsx';
import { FileSearch } from 'lucide-react';

export default function FileManager() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FileSearch className="size-4 text-primary" /> File Manager</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground">Coming soon – browse, move, rename, and delete files directly in your libraries.</p>
      </CardContent>
    </Card>
  );
}