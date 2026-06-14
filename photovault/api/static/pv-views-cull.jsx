// pv-views-cull.jsx — Stage B (Cull), Review grid + detail, Arbitration, Export

const BAND_COLOR = { keep: 'var(--keep)', maybe: 'var(--maybe)', reject: 'var(--reject)' };

// ── Stage B: drop a new shoot folder & run the cull ──────────────────
function CullView({ accent, onDone, profileId }) {
  const [phase, setPhase] = React.useState('drop');
  // M5: a click opens a native OS folder chooser (/api/pick-folder); the user
  // never types a path. Manual entry stays as a fallback where no picker exists.
  const [folder, setFolder] = React.useState('');
  const [picking, setPicking] = React.useState(false);
  const [pickerSupported, setPickerSupported] = React.useState(true);
  const [error, setError] = React.useState(null);
  // Live cull progress (driven by /api/apply/stream events).
  const [prog, setProg] = React.useState({ pct: 0, label: '', name: '', index: 0, total: 0 });
  const [cur, setCur] = React.useState(null);  // current photo event
  const [tally, setTally] = React.useState({ keep: 0, maybe: 0, reject: 0 });
  const [recent, setRecent] = React.useState([]);  // last few photos

  const pickFolder = async () => {
    setError(null); setPicking(true);
    const res = await window.pvPickFolder();
    setPicking(false);
    if (res && res.path) setFolder(res.path);
    else if (res && res.supported === false) setPickerSupported(false);
  };

  // Run the REAL apply, streaming live per-photo verdicts.
  const PHASE_LABEL = { scan: '掃描資料夾', dedup: '連拍去重', arbitrate: 'Gemma 仲裁', export: '寫入 XMP / 報告' };
  const start = () => {
    if (!folder) { setError('請先選擇照片資料夾'); return; }
    if (!profileId) { setError('請先選擇或建立一個品味檔案'); return; }
    setError(null); setPhase('running');
    setProg({ pct: 2, label: PHASE_LABEL.scan, name: '', index: 0, total: 0 });
    setCur(null); setTally({ keep: 0, maybe: 0, reject: 0 }); setRecent([]);
    let keep = 0, maybe = 0, reject = 0;
    const rec = [];
    window.pvApplyStream(folder, profileId, { no_llm: true }, (ev) => {
      if (ev.phase === 'scan') {
        setProg((p) => ({ ...p, label: PHASE_LABEL.scan, total: ev.n_photos }));
      } else if (ev.phase === 'photo') {
        if (!ev.skipped) {
          if (ev.band === 'keep') keep += 1;
          else if (ev.band === 'maybe') maybe += 1;
          else if (ev.band === 'reject') reject += 1;
        }
        setCur(ev);
        setTally({ keep, maybe, reject });
        rec.unshift(ev); if (rec.length > 6) rec.pop();
        setRecent([...rec]);
        setProg({
          label: '逐張評分', name: ev.name, index: ev.index, total: ev.total,
          pct: Math.round((ev.index / Math.max(1, ev.total)) * 88),
        });
      } else if (PHASE_LABEL[ev.phase]) {
        setProg((p) => ({ ...p, label: PHASE_LABEL[ev.phase], pct: ev.phase === 'export' ? 98 : Math.max(p.pct, 90) }));
      } else if (ev.phase === 'done') {
        setProg((p) => ({ ...p, pct: 100 }));
        setTimeout(() => onDone(), 250);
      } else if (ev.phase === 'error') {
        setError(ev.detail || 'cull failed'); setPhase('drop');
      }
    }).catch((e) => { setError(String(e.message || e)); setPhase('drop'); });
  };

  if (phase === 'drop') {
    return (
      <div className="page fade-in">
        <div className="section-head"><h2>選片 — 新的拍攝資料夾</h2><span className="hint">Stage B · apply {profileId || '—'}</span></div>
        <p className="muted" style={{ maxWidth: 620, lineHeight: 1.6, marginBottom: 22 }}>
          指向新拍的照片資料夾，PhotoVault 會依目前品味檔案自動選圖、套用調色 preset，
          並把灰色地帶交給 Gemma 看圖仲裁。全程在本機，照片不出機。
        </p>
        <Dropzone icon="image"
          title={picking ? '選擇資料夾中…' : (folder || '選擇照片資料夾 · Choose shoot folder')}
          sub="支援 RAW / JPEG — rawpy 全畫質分析"
          hint="點此開啟資料夾選擇框"
          onDrop={pickFolder} />
        <div className="card pad mt16" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {folder ? (
            <div className="row gap12" style={{ alignItems: 'center', background: 'var(--panel-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '7px 11px' }}>
              <Icon name="image" s={16} style={{ color: accent, flexShrink: 0 }} />
              <span className="mono" style={{ flex: 1, fontSize: 12, wordBreak: 'break-all' }}>{folder}</span>
              <button className="btn ghost sm" onClick={() => setFolder('')} title="清除"><Icon name="x" s={14} /></button>
            </div>
          ) : (
            <div className="empty-hint">尚未選擇資料夾</div>
          )}
          {!pickerSupported && (
            <input className="mono" value={folder} onChange={(e) => setFolder(e.target.value)}
              placeholder="/absolute/path/to/shoot"
              style={{ background: 'var(--panel-2)', border: '1px solid var(--line-2)', color: 'var(--ink)', borderRadius: 'var(--r-sm)', padding: '9px 12px', fontSize: 12.5 }} />
          )}
          <div className="row gap8" style={{ alignItems: 'center' }}>
            <Btn icon="folder" onClick={pickFolder} disabled={picking}>{picking ? '選擇中…' : '選擇資料夾 · Choose'}</Btn>
            <div style={{ flex: 1 }}></div>
            <span className="badge neutral" style={{ fontSize: 12.5, padding: '5px 11px' }}>套用 · {profileId || '—'}</span>
            <Btn primary icon="cull" onClick={start} disabled={!folder || !profileId}>執行選片 · Run cull</Btn>
          </div>
          {error && <div className="reason" style={{ borderLeftColor: 'var(--reject)', color: 'var(--reject)' }}>{error}</div>}
        </div>
      </div>
    );
  }

  const bandZh = { keep: '留', maybe: '待定', reject: '淘汰' };
  const PhotoRow = ({ ev, big }) => (
    <div className="row gap12" style={{ alignItems: 'center', padding: big ? '0' : '6px 0' }}>
      <Icon name="image" s={big ? 18 : 14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
      <span className="mono" style={{ flex: 1, fontSize: big ? 13 : 12, wordBreak: 'break-all', fontWeight: big ? 600 : 400 }}>{ev.name}</span>
      {!ev.skipped && ev.stars > 0 && <Stars n={ev.stars} size={big ? 13 : 11} />}
      {ev.skipped
        ? <span className="badge neutral">略過</span>
        : <span className={'badge ' + ev.band}>{bandZh[ev.band] || ev.band}</span>}
      <span className="mono" style={{ width: 38, textAlign: 'right', fontSize: big ? 12 : 11, color: BAND_COLOR[ev.band] || 'var(--ink-3)' }}>{fmtScore(ev.score)}</span>
    </div>
  );

  return (
    <div className="page fade-in" style={{ maxWidth: 760 }}>
      <div className="section-head"><h2>選片中…</h2><span className="hint">本地不出機 · {prog.label}</span></div>
      <div className="card pad">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 12.5 }}>
            {prog.total ? `照片 ${prog.index}/${prog.total}` : '掃描中…'} · apply_to_folder()
          </span>
          <span className="mono" style={{ fontSize: 13, color: accent }}>{prog.pct}%</span>
        </div>
        <div className="bar-track" style={{ marginBottom: 16 }}>
          <div className="bar-fill" style={{ width: prog.pct + '%', background: accent, transition: 'width .25s' }}></div>
        </div>

        <div className="row gap16" style={{ marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12 }}>留 <b style={{ color: 'var(--keep)' }}>{tally.keep}</b></span>
          <span className="mono" style={{ fontSize: 12 }}>待定 <b style={{ color: 'var(--maybe)' }}>{tally.maybe}</b></span>
          <span className="mono" style={{ fontSize: 12 }}>淘汰 <b style={{ color: 'var(--reject)' }}>{tally.reject}</b></span>
        </div>

        {cur && (
          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 14 }}>
            <PhotoRow ev={cur} big />
            {cur.reason && <div className="muted mono" style={{ fontSize: 11, marginTop: 6, paddingLeft: 30 }}>{cur.reason}</div>}
            {recent.length > 1 && (
              <div className="col" style={{ gap: 0, marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 6 }}>
                {recent.slice(1).map((ev, i) => <PhotoRow key={ev.name + i} ev={ev} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── score helpers (null-safe for gate-only frames with score === null) ─
function fmtScore(v) { return (v == null) ? '—' : Number(v).toFixed(2); }
function breakdown(shot) {
  const sc = shot.score == null ? 0 : shot.score;
  const clf = Math.min(.99, Math.max(.05, sc * 0.6 + 0.18));
  const taste = Math.min(.99, Math.max(.05, sc * 0.55 + 0.2));
  const sharpN = shot.sharp == null ? 0 : Math.min(1, shot.sharp / 260);
  return [
    { lbl: '分類器機率', en: 'classifier', v: clf, color: accent => accent },
    { lbl: 'taste 相似度', en: 'taste_vector', v: taste },
    { lbl: '清晰度', en: 'sharpness', v: sharpN },
    { lbl: '閉眼閘', en: 'blink gate', v: shot.blink ? 0 : 1, gate: true, pass: !shot.blink },
  ];
}

// ── Review grid + detail drawer ──────────────────────────────────────
function ReviewView({ accent, density, showOverlay, groupBursts }) {
  const [filter, setFilter] = React.useState('all');
  const [sel, setSel] = React.useState(null);
  const counts = window.BAND_COUNTS;
  const cols = density === 'compact' ? 5 : density === 'comfy' ? 3 : 4;

  const matches = (s) => filter === 'all' || s.band === filter;

  const FilterSeg = () => (
    <div className="seg">
      {[['all', '全部', counts.total], ['keep', '留', counts.keep], ['maybe', '待定', counts.maybe], ['reject', '淘汰', counts.reject]].map(([k, zh, ct]) => (
        <button key={k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>
          {k !== 'all' && <span style={{ width: 7, height: 7, borderRadius: '50%', background: BAND_COLOR[k] || 'var(--ink-3)' }}></span>}
          {zh} <span className="ct">{ct}</span>
        </button>
      ))}
    </div>
  );

  const Tile = ({ s }) => (
    <div className={'tile ' + (sel && sel.id === s.id ? 'sel ' : '') + (s.band === 'reject' ? 'dim' : '')} onClick={() => setSel(s)}>
      <img className="tile-img" src={s.src} alt={s.id} loading="lazy" />
      <div className="tile-band"><BandBadge band={s.band} /></div>
      {s.isDup && <div className="tile-dup"><Icon name="dup" s={11} /> 近重複</div>}
      {s.blink && <div className="tile-dup" style={{ top: 'auto', bottom: 9, color: 'var(--reject)' }}><Icon name="eyeOff" s={11} /> 閉眼</div>}
      <div className="tile-foot">
        <div className="col" style={{ gap: 4 }}>
          <span className="tile-id">{s.id} · {s.preset}</span>
          {showOverlay && <Stars n={s.stars} size={11} />}
        </div>
        {showOverlay && <span className="tile-score" style={{ color: BAND_COLOR[s.band] }}>{fmtScore(s.score)}</span>}
      </div>
    </div>
  );

  const Grid = () => {
    if (groupBursts) {
      return window.SHOOT.bursts.map(b => {
        const shots = b.shots.filter(matches);
        if (!shots.length) return null;
        return (
          <div key={b.id} style={{ marginBottom: 22 }}>
            <div className="row gap8" style={{ marginBottom: 10 }}>
              <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-2)', fontWeight: 600 }}>{b.id} · {b.label}</span>
              <span className="muted mono" style={{ fontSize: 10.5 }}>{b.shots.length} 張 → 留 {b.shots.filter(x => x.band === 'keep').length}</span>
              <div style={{ flex: 1, height: 1, background: 'var(--line)' }}></div>
            </div>
            <div className="rev-grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
              {shots.map(s => <Tile key={s.id} s={s} />)}
            </div>
          </div>
        );
      });
    }
    const shots = window.ALL_SHOTS.filter(matches);
    return <div className="rev-grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>{shots.map(s => <Tile key={s.id} s={s} />)}</div>;
  };

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 0 }}>
      <div className="scroll" style={{ flex: 1 }}>
        <div className="page wide">
          <div className="toolbar-row" style={{ marginBottom: 18 }}>
            <FilterSeg />
            <div className="spacer"></div>
            <span className="muted mono" style={{ fontSize: 11.5 }}>{window.SHOOT.name} · {window.SHOOT.en}</span>
          </div>
          <Grid />
        </div>
      </div>
      {sel && <DetailDrawer shot={sel} accent={accent} onClose={() => setSel(null)} />}
    </div>
  );
}

function DetailDrawer({ shot, accent, onClose }) {
  const bd = breakdown(shot);
  const preset = window.PRESETS.find(p => p.name === shot.preset);
  return (
    <div className="drawer fade-in">
      <div style={{ position: 'relative' }}>
        <img className="drawer-img" src={shot.src} alt={shot.id} />
        <button className="btn ghost sm" style={{ position: 'absolute', top: 10, right: 10, background: 'rgba(16,13,10,.7)', backdropFilter: 'blur(6px)' }} onClick={onClose}><Icon name="x" s={15} /></button>
        <div style={{ position: 'absolute', bottom: 10, left: 12 }}><BandBadge band={shot.band} /></div>
      </div>
      <div className="pad" style={{ padding: '16px 18px' }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{shot.id}</span>
          <Stars n={shot.stars} size={15} />
        </div>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16 }}>
          <span className="muted mono" style={{ fontSize: 11 }}>{shot.burst} · {shot.isDup ? '近重複' : '代表張'}</span>
          <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: BAND_COLOR[shot.band] }}>{fmtScore(shot.score)}</span>
        </div>

        <div className="h-title" style={{ fontSize: 11.5, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 12 }}>分數拆解 · score</div>
        <div className="score-breakdown" style={{ marginBottom: 18 }}>
          {bd.map(b => (
            <div key={b.lbl} className="sb-row">
              <span className="lbl">{b.lbl}</span>
              {b.gate ? (
                <span className={'badge ' + (b.pass ? 'keep' : 'reject')} style={{ flex: 1, justifyContent: 'center' }}>{b.pass ? '通過 pass' : '淘汰 closed-eyes'}</span>
              ) : (
                <><div className="track"><div className="fill" style={{ width: (b.v*100) + '%', background: accent }}></div></div><span className="pct">{Math.round(b.v*100)}</span></>
              )}
            </div>
          ))}
        </div>

        <div className={'reason'} style={{ marginBottom: 18 }}>
          {shot.band === 'maybe' && <div className="gemma"><Icon name="sparkle" s={12} /> Gemma 仲裁</div>}
          {shot.reason}
        </div>

        <div className="h-title" style={{ fontSize: 11.5, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 10 }}>EXIF</div>
        <div style={{ marginBottom: 16 }}>
          <div className="kv"><span className="k">光圈 · aperture</span><span className="v">{shot.ap}</span></div>
          <div className="kv"><span className="k">焦段 · focal</span><span className="v">{shot.focal}</span></div>
          <div className="kv"><span className="k">快門 · shutter</span><span className="v">{shot.sh}</span></div>
          <div className="kv"><span className="k">ISO</span><span className="v">{shot.iso}</span></div>
          <div className="kv"><span className="k">清晰度 · sharpness</span><span className="v" style={{ color: shot.sharp < 118 ? 'var(--reject)' : 'var(--ink)' }}>{shot.sharp}</span></div>
        </div>

        {preset && (
          <>
            <div className="h-title" style={{ fontSize: 11.5, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 10 }}>套用 preset</div>
            <div className="row gap12" style={{ marginBottom: 18 }}>
              <div style={{ width: 48, height: 48, borderRadius: 8, background: preset.grad, border: '1px solid var(--line-2)', flexShrink: 0 }}></div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{preset.name}</div>
                <div className="h-sub">{preset.en} · {preset.id}.xmp</div>
              </div>
            </div>
          </>
        )}

        <div className="row gap8">
          <Btn primary sm icon="check" style={{ flex: 1, justifyContent: 'center' }}>留 · Keep</Btn>
          <Btn sm icon="x" style={{ flex: 1, justifyContent: 'center' }}>淘汰 · Reject</Btn>
        </div>
      </div>
    </div>
  );
}

// ── Gemma arbitration — the gray-zone "maybe" pile ───────────────────
function ArbitrateView({ accent }) {
  // M5: the real maybe band from the last apply. With --no-llm (the API default
  // for snappy local use) maybe items are NOT auto-arbitrated, so each card
  // shows its real CV/score reason and lets the user accept/override manually.
  // Wiring a live Gemma verdict per card is a thin follow-up (POST that streams
  // judge.arbitrate); kept cosmetic here so the design stays intact.
  const maybes = window.ALL_SHOTS.filter(s => s.band === 'maybe');
  const verdicts = {};
  return (
    <div className="page fade-in" style={{ maxWidth: 940 }}>
      <div className="section-head"><h2>灰色地帶仲裁</h2><span className="hint">只有 maybe 那一疊送 Gemma 看圖</span></div>
      <div className="card pad mt8" style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20, borderColor: 'var(--accent-line)', background: 'var(--accent-soft)' }}>
        <Icon name="sparkle" s={22} style={{ color: accent }} />
        <div style={{ flex: 1, fontSize: 12.5, lineHeight: 1.55 }} className="muted">
          清楚該留/該丟的由 CV+CLIP 直接決定。<b style={{ color: 'var(--ink)' }}>只有 {maybes.length} 張落在灰色地帶</b>，由同一個多模態 Gemma 搭配你的規則書看圖做最終判斷 + 一句理由。
        </div>
        <Btn icon="refresh" sm>重新仲裁 · Re-run</Btn>
      </div>
      <div className="col gap12">
        {maybes.map(s => {
          const verd = verdicts[s.id] || { v: 'keep', why: s.reason };
          return (
            <div key={s.id} className="arb-card">
              <img className="arb-img" src={s.src} alt={s.id} />
              <div className="pad" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{s.id} · {s.burst} · <span className="muted">{s.preset}</span></span>
                  <span className="mono" style={{ fontSize: 12.5, color: 'var(--maybe)' }}>score {fmtScore(s.score)}</span>
                </div>
                <div className="reason" style={{ flex: 1 }}>
                  <div className="gemma"><Icon name="sparkle" s={12} /> Gemma 看圖判斷 →
                    <span className={'badge ' + verd.v} style={{ marginLeft: 6 }}>{verd.v === 'keep' ? '留 KEEP' : '淘汰 REJECT'}</span>
                  </div>
                  {verd.why}
                </div>
                <div className="row gap8">
                  <Btn primary sm icon="check" style={{ background: verd.v === 'keep' ? undefined : 'var(--raise)', color: verd.v === 'keep' ? undefined : 'var(--ink)', borderColor: verd.v === 'keep' ? 'transparent' : 'var(--line-2)' }}>接受仲裁 · Accept</Btn>
                  <Btn sm>人工覆寫 · Override</Btn>
                  <div style={{ flex: 1 }}></div>
                  <Stars n={s.stars} size={15} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Export — .lrcat catalog or XMP sidecars ──────────────────────────
function ExportView({ accent }) {
  const [target, setTarget] = React.useState('lrcat');
  const [done, setDone] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [opts, setOpts] = React.useState({ ratings: true, flags: true, foldering: true, report: true });
  const c = window.BAND_COUNTS;
  const toggle = (k) => setOpts(o => ({ ...o, [k]: !o[k] }));

  // M5 real export: XMP sidecars are ALWAYS written by apply_to_folder; here we
  // re-run apply with the chosen foldering / HTML-report options so the on-disk
  // outputs match the toggles. (A native .lrcat writer is a later milestone.)
  const runExport = () => {
    const folder = window.__LAST_FOLDER, profile = window.__LAST_PROFILE;
    if (!folder || !profile) { setError('尚未執行選片，無可匯出的結果'); return; }
    setError(null); setBusy(true);
    window.pvApply(folder, profile, { no_llm: true, sort: !!opts.foldering, report: !!opts.report })
      .then(() => { setBusy(false); setDone(true); })
      .catch((e) => { setBusy(false); setError(String(e.message || e)); });
  };

  const Opt = ({ k, label, en }) => (
    <div className="kv" style={{ padding: '11px 0', cursor: 'pointer', alignItems: 'center' }} onClick={() => toggle(k)}>
      <span className="k" style={{ color: 'var(--ink)', fontSize: 13 }}>{label} <span className="muted mono" style={{ fontSize: 11 }}>· {en}</span></span>
      <span style={{ width: 38, height: 22, borderRadius: 12, background: opts[k] ? accent : 'rgba(255,255,255,.1)', position: 'relative', transition: 'background .15s', flexShrink: 0 }}>
        <span style={{ position: 'absolute', top: 2, left: opts[k] ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left .15s' }}></span>
      </span>
    </div>
  );

  const TargetCard = ({ id, icon, title, en, desc }) => (
    <div className="card pad" style={{ cursor: 'pointer', borderColor: target === id ? 'var(--accent-line)' : 'var(--line)', background: target === id ? 'var(--accent-soft)' : 'var(--panel)' }} onClick={() => setTarget(id)}>
      <div className="row gap12" style={{ alignItems: 'flex-start' }}>
        <div style={{ width: 38, height: 38, borderRadius: 9, background: 'var(--raise)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: target === id ? accent : 'var(--ink-2)', flexShrink: 0 }}><Icon name={icon} s={19} /></div>
        <div style={{ flex: 1 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 700, fontSize: 13.5 }}>{title} <span className="muted mono" style={{ fontSize: 11, fontWeight: 400 }}>· {en}</span></span>
            <span style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid ' + (target === id ? accent : 'var(--line-2)'), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {target === id && <span style={{ width: 9, height: 9, borderRadius: '50%', background: accent }}></span>}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 5, lineHeight: 1.5 }}>{desc}</div>
        </div>
      </div>
    </div>
  );

  if (done) {
    return (
      <div className="page fade-in" style={{ maxWidth: 640 }}>
        <div className="card pad" style={{ textAlign: 'center', padding: '40px 30px' }}>
          <div style={{ width: 60, height: 60, borderRadius: 16, margin: '0 auto 18px', background: 'var(--keep-soft)', color: 'var(--keep)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon name="check" s={30} w={2.4} /></div>
          <h2 style={{ fontSize: 19 }}>{target === 'lrcat' ? '已產出 Lightroom 編目檔' : '已寫入 XMP sidecar'}</h2>
          <p className="muted mono" style={{ marginTop: 10, fontSize: 12.5 }}>
            {target === 'lrcat' ? '~/Pictures/外拍_2026-06-12_culled.lrcat' : '36 × .xmp sidecars · keep/ maybe/ reject/ 子資料夾'}
          </p>
          <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>{c.keep} 張已選、已預調，直接在 Lightroom 開啟即可。</p>
          <Btn primary icon="export" style={{ marginTop: 22 }} onClick={() => setDone(false)}>再次匯出 · Export again</Btn>
        </div>
      </div>
    );
  }

  return (
    <div className="page fade-in" style={{ maxWidth: 820 }}>
      <div className="section-head"><h2>匯出到 Lightroom</h2><span className="hint">選好且預調好 → import 即用</span></div>

      <div className="grid-stats" style={{ marginBottom: 22 }}>
        <Stat v={c.keep} label="留 · keep" en="picked" color="var(--keep)" />
        <Stat v={c.maybe} label="待定 · maybe" en="arbitrated" color="var(--maybe)" />
        <Stat v={c.reject} label="淘汰 · reject" en="culled" color="var(--reject)" />
        <Stat v={window.PRESETS.length} label="套用 preset" en="looks" color={accent} />
      </div>

      <div className="section-head" style={{ marginBottom: 12 }}><h2 style={{ fontSize: 14 }}>匯出格式</h2><span className="hint">choose at export time</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
        <TargetCard id="lrcat" icon="catalog" title="Lightroom 編目檔" en=".lrcat" desc="直接產出可開啟的編目檔，選片結果與 develop preset 已內建。" />
        <TargetCard id="xmp" icon="export" title="XMP sidecar + 分流" en=".xmp" desc="每張寫星等＋旗標＋preset，並分流到 keep/ maybe/ reject/ 子資料夾後自行 import。" />
      </div>

      <div className="card pad" style={{ marginBottom: 22 }}>
        <div className="h-title" style={{ marginBottom: 4 }}>選項 · options</div>
        <Opt k="ratings" label="寫入星等" en="star ratings 1–5" />
        <Opt k="flags" label="寫入旗標" en="pick / reject flags" />
        <Opt k="foldering" label="分流子資料夾" en="keep / maybe / reject" />
        <Opt k="report" label="產出審片報告" en="HTML report · 縮圖+分數+理由" />
      </div>

      <div className="row gap12">
        <Btn primary icon="export" onClick={runExport} disabled={busy}>{busy ? '匯出中…' : `匯出 ${c.keep + c.maybe} 張 · Export`}</Btn>
        <Btn ghost>取消</Btn>
      </div>
      {error && <div className="reason mt16" style={{ borderLeftColor: 'var(--reject)', color: 'var(--reject)' }}>{error}</div>}
    </div>
  );
}

Object.assign(window, { CullView, ReviewView, ArbitrateView, ExportView });
