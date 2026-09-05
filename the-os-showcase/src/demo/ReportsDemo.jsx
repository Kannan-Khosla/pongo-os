import { Download, FileBarChart, PackageCheck, ScanLine, TrendingDown, Truck, WalletCards } from 'lucide-react';
import { useState } from 'react';
import { reports } from '../mock-data/data.js';

const reportMeta = [
  ['valuation', WalletCards], ['lowStock', TrendingDown], ['movements', ScanLine], ['skuOrders', FileBarChart], ['receiving', Truck], ['fulfillment', PackageCheck],
];

function BarChart({ values, label }) {
  const max = Math.max(...values);
  return <div className="bar-chart" role="img" aria-label={`${label}: ${values.join(', ')}`}><div className="bar-chart__plot">{values.map((value, index) => <i key={`${value}-${index}`} style={{ height: `${(value / max) * 100}%` }} />)}</div><div className="chart-axis" aria-hidden="true"><span>Fri</span><span>Sat</span><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span></div></div>;
}

export default function ReportsDemo() {
  const [reportId, setReportId] = useState('valuation');
  const [message, setMessage] = useState('Choose a report to update the workspace.');
  const report = reports[reportId];
  return (
    <section className="demo-view reports-demo" aria-labelledby="reports-title">
      <header className="demo-heading"><div><span>Operational reporting</span><h3 id="reports-title">From movement history to executive visibility</h3><p>Focused reports with useful filters, lightweight charts, and export-ready rows.</p></div><button className="soft-button" type="button" onClick={() => setMessage(`${report.label} sample prepared for CSV export.`)}><Download size={15} />Export sample</button></header>
      <div className="reports-layout">
        <nav className="report-menu" aria-label="Report library">{reportMeta.map(([id, Icon]) => <button type="button" className={reportId === id ? 'active' : ''} aria-current={reportId === id ? 'page' : undefined} key={id} onClick={() => { setReportId(id); setMessage(`${reports[id].label} loaded.`); }}><Icon size={17} /><span>{reports[id].label}</span></button>)}</nav>
        <article className="demo-card report-workspace">
          <div className="report-workspace__heading"><div><span className="drawer-kicker">August 7–13, 2026</span><h4>{report.label}</h4></div><span className="quiet-label">Synthetic data</span></div>
          <div className="report-metrics">{report.metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
          <BarChart values={report.chart} label={report.label} />
          <div className="report-table" role="table" aria-label={`${report.label} summary`}><div role="row"><b role="columnheader">Dimension</b><b role="columnheader">Value</b><b role="columnheader">Share / context</b></div>{report.rows.map((row) => <div role="row" key={row[0]}>{row.map((cell) => <span role="cell" key={cell}>{cell}</span>)}</div>)}</div>
        </article>
      </div>
      <div className="demo-status" role="status" aria-live="polite"><span>6 implemented report families represented</span><span>{message}</span></div>
    </section>
  );
}
