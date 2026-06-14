// pv-app.jsx — window chrome + routing + tweaks

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#C98A3C",
  "density": "regular",
  "showOverlay": true,
  "groupBursts": false
}/*EDITMODE-END*/;

// lighten a hex toward white by f (0..1)
function lighten(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r = Math.round(r + (255 - r) * f); g = Math.round(g + (255 - g) * f); b = Math.round(b + (255 - b) * f);
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
}
function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`;
}

const CRUMB = {
  inspector: ['檔案總覽', 'Profile'],
  learn: ['學習新檔案', 'Learn'],
  cull: ['選片', 'Cull'],
  review: ['審片', 'Review'],
  arbitrate: ['仲裁', 'Arbitrate'],
  export: ['匯出', 'Export'],
  settings: ['設定', 'Settings'],
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [view, setView] = React.useState('inspector');
  const [profileId, setProfileId] = React.useState(window.__INITIAL_PROFILE);
  // tick bumps when async data (profile detail / apply) arrives so the app re-renders.
  const [, setTick] = React.useState(0);
  const bump = () => setTick(x => x + 1);
  const FALLBACK_PROFILE = { id: null, name: '無檔案', en: 'No profile', accent: '#6E6457', samples: 0, catalogs: 0, keepRate: 0, blurb: '' };
  const profile = window.PROFILES.find(p => p.id === profileId) || window.PROFILES[0] || FALLBACK_PROFILE;
  const accent = t.accent;

  // Switching the active profile fetches its detail (thresholds/presets/md) then re-renders.
  const selectProfile = (id) => {
    setProfileId(id);
    if (id && window.pvLoadProfile) {
      window.pvLoadProfile(id).then(bump).catch(() => bump());
    }
  };

  React.useEffect(() => {
    const r = document.documentElement.style;
    r.setProperty('--accent', accent);
    r.setProperty('--accent-2', lighten(accent, 0.22));
    r.setProperty('--accent-soft', rgba(accent, 0.16));
    r.setProperty('--accent-line', rgba(accent, 0.42));
  }, [accent]);

  const [crumbZh, crumbEn] = CRUMB[view];
  const showProfile = !['learn', 'settings'].includes(view);

  const topActions = () => {
    switch (view) {
      case 'inspector': return (<>
        <Btn ghost icon="refresh" onClick={() => setView('learn')}>重新學習</Btn>
        <Btn primary icon="cull" onClick={() => setView('cull')}>選片 · Cull</Btn>
      </>);
      case 'review': return (<>
        <Btn ghost icon="arbitrate" onClick={() => setView('arbitrate')}>仲裁 {window.BAND_COUNTS.maybe}</Btn>
        <Btn primary icon="export" onClick={() => setView('export')}>匯出 · Export</Btn>
      </>);
      case 'arbitrate': return <Btn primary icon="export" onClick={() => setView('export')}>匯出 · Export</Btn>;
      default: return null;
    }
  };

  const renderView = () => {
    switch (view) {
      case 'learn': return <LearnView accent={accent} onDone={(name) => { if (name) selectProfile(name); setView('inspector'); }} />;
      case 'inspector': return <InspectorView profile={profile} accent={accent} />;
      case 'cull': return <CullView accent={accent} profileId={profileId} onDone={() => { bump(); setView('review'); }} onExport={() => { bump(); setView('export'); }} />;
      case 'review': return <ReviewView accent={accent} density={t.density} showOverlay={t.showOverlay} groupBursts={t.groupBursts} />;
      case 'arbitrate': return <ArbitrateView accent={accent} />;
      case 'export': return <ExportView accent={accent} />;
      case 'settings': return <SettingsView accent={accent} />;
      default: return null;
    }
  };

  const isReview = view === 'review';

  return (
    <div className="desktop">
      <div className="window">
        <div className="titlebar">
          <div className="lights"><span className="light r"></span><span className="light y"></span><span className="light g"></span></div>
          <div className="tb-title"><b>PhotoVault</b><span className="tb-sep">—</span>{profile.name} · {profile.en}</div>
          <div className="tb-status"><span className="dot-live"></span>本地 · 離線 · 0 API</div>
        </div>

        <div className="body">
          <Sidebar view={view} setView={setView} profileId={profileId} setProfileId={selectProfile} accent={accent} />

          <div className="main">
            <div className="topbar">
              <div className="crumb">
                {showProfile && <><span style={{ display: 'inline-flex', width: 9, height: 9, borderRadius: '50%', background: profile.accent }}></span><span>{profile.name}</span><span className="sl">/</span></>}
                <b>{crumbZh}</b><span className="mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>{crumbEn}</span>
              </div>
              <div className="top-actions">{topActions()}</div>
            </div>

            {isReview ? renderView() : <div className="scroll">{renderView()}</div>}
          </div>
        </div>
      </div>

      <TweaksPanel>
        <TweakSection label="外觀 · Appearance" />
        <TweakColor label="主題色 Accent" value={t.accent}
          options={['#C98A3C', '#D9756A', '#6E8BA8', '#7FA882', '#B07CC6']}
          onChange={(v) => setTweak('accent', v)} />
        <TweakSection label="審片網格 · Review grid" />
        <TweakRadio label="密度 Density" value={t.density} options={['compact', 'regular', 'comfy']}
          onChange={(v) => setTweak('density', v)} />
        <TweakToggle label="顯示分數/星等 Score overlay" value={t.showOverlay}
          onChange={(v) => setTweak('showOverlay', v)} />
        <TweakToggle label="依連拍組分群 Group bursts" value={t.groupBursts}
          onChange={(v) => setTweak('groupBursts', v)} />
      </TweaksPanel>
    </div>
  );
}

window.App = App;
// NOTE: rendering is performed by pv-boot.jsx after initial data has loaded.
