import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card.jsx';
import { Mic } from 'lucide-react';

export default function AudioQualityAnalyzer() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Mic className="size-4 text-primary" /> Audio Quality Analyzer</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground">Coming soon – analyze bitrate, sample rate, and codec quality across your library.</p>
      </CardContent>
    </Card>
  );
}