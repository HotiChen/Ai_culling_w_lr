// pv-ui.jsx — shared UI primitives + icon set for PhotoVault

// ── Icons (stroke, inherit currentColor) ─────────────────────────────
const _I = (p) => ({ width: p.s || 17, height: p.s || 17, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: p.w || 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' });
function Icon({ name, s, w, style }) {
  const a = _I({ s, w });
  const paths = {
    profile: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 13h4M8 16h7"/></>,
    cull: <><path d="M3 5h18l-7 8v6l-4-2v-4z"/></>,
    review: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    arbitrate: <><path d="M12 3v18M5 7l-2.5 6a3 3 0 0 0 5 0L5 7zM19 7l-2.5 6a3 3 0 0 0 5 0L19 7zM4 7h16M8 21h8"/></>,
    export: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 11v6c0 1.66 3.58 3 8 3M16 19l3 3 3-3M19 22v-7"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-2.82 1.17V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></>,
    catalog: <><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12l9 5 9-5M3 16l9 5 9-5"/></>,
    star: <path d="M12 3l2.7 5.5 6 .9-4.3 4.2 1 6L12 17l-5.4 2.8 1-6L3.3 9.4l6-.9z" fill="currentColor" stroke="none"/>,
    starO: <path d="M12 3l2.7 5.5 6 .9-4.3 4.2 1 6L12 17l-5.4 2.8 1-6L3.3 9.4l6-.9z"/>,
    check: <path d="M5 12l5 5L20 6"/>,
    x: <path d="M6 6l12 12M18 6L6 18"/>,
    sparkle: <><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="2.5"/></>,
    eyeOff: <><path d="M3 3l18 18M10.6 10.6a2.5 2.5 0 0 0 3.4 3.4M9.4 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a16 16 0 0 1-3.1 3.9M6.6 6.6A16 16 0 0 0 2 12s3.5 7 10 7a9.6 9.6 0 0 0 2.6-.4"/></>,
    focus: <><circle cx="12" cy="12" r="3"/><path d="M3 7V4h3M21 7V4h-3M3 17v3h3M21 17v3h-3"/></>,
    dup: <><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></>,
    chevron: <path d="M9 6l6 6-6 6"/>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/></>,
    layers: <><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12l9 5 9-5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    arrowRight: <path d="M5 12h14M13 6l6 6-6 6"/>,
  };
  return <svg {...a} style={style}>{paths[name]}</svg>;
}

// ── Stars (1–5) ──────────────────────────────────────────────────────
function Stars({ n, size = 13, onChange }) {
  return (
    <span className="stars" style={{ cursor: onChange ? 'pointer' : 'default' }}>
      {[1,2,3,4,5].map(i => (
        <svg key={i} className={'star ' + (i <= n ? 'f' : 'e')} viewBox="0 0 24 24"
             style={{ width: size, height: size }}
             onClick={onChange ? (e) => { e.stopPropagation(); onChange(i === n ? 0 : i); } : undefined}>
          <path d="M12 3l2.7 5.5 6 .9-4.3 4.2 1 6L12 17l-5.4 2.8 1-6L3.3 9.4l6-.9z" fill="currentColor"/>
        </svg>
      ))}
    </span>
  );
}

// ── Band badge ───────────────────────────────────────────────────────
const BAND_LABEL = { keep: ['留', 'KEEP'], maybe: ['待定', 'MAYBE'], reject: ['淘汰', 'REJECT'] };
function BandBadge({ band }) {
  const [zh, en] = BAND_LABEL[band] || ['', ''];
  return <span className={'badge ' + band}>{zh} · {en}</span>;
}

function Btn({ children, primary, ghost, sm, icon, onClick, disabled, style }) {
  const cls = ['btn', primary && 'primary', ghost && 'ghost', sm && 'sm'].filter(Boolean).join(' ');
  return (
    <button className={cls} onClick={onClick} disabled={disabled} style={style}>
      {icon && <Icon name={icon} s={sm ? 14 : 16} />}{children}
    </button>
  );
}

function Stat({ v, label, en, color }) {
  return (
    <div className="stat">
      <div className="stat-v" style={color ? { color } : null}>{v}</div>
      <div className="stat-l">{label} {en && <span>· {en}</span>}</div>
    </div>
  );
}

function DistBar({ k, v, max = 1 }) {
  return (
    <div className="dist-row">
      <div className="dist-k">{k}</div>
      <div className="dist-bar"><div className="dist-fill" style={{ width: (v / max * 100) + '%' }}></div></div>
      <div className="dist-v">{Math.round(v * 100)}%</div>
    </div>
  );
}

// ── Dropzone ─────────────────────────────────────────────────────────
function Dropzone({ icon, title, sub, hint, onDrop }) {
  const [hot, setHot] = React.useState(false);
  return (
    <div className={'dropzone ' + (hot ? 'hot' : '')}
         onClick={onDrop}
         onDragOver={(e) => { e.preventDefault(); setHot(true); }}
         onDragLeave={() => setHot(false)}
         onDrop={(e) => { e.preventDefault(); setHot(false); onDrop && onDrop(); }}>
      <div className="dz-ico"><Icon name={icon || 'folder'} s={26} /></div>
      <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
      <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>{sub}</div>
      {hint && <div className="empty-hint mono" style={{ marginTop: 12 }}>{hint}</div>}
    </div>
  );
}

// tiny inline markdown → JSX (handles the profile.md subset we author)
function MiniMd({ src }) {
  const lines = src.split('\n');
  const out = []; let list = null; let key = 0;
  const inline = (t) => {
    const parts = t.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) => p.startsWith('**')
      ? <strong key={i}>{p.slice(2, -2)}</strong> : <React.Fragment key={i}>{p}</React.Fragment>);
  };
  const flush = () => { if (list) { out.push(<ul key={key++}>{list}</ul>); list = null; } };
  lines.forEach((ln) => {
    if (ln.startsWith('# ')) { flush(); out.push(<h1 key={key++}>{ln.slice(2)}</h1>); }
    else if (ln.startsWith('> ')) { flush(); out.push(<blockquote key={key++}>{inline(ln.slice(2))}</blockquote>); }
    else if (ln.startsWith('- ')) { (list = list || []).push(<li key={key++}>{inline(ln.slice(2))}</li>); }
    else if (ln.trim() === '') { flush(); }
    else { flush(); out.push(<p key={key++}>{inline(ln)}</p>); }
  });
  flush();
  return <div className="md">{out}</div>;
}

Object.assign(window, { Icon, Stars, BandBadge, BAND_LABEL, Btn, Stat, DistBar, Dropzone, MiniMd });
