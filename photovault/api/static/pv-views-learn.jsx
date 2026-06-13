// pv-views-learn.jsx — Stage A (Learn), Profile Inspector, Settings

// ── Stage A: Learn a Taste Profile from catalog folder(s) ────────────
function LearnView({ accent, onDone }) {
  const [phase, setPhase] = React.useState('drop'); // drop | running | done
  // M5: browsers can't read real local paths from a drop, so we take an
  // absolute folder path via a text field (the dropzone stays as a visual cue).
  const [folder, setFolder] = React.useState('');
  const [name, setName] = React.useState('');
  const [step, setStep] = React.useState(-1);
  const [pct, setPct] = React.useState(0);
  const [error, setError] = React.useState(null);
  const [report, setReport] = React.useState(null);
  const steps = window.LEARN_STEPS;
  const timer = React.useRef(null);
  const pathInput = React.useRef(null);

  // Run the REAL learn (POST /api/learn) while the cosmetic progress animates.
  const start = () => {
    if (!folder || !name) { setError('請輸入編目檔資料夾路徑與檔名'); return; }
    setError(null);
    setPhase('running'); setStep(0); setPct(0);
    let i = 0;
    timer.current = setInterval(() => {
      i += 1;
      if (i >= steps.length - 1) { setStep(steps.length - 1); setPct(95); clearInterval(timer.current); }
      else { setStep(i); setPct(Math.round(i / steps.length * 100)); }
    }, 600);
    window.pvLearn(folder, name, { no_llm: true })
      .then((rep) => { clearInterval(timer.current); setReport(rep); setStep(steps.length); setPct(100); setTimeout(() => setPhase('done'), 300); })
      .catch((e) => { clearInterval(timer.current); setError(String(e.message || e)); setPhase('drop'); });
  };
  React.useEffect(() => () => clearInterval(timer.current), []);

  if (phase === 'drop') {
    return (
      <div className="page fade-in">
        <div className="section-head"><h2>學習新品味檔案</h2><span className="hint">Stage A · learn from .lrcat</span></div>
        <p className="muted" style={{ maxWidth: 620, lineHeight: 1.6, marginBottom: 22 }}>
          指向你的 Lightroom 編目檔資料夾，PhotoVault 會以唯讀方式分析你過往的選片與調色，
          學成一份可重複使用的「品味檔案」。原始檔已刪也能學 —— L1/L2 只住在編目檔，L3 改讀預覽快取。
        </p>
        <Dropzone icon="catalog"
          title={'輸入編目檔資料夾路徑 · Catalog folder path'}
          sub="掃描所有 .lrcat（immutable=1，不動原檔）"
          hint="點此後在下方填入絕對路徑，例如 /Users/you/Lightroom/"
          onDrop={() => pathInput.current && pathInput.current.focus()} />
        <div className="card pad mt16" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="row gap12" style={{ alignItems: 'center' }}>
            <Icon name="catalog" s={20} style={{ color: accent }} />
            <input ref={pathInput} className="mono" value={folder} onChange={(e) => setFolder(e.target.value)}
              placeholder="/absolute/path/to/catalogs"
              style={{ flex: 1, background: 'var(--panel-2)', border: '1px solid var(--line-2)', color: 'var(--ink)', borderRadius: 'var(--r-sm)', padding: '9px 12px', fontSize: 12.5 }} />
          </div>
          <div className="row gap12" style={{ alignItems: 'center' }}>
            <label className="muted mono" style={{ fontSize: 11, width: 28 }}>檔名</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="profile name"
              style={{ flex: 1, background: 'var(--panel-2)', border: '1px solid var(--line-2)', color: 'var(--ink)', borderRadius: 'var(--r-sm)', padding: '9px 12px', fontSize: 12.5 }} />
            <Btn primary icon="cpu" onClick={start} disabled={!folder || !name}>開始學習 · Learn</Btn>
          </div>
          {error && <div className="reason" style={{ borderLeftColor: 'var(--reject)', color: 'var(--reject)' }}>{error}</div>}
        </div>
      </div>
    );
  }

  if (phase === 'running') {
    return (
      <div className="page fade-in" style={{ maxWidth: 720 }}>
        <div className="section-head"><h2>學習中…</h2><span className="hint">Apple Silicon · MPS · 本地不出機</span></div>
        <div className="card pad">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
            <span className="muted" style={{ fontSize: 12.5 }}>階段 A 管線 · learn_from_folder()</span>
            <span className="mono" style={{ fontSize: 13, color: accent }}>{pct}%</span>
          </div>
          <div className="bar-track" style={{ marginBottom: 22 }}><div className="bar-fill" style={{ width: pct + '%', background: accent, transition: 'width .6s' }}></div></div>
          <div className="col" style={{ gap: 4 }}>
            {steps.map((s, i) => {
              const state = i < step ? 'done' : i === step ? 'now' : 'wait';
              return (
                <div key={s.k} className="row" style={{ gap: 12, padding: '9px 4px', opacity: state === 'wait' ? .4 : 1, transition: 'opacity .3s' }}>
                  <span style={{ width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    background: state === 'done' ? 'var(--keep-soft)' : state === 'now' ? accent : 'rgba(255,255,255,.06)',
                    color: state === 'done' ? 'var(--keep)' : state === 'now' ? '#241704' : 'var(--ink-3)' }}>
                    {state === 'done' ? <Icon name="check" s={13} w={2.4} /> : state === 'now'
                      ? <span className="spin" style={{ width: 11, height: 11, border: '2px solid #241704', borderTopColor: 'transparent', borderRadius: '50%', animation: 'sp .7s linear infinite' }}></span>
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
        <style>{`@keyframes sp{to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  // done
  return (
    <div className="page fade-in" style={{ maxWidth: 720 }}>
      <div className="card pad" style={{ textAlign: 'center', padding: '40px 30px' }}>
        <div style={{ width: 60, height: 60, borderRadius: 16, margin: '0 auto 18px', background: 'var(--keep-soft)', color: 'var(--keep)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="check" s={30} w={2.4} />
        </div>
        <h2 style={{ fontSize: 19 }}>品味檔案「{name}」已建立</h2>
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          {report ? `${report.n_images.toLocaleString()} 樣本 · ${report.n_presets} 個 preset · ${report.n_keepers} keep / ${report.n_rejects} reject` : ''}
        </p>
        <div className="grid-stats mt24" style={{ textAlign: 'left' }}>
          <Stat v={report ? report.n_catalogs : '—'} label="來源編目檔" en="catalogs" />
          <Stat v={report ? report.n_presets : '—'} label="風格 preset" en="looks" color={accent} />
          <Stat v={report ? report.n_keepers : '—'} label="keepers" en="kept" />
          <Stat v={report ? report.n_rejects : '—'} label="rejects" en="culled" />
        </div>
        <div className="row gap12 mt24" style={{ justifyContent: 'center' }}>
          <Btn primary icon="profile" onClick={() => onDone(name)}>檢視檔案 · Inspect</Btn>
        </div>
      </div>
    </div>
  );
}

// ── Profile Inspector ────────────────────────────────────────────────
function InspectorView({ profile, accent }) {
  const T = window.THRESHOLDS;
  return (
    <div className="page fade-in">
      <div className="grid-stats" style={{ marginBottom: 22 }}>
        <Stat v={Math.round(profile.keepRate*100) + '%'} label="留存率" en="keep-rate" color={accent} />
        <Stat v={profile.samples.toLocaleString()} label="訓練樣本" en="samples" />
        <Stat v={profile.catalogs} label="來源編目檔" en="catalogs" />
        <Stat v={T.burstRetain} label="連拍留存" en="per burst" />
        <Stat v={'≤' + T.isoTolerance} label="ISO 容忍" en="tolerance" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr .85fr', gap: 16, alignItems: 'start' }}>
        {/* rule-book */}
        <div className="card pad">
          <div className="section-head" style={{ marginBottom: 12 }}>
            <h2 style={{ fontSize: 14 }}>品味規則書</h2>
            <span className="hint">profile.md · Gemma 生成</span>
          </div>
          <MiniMd src={window.PROFILE_MD} />
        </div>

        {/* thresholds */}
        <div className="col gap16">
          <div className="card pad">
            <div className="h-title" style={{ marginBottom: 14 }}>選片門檻 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· thresholds.json</span></div>
            <div className="kv"><span className="k">清晰度下限 · sharpness</span><span className="v">{T.sharpnessFloor} <span className="muted">var</span></span></div>
            <div className="kv"><span className="k">閉眼 · closed-eyes</span><span className="v" style={{ color: 'var(--reject)' }}>絕不留</span></div>
            <div className="kv"><span className="k">留片位置 · burst bias</span><span className="v">後段 late</span></div>
            <div className="kv"><span className="k">keep 評等 · rating ≥</span><span className="v">{T.keepRating}★</span></div>
          </div>
          <div className="card pad">
            <div className="h-title" style={{ marginBottom: 14 }}>光圈分佈 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· aperture</span></div>
            {T.apertures.map(a => <DistBar key={a.k} k={a.k} v={a.v} max={.4} />)}
          </div>
        </div>
      </div>

      {/* distributions row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 14 }}>焦段偏好 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· focal length</span></div>
          {T.focals.map(f => <DistBar key={f.k} k={f.k} v={f.v} max={.45} />)}
        </div>
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 14 }}>ISO 留存分佈 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· keepers by ISO</span></div>
          {T.isoBuckets.map(b => <DistBar key={b.k} k={'ISO ' + b.k} v={b.v} max={.35} />)}
        </div>
      </div>

      {/* presets */}
      <div className="section-head mt24"><h2>風格 Presets</h2><span className="hint">L1 · develop settings → {window.PRESETS.length} looks → XMP</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(208px, 1fr))', gap: 14 }}>
        {window.PRESETS.map(p => (
          <div key={p.id} className="preset-card">
            <div className="preset-sw" style={{ background: p.grad, borderRadius: 0, border: 0, height: 70, position: 'relative' }}>
              {p.sig && <span className="badge" style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(16,13,10,.7)', color: accent, fontSize: 9.5 }}>簽名檔 · signature</span>}
            </div>
            <div className="pad" style={{ padding: '12px 14px' }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{p.name}</div>
                <div className="mono" style={{ fontSize: 11, color: accent }}>{Math.round(p.share*100)}%</div>
              </div>
              <div className="h-sub" style={{ marginBottom: 8 }}>{p.en} · {p.id}.xmp</div>
              <div className="row" style={{ flexWrap: 'wrap', gap: 5 }}>
                {Object.entries(p.settings).slice(0, 4).map(([k, v]) => (
                  <span key={k} className="mono" style={{ fontSize: 10, color: 'var(--ink-3)', background: 'var(--raise)', padding: '2px 6px', borderRadius: 5 }}>{k} {v}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Settings ─────────────────────────────────────────────────────────
function SettingsView({ accent }) {
  const Field = ({ label, en, children }) => (
    <div className="kv" style={{ padding: '12px 0', alignItems: 'center' }}>
      <span className="k" style={{ color: 'var(--ink)', fontSize: 13 }}>{label} <span className="muted mono" style={{ fontSize: 11 }}>· {en}</span></span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>{children}</span>
    </div>
  );
  const Pill = ({ children }) => <span className="badge neutral" style={{ fontSize: 12.5, padding: '5px 12px' }}>{children}</span>;
  // M5: real settings from GET /api/settings (falls back to defaults if absent).
  const S = window.SETTINGS || { cull: {}, score: {}, style: {}, llm: {} };
  const c = S.cull || {}, sc = S.score || {}, st = S.style || {}, llm = S.llm || {};
  return (
    <div className="page fade-in" style={{ maxWidth: 760 }}>
      <div className="section-head"><h2>設定</h2><span className="hint">PHOTOVAULT_* · settings.py</span></div>
      <div className="col gap16">
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 6 }}>選片門檻 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· cull</span></div>
          <Field label="keep 評等" en="keep_rating ≥"><Pill>{c.keep_rating} ★</Pill></Field>
          <Field label="reject 評等" en="reject_rating ≤"><Pill>{c.reject_rating} ★</Pill></Field>
          <Field label="連拍間隔" en="burst_gap_seconds"><Pill>{c.burst_gap_seconds} s</Pill></Field>
          <Field label="連拍最少張數" en="burst_min_frames"><Pill>{c.burst_min_frames}</Pill></Field>
        </div>
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 6 }}>評分 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· score</span></div>
          <Field label="分類器權重" en="w_classifier"><Pill>{sc.w_classifier}</Pill></Field>
          <Field label="taste_vector 權重" en="w_taste"><Pill>{sc.w_taste}</Pill></Field>
          <Field label="keep 門檻" en="keep_above"><span className="badge keep" style={{ padding: '5px 12px' }}>≥ {sc.keep_above}</span></Field>
          <Field label="reject 門檻" en="reject_below"><span className="badge reject" style={{ padding: '5px 12px' }}>&lt; {sc.reject_below}</span></Field>
          <Field label="pHash 去重距離" en="phash_hamming_max"><Pill>{sc.phash_hamming_max}</Pill></Field>
        </div>
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 6 }}>風格分群 <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· style</span></div>
          <Field label="preset 數量 (k)" en="n_presets"><Pill>{st.n_presets}</Pill></Field>
          <Field label="k-means 迭代" en="kmeans_iters"><Pill>{st.kmeans_iters}</Pill></Field>
        </div>
        <div className="card pad">
          <div className="h-title" style={{ marginBottom: 6 }}>本地 LLM <span className="muted mono" style={{ fontWeight: 400, fontSize: 11 }}>· llm</span></div>
          <Field label="模型" en="model"><Pill>{llm.model}</Pill></Field>
          <Field label="主機" en="host"><Pill>{llm.host}</Pill></Field>
          <Field label="溫度" en="temperature"><Pill>{llm.temperature}</Pill></Field>
          <Field label="啟用視覺仲裁" en="enabled">
            {llm.enabled
              ? <span className="badge keep" style={{ padding: '5px 12px' }}><span className="dot-live"></span>ON</span>
              : <span className="badge neutral" style={{ padding: '5px 12px' }}>OFF</span>}
          </Field>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { LearnView, InspectorView, SettingsView });
