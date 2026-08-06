import { useState, useEffect } from 'react';
import { FolderPlus, RefreshCw } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { toast } from '../../toast.jsx';

export default function ImportFolder() {
  const [libs, setLibs] = useState([]);
  const { running, run } = useJob();
  const [importSource, setImportSource] = useState('');
  const [importDestLib, setImportDestLib] = useState('');
  const [importPreserve, setImportPreserve] = useState(true);
  const [importMove, setImportMove] = useState(true);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setImportDestLib(l[0].id);
    }).catch(() => {});
  }, []);

  const runImport = async () => {
    const res = await run('import-folder', {
      source_path: importSource,
      dest_library_id: importDestLib,
      preserve_structure: importPreserve,
      move: importMove,
    });
    if (res?.ok) {
      toast.success(`Imported ${res.moved} files, ${res.errors?.length || 0} errors`);
      setImportSource('');
    } else {
      toast.error(res?.error || 'Import failed');
    }
  };

  return (
    <div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FolderPlus className="size-4 text-primary" /> Import folder</CardTitle>
          <CardDescription>Move or copy all audio files from a source folder into a library</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Source folder</label>
            <Input
              value={importSource}
              onChange={(e) => setImportSource(e.target.value)}
              placeholder="C:\Downloads\New Music"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Destination library</label>
            <Select value={importDestLib} onValueChange={setImportDestLib}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Select a library" /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={importPreserve} onChange={(e) => setImportPreserve(e.target.checked)} />
              Preserve folder structure
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={importMove} onChange={(e) => setImportMove(e.target.checked)} />
              Move (instead of copy)
            </label>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={running || !importSource || !importDestLib} onClick={runImport}>
              <RefreshCw className="size-3.5" /> Import
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}