import { useState } from 'react';
import {
  FolderTree, Copy, ShieldAlert, UserCheck, Trash2, FolderPlus,
  Music2, Tag, Mic, FileSearch, LayoutGrid,
} from 'lucide-react';
import { PageHeader } from '../components/PageHeader.jsx';
import Organize from './tools/Organize.jsx';
import Duplicates from './tools/Duplicates.jsx';
import Exclusivity from './tools/Exclusivity.jsx';
import Cleanup from './tools/Cleanup.jsx';
import ImportFolder from './tools/ImportFolder.jsx';
import GenreManager from './tools/GenreManager.jsx';
import TagsManager from './tools/TagsManager.jsx';
import AudioQualityAnalyzer from './tools/AudioQualityAnalyzer.jsx';
import FileManager from './tools/FileManager.jsx';

const TOOLS = [
  { id: 'organize', label: 'Organize', Icon: FolderTree, component: Organize },
  { id: 'duplicates', label: 'In-Library Duplicates', Icon: Copy, component: Duplicates },
  { id: 'exclusivity', label: 'Library / Artist Exclusivity', Icon: ShieldAlert, component: Exclusivity },
  { id: 'cleanup', label: 'Cleanup', Icon: Trash2, component: Cleanup },
  { id: 'import', label: 'Import Folder', Icon: FolderPlus, component: ImportFolder },
  { id: 'genres', label: 'Genre Manager', Icon: Music2, component: GenreManager },
  { id: 'tags', label: 'Tags Manager', Icon: Tag, component: TagsManager },
  { id: 'audioquality', label: 'Audio Quality Analyzer', Icon: Mic, component: AudioQualityAnalyzer },
  { id: 'filemanager', label: 'File Manager', Icon: FileSearch, component: FileManager },
];

export default function Tools() {
  const [selectedTool, setSelectedTool] = useState(null);

  if (selectedTool) {
    const tool = TOOLS.find((t) => t.id === selectedTool);
    if (!tool) return null;
    const Component = tool.component;
    return (
      <div>
        <button
          onClick={() => setSelectedTool(null)}
          className="back-button mb-4 flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          ← Back to Tools
        </button>
        <Component />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Tools"
        description="All music management utilities in one place."
      />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {TOOLS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setSelectedTool(id)}
            className="tool-card flex flex-col items-center justify-center rounded-xl border bg-card p-6 transition hover:bg-accent hover:shadow-md"
          >
            <Icon className="tool-icon size-12 text-primary" strokeWidth={1.5} />
            <span className="tool-label mt-3 text-center text-sm font-medium">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}