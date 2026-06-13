// pv-sidebar.jsx — left rail: brand, taste profiles, workflow nav, status

const NAV_ITEMS = [
  { id: 'inspector', zh: '檔案總覽', en: 'Profile', icon: 'profile' },
  { id: 'cull', zh: '選片', en: 'Cull', icon: 'cull' },
  { id: 'review', zh: '審片', en: 'Review', icon: 'review' },
  { id: 'arbitrate', zh: '仲裁', en: 'Arbitrate', icon: 'arbitrate' },
  { id: 'export', zh: '匯出', en: 'Export', icon: 'export' },
];

function Sidebar({ view, setView, profileId, setProfileId, accent }) {
  const maybeCount = window.BAND_COUNTS.maybe;
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#241704" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="12" cy="12" r="3.2"/><path d="M8 5l1.5-2h5L16 5"/>
          </svg>
        </div>
        <div>
          <div className="brand-name">PhotoVault</div>
          <div className="brand-sub">本地選片引擎 · offline</div>
        </div>
      </div>

      <div className="nav-label">品味檔案 · Taste Profiles</div>
      <div className="profiles">
        {window.PROFILES.map(p => (
          <div key={p.id} className={'profile-row ' + (p.id === profileId ? 'on' : '')}
               onClick={() => { setProfileId(p.id); if (['learn'].includes(view)) setView('inspector'); }}>
            <span className="pr-dot" style={{ background: p.accent, boxShadow: p.id === profileId ? `0 0 5px ${p.accent}` : 'none' }}></span>
            <div className="pr-text">
              <div className="pr-name">{p.name} <span>{p.en}</span></div>
              <div className="pr-meta">{p.samples.toLocaleString()} 樣本 · {Math.round(p.keepRate*100)}% 留存</div>
            </div>
          </div>
        ))}
      </div>
      <button className="learn-new" onClick={() => setView('learn')}>
        <Icon name="plus" s={15} /> 學習新檔案 · Learn new
      </button>

      <div className="nav-label">工作流程 · Workflow</div>
      <nav className="nav">
        {NAV_ITEMS.map(n => (
          <div key={n.id} className={'nav-item ' + (n.id === view ? 'on' : '')} onClick={() => setView(n.id)}>
            <span className="nav-ico"><Icon name={n.icon} s={17} /></span>
            <span className="nav-zh">{n.zh}</span>
            {n.id === 'arbitrate' && maybeCount > 0
              ? <span className="nav-badge">{maybeCount}</span>
              : <span className="nav-en">{n.en}</span>}
          </div>
        ))}
      </nav>

      <div className="side-foot">
        <div className={'nav-item ' + (view === 'settings' ? 'on' : '')} style={{ margin: 0 }} onClick={() => setView('settings')}>
          <span className="nav-ico"><Icon name="settings" s={17} /></span>
          <span className="nav-zh">設定</span><span className="nav-en">Settings</span>
        </div>
        <div className="side-chip"><span className="dot-live"></span>離線 · Gemma 4 12B</div>
      </div>
    </aside>
  );
}

Object.assign(window, { Sidebar });
