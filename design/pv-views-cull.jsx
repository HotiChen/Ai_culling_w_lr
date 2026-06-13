// pv-views-cull.jsx — Stage B (Cull), Review grid + detail, Arbitration, Export

const BAND_COLOR = { keep: 'var(--keep)', maybe: 'var(--maybe)', reject: 'var(--reject)' };

// ── Stage B: drop a new shoot folder & run the cull ──────────────────
function CullView({ accent, onDone }) {
  const [phase, setPhase] = React.useState('drop');
  const [folder, setFolder] = React.useState(null);
  const [step, setStep] = React.useState(-1);
  const [pct, setPct] = React.useState(0);
  const steps = window.CULL_STEPS;
  const timer = React.useRef(null);

  const start = () => {
    setPhase('running'); setStep(0); setPct(0);
    let i = 0;
    timer.current = setInterval(() => {
      i += 1;
      if (i >= steps.length) { clearInterval(timer.current); setStep(steps.length); setPct(100); setTimeout(() => onDone(), 600); }
      else { setStep(i); setPct(Math.round(i / steps.length * 100)); }
    }, 720);
  };
  React.useEffect(() => () => clearInterval(timer.current), []);

  if (phase === 'drop') {
    return (
      <div className="page fade-in">
        <div className="section-head"><h2>選片 — 新的拍攝資料夾</h2><span className="hint">Stage B · apply 熱茶</span></div>
        <p className="muted" style={{ maxWidth: 620, lineHeight: 1.6, marginBottom: 22 }}>
          拖入新拍的照片資料夾，PhotoVault 會依「熱茶」的品味自動選圖、套用最匹配的調色 preset，
          並把灰色地帶交給 Gemma 看圖仲裁。全程在本機，照片不出機。
        </p>
        <Dropzone icon="image"
          title={folder || '拖入照片資料夾 · Drop a shoot folder'}
          sub="支援 RAW / JPEG — rawpy 全畫質分析"
          hint="2026-06-12 外拍 · 36 frames"
          onDrop={() => setFolder('2026-06-12 外拍 / 36 frames')} />
        {folder && (
          <div className="card pad mt16" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <Icon name="image" s={22} style={{ color: accent }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>2026-06-12 外拍 · 36 張</div>
              <div className="h-sub">依 EXIF 拍攝時間分為 8 個連拍組</div>
            </div>
            <span className="badge neutral" style={{ fontSize: 12.5, padding: '5px 11px' }}>套用 · 熱茶</span>
            <Btn primary icon="cull" onClick={start}>執行選片 · Run cull</Btn>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="page fade-in" style={{ maxWidth: 720 }}>
      <div className="section-head"><h2>選片中…</h2><span className="hint">36 frames · 8 bursts</span></div>
      <div className="card pad">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 12.5 }}>階段 B 管線 · apply_to_folder()</span>
          <span className="mono" style={{ fontSize: 13, color: accent }}>{pct}%</span>
        </div>
        <div className="bar-track" style={{ marginBottom: 22 }}><div className="bar-fill" style={{ width: pct + '%', background: accent, transition: 'width .55s' }}></div></div>
        <div className="col" style={{ gap: 4 }}>
          {steps.map((s, i) => {
            const state = i < step ? 'done' : i === step ? 'now' : 'wait';
            return (
              <div key={s.k} className="row" style={{ gap: 12, padding: '9px 4px', opacity: state === 'wait' ? .4 : 1, transition: 'opacity .3s' }}>
                <span style={{ width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  background: state === 'done' ? 'var(--keep-soft)' : state === 'now' ? accent : 'rgba(255,255,255,.06)',
                  color: state === 'done' ? 'var(--keep)' : state === 'now' ? '#241704' : 'var(--ink-3)' }}>
                  {state === 'done' ? <Icon name="check" s={13} w={2.4} /> : state === 'now'
                    ? <span style={{ width: 11, height: 11, border: '2px solid #241704', borderTopColor: 'transparent', borderRadius: '50%', animation: 'sp .7s linear infinite' }}></span>
                    : <span className="mono" style={{ fontSize: 11 }}>{i + 1}</span>}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{s.zh} <span className="muted mono" style={{ fontSize: 11 }}>· {s.en}</span></div>
                </div>
                <span className="muted mono" style={{ fontSize: 11 }}>{s.detail}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── score breakdown helper ───────────────────────────────────────────
function breakdown(shot) {
  const clf = Math.min(.99, Math.max(.05, shot.score * 0.6 + 0.18));
  const taste = Math.min(.99, Math.max(.05, shot.score * 0.55 + 0.2));
  const sharpN = Math.min(1, shot.sharp / 260);
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
        {showOverlay && <span className="tile-score" style={{ color: BAND_COLOR[s.band] }}>{s.score.toFixed(2)}</span>}
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
          <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: BAND_COLOR[shot.band] }}>{shot.score.toFixed(2)}</span>
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
  const maybes = window.ALL_SHOTS.filter(s => s.band === 'maybe');
  // pre-baked Gemma verdicts for the demo
  const verdicts = {
    F002: { v: 'reject', why: '與 F001 近重複，且眼神略飄；同組已有更佳張，淘汰。' },
    F006: { v: 'keep', why: '構圖雖中性，但膚調與光線符合「暖膚淺景深」品味，留。' },
    F008: { v: 'reject', why: '近重複且表情偏弱、缺乏情緒張力；不符合你的留片標準。' },
    F011: { v: 'reject', why: '與 F012 為一組，兩張平淡中相對較弱，去重後淘汰。' },
    F012: { v: 'keep', why: '同組中表情與清晰度俱佳，作為代表張保留。' },
    F014: { v: 'keep', why: '邊界分數但 85mm 淺景深、眼神到位，傾向保留。' },
  };
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
                  <span className="mono" style={{ fontSize: 12.5, color: 'var(--maybe)' }}>score {s.score.toFixed(2)}</span>
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
  const [opts, setOpts] = React.useState({ ratings: true, flags: true, foldering: true, report: true });
  const c = window.BAND_COUNTS;
  const toggle = (k) => setOpts(o => ({ ...o, [k]: !o[k] }));

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
        <Btn primary icon="export" onClick={() => setDone(true)}>匯出 {c.keep + c.maybe} 張 · Export</Btn>
        <Btn ghost>取消</Btn>
      </div>
    </div>
  );
}

Object.assign(window, { CullView, ReviewView, ArbitrateView, ExportView });
