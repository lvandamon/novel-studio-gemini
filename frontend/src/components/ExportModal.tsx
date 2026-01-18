import React, { useState } from 'react';
import { api } from '../api';
import { Book, Download, FileText } from 'lucide-react';

interface ExportModalProps {
  currentChapter: number;
  onClose: () => void;
}

const ExportModal: React.FC<ExportModalProps> = ({ currentChapter, onClose }) => {
  const [range, setRange] = useState({ start: 1, end: currentChapter });
  const [loading, setLoading] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");

  const handleExport = async (format: 'txt' | 'epub') => {
    setLoading(true);
    try {
      const res = await api.generateExport(range.start, range.end, format);
      // Determine full URL
      const fullUrl = `http://localhost:8000${res.download_url}`;
      setDownloadUrl(fullUrl);
      // Auto trigger?
      window.open(fullUrl, '_blank');
    } catch (e) {
      alert("Export failed: " + e);
    }
    setLoading(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        <div className="p-6 bg-gray-50 border-b border-gray-100 flex items-center gap-3">
           <div className="bg-green-100 p-2 rounded text-green-600">
             <Download size={24} />
           </div>
           <div>
             <h2 className="text-xl font-bold text-gray-900">Publishing Center</h2>
             <p className="text-xs text-gray-500 uppercase font-bold tracking-wider">Compile & Export Novel</p>
           </div>
        </div>

        <div className="p-6 space-y-6">
          
          {downloadUrl ? (
             <div className="text-center space-y-4">
                <div className="text-green-600 font-bold text-lg">Export Ready!</div>
                <p className="text-sm text-gray-500">If the download didn't start automatically, click below:</p>
                <a href={downloadUrl} target="_blank" className="inline-block bg-green-600 text-white px-6 py-2 rounded font-bold hover:bg-green-700">Download File</a>
                <button onClick={() => setDownloadUrl("")} className="block w-full text-xs text-gray-400 mt-4 hover:underline">Export Another</button>
             </div>
          ) : (
            <>
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-500 uppercase">Chapter Range</label>
            <div className="flex items-center gap-3">
               <div className="relative flex-1">
                 <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs font-bold">START</span>
                 <input 
                   type="number" 
                   value={range.start}
                   onChange={(e) => setRange(prev => ({ ...prev, start: parseInt(e.target.value) || 1 }))}
                   className="w-full pl-12 p-2 border rounded font-mono text-sm"
                 />
               </div>
               <span className="text-gray-400 font-bold">-</span>
               <div className="relative flex-1">
                 <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs font-bold">END</span>
                 <input 
                   type="number" 
                   value={range.end}
                   onChange={(e) => setRange(prev => ({ ...prev, end: parseInt(e.target.value) || 1 }))}
                   className="w-full pl-10 p-2 border rounded font-mono text-sm"
                 />
               </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
             <button 
               onClick={() => handleExport('epub')}
               disabled={loading}
               className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 rounded-xl hover:border-green-500 hover:bg-green-50 transition-all group"
             >
               <Book size={32} className="text-gray-400 group-hover:text-green-600 mb-2" />
               <span className="font-bold text-gray-700 group-hover:text-green-800">EPUB E-Book</span>
               <span className="text-xs text-gray-400">For Readers</span>
             </button>

             <button 
               onClick={() => handleExport('txt')}
               disabled={loading}
               className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 rounded-xl hover:border-blue-500 hover:bg-blue-50 transition-all group"
             >
               <FileText size={32} className="text-gray-400 group-hover:text-blue-600 mb-2" />
               <span className="font-bold text-gray-700 group-hover:text-blue-800">Clean TXT</span>
               <span className="text-xs text-gray-400">For Platforms</span>
             </button>
          </div>

          {loading && (
            <div className="text-center text-sm text-gray-500 animate-pulse">
               Compiling...
            </div>
          )}
            </>
          )}
        </div>

        <div className="p-4 bg-gray-50 text-right">
           <button onClick={onClose} className="text-sm font-bold text-gray-500 hover:text-gray-800">Close</button>
        </div>
      </div>
    </div>
  );
};

export default ExportModal;
