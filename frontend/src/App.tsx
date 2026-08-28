import React, { useEffect, useState, useCallback } from 'react';
import './App.css';

interface SectorInfo {
  name: string;
  columns: string[];
}

interface SchemaData {
  status: string;
  source: string | null;
  rows: number;
  columns: number;
  sectors: SectorInfo[];
  extra_columns: string[];
}

interface PreviewData {
  columns: string[];
  data: Record<string, any>[];
  tables: string[];
  total_rows: number;
  selected_columns_count: number;
}

export default function App() {
  const [schema, setSchema] = useState<SchemaData | null>(null);
  const [schemaError, setSchemaError] = useState<string>("");
  const [selectedSectors, setSelectedSectors] = useState<Set<string>>(new Set());
  const [sectorColumns, setSectorColumns] = useState<Record<string, string[]>>({});
  const [extraSelected, setExtraSelected] = useState<string[]>([]);
  const [includeKeys, setIncludeKeys] = useState<boolean>(true);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [previewView, setPreviewView] = useState<string>("Combined");
  const [exportFormat, setExportFormat] = useState<string>("excel_workbook");
  const [loading, setLoading] = useState<boolean>(false);
  const [etlRunning, setEtlRunning] = useState<boolean>(false);
  const [etlLog, setEtlLog] = useState<string>("");
  const [downloadUrl, setDownloadUrl] = useState<string>("");
  const [exportMsg, setExportMsg] = useState<string>("");

  useEffect(() => {
    fetch('/api/schema')
      .then(r => r.json())
      .then(data => {
        if (data.error) { setSchemaError(data.error); return; }
        setSchema(data);
        const defaults = data.sectors.filter((s: SectorInfo) =>
          s.name !== 'Geographic' && s.name !== 'Calculated Metrics'
        );
        setSelectedSectors(new Set(defaults.map((s: SectorInfo) => s.name)));
        const bySector: Record<string, string[]> = {};
        defaults.forEach((s: SectorInfo) => { bySector[s.name] = [...s.columns]; });
        setSectorColumns(bySector);
      })
      .catch(err => setSchemaError(String(err)));
  }, []);

  const buildPayload = useCallback(() => {
    const sector_columns: Record<string, string[]> = {};
    selectedSectors.forEach(name => {
      const cols = sectorColumns[name];
      if (cols && cols.length) sector_columns[name] = cols;
    });
    if (extraSelected.length) sector_columns.__extra__ = extraSelected;
    return { sector_columns, include_keys: includeKeys };
  }, [selectedSectors, sectorColumns, extraSelected, includeKeys]);

  useEffect(() => {
    if (!schema || !schema.source) return;
    const payload = buildPayload();
    const hasAny = Object.values(payload.sector_columns || {}).some((c) => (c as string[]).length > 0);
    if (!hasAny) { setPreview(null); return; }
    setLoading(true);
    fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(r => r.json())
      .then(setPreview)
      .catch(err => setExportMsg('Preview error: ' + err))
      .finally(() => setLoading(false));
  }, [schema, buildPayload]);

  const toggleSector = (name: string) => {
    setSelectedSectors(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
        setSectorColumns(sc => {
          const copy = { ...sc };
          delete copy[name];
          return copy;
        });
      } else {
        next.add(name);
        if (schema) {
          const s = schema.sectors.find(x => x.name === name);
          if (s) setSectorColumns(sc => ({ ...sc, [name]: [...s.columns] }));
        }
      }
      return next;
    });
  };

  const toggleColumn = (sector: string, col: string) => {
    setSectorColumns(prev => {
      const current = prev[sector] || [];
      const has = current.includes(col);
      return { ...prev, [sector]: has ? current.filter(c => c !== col) : [...current, col] };
    });
  };

  const toggleSectorAll = (sector: string) => {
    if (!schema) return;
    const all = schema.sectors.find(s => s.name === sector)?.columns || [];
    setSectorColumns(prev => {
      const current = prev[sector] || [];
      const allPicked = all.length > 0 && all.every(c => current.includes(c));
      return { ...prev, [sector]: allPicked ? [] : [...all] };
    });
  };

  const toggleExtra = (col: string) => {
    setExtraSelected(prev => prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]);
  };

  const runEtl = () => {
    setEtlRunning(true);
    setEtlLog("Running pipeline...");
    fetch('/api/run-etl', { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        setEtlLog(d.log || "Done.");
        if (d.success) window.location.reload();
      })
      .catch(e => setEtlLog("ETL failed: " + e.message))
      .finally(() => setEtlRunning(false));
  };

  const handleExport = () => {
    setExportMsg("");
    fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...buildPayload(), format: exportFormat })
    })
      .then(r => r.json())
      .then(d => {
        if (d.success && d.download_url) { setDownloadUrl(d.download_url); setExportMsg('Export ready.'); }
        else setExportMsg(d.error || 'Export failed.');
      })
      .catch(() => setExportMsg('Export failed.'));
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Delaware ZCTA Health · Sector Exporter</h1>
        <p>Pick a dataset, choose sectors &amp; columns, then export clean per-sector files (or one multi-sheet workbook) without cluttering your workspace.</p>
      </header>

      <div className="main-content">
        <aside className="sidebar">
          <h2>1 · Data source</h2>
          {schemaError && <p className="error-text">{schemaError}</p>}
          <div className="status-box">
            <p><strong>Active Dataset:</strong> {schema?.source || "None found"}</p>
            <p><strong>Total ZCTAs:</strong> {schema?.rows || 0}</p>
            <p><strong>Total Columns:</strong> {schema?.columns || 0}</p>
          </div>
          <button className="btn btn-primary" onClick={runEtl} disabled={etlRunning}>
            {etlRunning ? "Running Pipeline..." : "Run ETL & Refresh Data"}
          </button>
          {etlLog && <div className="etl-log"><pre>{etlLog}</pre></div>}
          <hr />
          <label className="checkbox-label toggle-inline">
            <input type="checkbox" checked={includeKeys} onChange={e => setIncludeKeys(e.target.checked)} />
            Include geographic keys (ZCTA · County_FIPS · County_Name)
          </label>
        </aside>

        <main className="content-area">
          <section className="card">
            <h2>2 · Pick sectors &amp; columns</h2>

            <h3 className="sub-heading">Sectors to include</h3>
            {!schema ? <p>Loading sectors...</p> : (
              <div className="sector-chip-list">
                {schema.sectors.map(s => (
                  <label key={s.name} className={`chip ${selectedSectors.has(s.name) ? 'chip-on' : ''}`}>
                    <input
                      type="checkbox"
                      checked={selectedSectors.has(s.name)}
                      onChange={() => toggleSector(s.name)}
                    />
                    {s.name}
                  </label>
                ))}
              </div>
            )}

            {schema && selectedSectors.size > 0 && (
              <>
                <h3 className="sub-heading">Refine columns per sector</h3>
                {schema.sectors.filter(s => selectedSectors.has(s.name)).map(s => {
                  const picked = sectorColumns[s.name] || [];
                  const allPicked = s.columns.length > 0 && s.columns.every(c => picked.includes(c));
                  return (
                    <div className="sector-block" key={s.name}>
                      <div className="sector-block-header">
                        <strong>{s.name}</strong>
                        <span className="sector-block-count">{picked.length} of {s.columns.length} selected</span>
                        <button className="link-btn" onClick={() => toggleSectorAll(s.name)}>
                          {allPicked ? 'Clear' : 'Select all'}
                        </button>
                      </div>
                      <div className="col-check-list">
                        {s.columns.map(col => (
                          <label key={col} className="checkbox-label">
                            <input
                              type="checkbox"
                              checked={picked.includes(col)}
                              onChange={() => toggleColumn(s.name, col)}
                            />
                            {col}
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </>
            )}

            {schema && schema.extra_columns.length > 0 && (
              <>
                <h3 className="sub-heading">Other columns in this dataset</h3>
                <div className="col-check-list">
                  {schema.extra_columns.map(col => (
                    <label key={col} className="checkbox-label">
                      <input type="checkbox" checked={extraSelected.includes(col)} onChange={() => toggleExtra(col)} />
                      {col}
                    </label>
                  ))}
                </div>
              </>
            )}
          </section>
<section className="card">
            <h2>3 · Preview</h2>
            {loading ? <p>Loading preview...</p> : preview?.data ? (
              <div>
                <label className="preview-select">
                  Preview table:
                  <select value={previewView} onChange={e => setPreviewView(e.target.value)}>
                    <option value="Combined">Combined</option>
                    {(preview.tables || []).map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
                <p className="preview-meta">
                  {preview.tables.length} sector tables · {preview.selected_columns_count} selected columns · {preview.total_rows} ZCTA rows
                </p>
                <div className="table-responsive">
                  <table>
                    <thead>
                      <tr>{preview.columns.map((col: string) => <th key={col}>{col}</th>)}</tr>
                    </thead>
                    <tbody>
                      {preview.data.map((row: any, idx: number) => (
                        <tr key={idx}>
                          {preview.columns.map((col: string) => <td key={col}>{String(row[col] ?? "")}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : <p>Select at least one sector or column to preview.</p>}
          </section>

          <section className="card">
            <h2>4 · Export</h2>
            <div className="export-options">
              <label className="radio-label"><input type="radio" name="fmt" checked={exportFormat === "excel_workbook"} onChange={() => setExportFormat("excel_workbook")} /> One Excel workbook (one sheet per sector)</label>
              <label className="radio-label"><input type="radio" name="fmt" checked={exportFormat === "csv_separate"} onChange={() => setExportFormat("csv_separate")} /> Separate CSV files (ZIP)</label>
              <label className="radio-label"><input type="radio" name="fmt" checked={exportFormat === "excel_separate"} onChange={() => setExportFormat("excel_separate")} /> Separate Excel files (ZIP)</label>
              <label className="radio-label"><input type="radio" name="fmt" checked={exportFormat === "combined_csv"} onChange={() => setExportFormat("combined_csv")} /> One combined CSV</label>
              <label className="radio-label"><input type="radio" name="fmt" checked={exportFormat === "combined_excel"} onChange={() => setExportFormat("combined_excel")} /> One combined Excel</label>
            </div>
            <button className="btn btn-success" onClick={handleExport}>Export Data</button>
            {exportMsg && <p className="export-msg">{exportMsg}</p>}
            {downloadUrl && (
              <div className="download-box">
                <a href={downloadUrl} className="btn-download" target="_blank" rel="noreferrer">Download Exported File</a>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}