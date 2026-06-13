// pv-data.jsx — REAL data layer (M5).
//
// In the standalone design this file held MOCK arrays. In the served app the
// real data is fetched from the FastAPI backend by pv-boot.jsx and assigned to
// the same window.* globals BEFORE the app renders. This file now only:
//   * keeps the cosmetic pipeline step lists (LEARN_STEPS / CULL_STEPS) — these
//     are static UI labels, not data, so they stay here verbatim;
//   * seeds SAFE EMPTY defaults for the data globals so components never crash
//     if they read a global before an apply/learn has populated it.
//
// Everything else (PROFILES, THRESHOLDS, PRESETS, PROFILE_MD, SHOOT,
// ALL_SHOTS, BAND_COUNTS) is overwritten with real backend data by pv-boot.jsx.

// ── Stage-A learn pipeline steps (cosmetic progress labels) ──────────
const LEARN_STEPS = [
  { k: 'scan', zh: '掃描編目檔', en: 'Scan .lrcat (read-only)', detail: '' },
  { k: 'style', zh: '風格分群 → presets', en: 'Cluster develop settings', detail: 'k-means → looks + signature' },
  { k: 'cull', zh: 'metadata 選片統計', en: 'L2 cull statistics', detail: 'keep-rate, burst, ISO/aperture' },
  { k: 'preview', zh: '抽取預覽像素', en: 'Extract preview pixels', detail: '.lrprev / Smart Preview' },
  { k: 'features', zh: '清晰 / 閉眼 / CLIP', en: 'Sharpness · blink · CLIP', detail: 'MPS · open-clip' },
  { k: 'train', zh: '訓練分類器 + taste_vector', en: 'Train classifier', detail: 'LogReg → Chroma store' },
  { k: 'gemma', zh: 'Gemma 寫品味規則書', en: 'Gemma writes profile.md', detail: 'gemma4:12b · local' },
];

// ── Stage-B cull pipeline steps (cosmetic progress labels) ───────────
const CULL_STEPS = [
  { k: 'scan', zh: '掃描資料夾 · 分連拍組', en: 'Scan folder · group bursts', detail: '' },
  { k: 'features', zh: '像素特徵 + embedding', en: 'Pixel features + embedding', detail: 'sharpness · blink · CLIP' },
  { k: 'gate', zh: '技術閘 (閉眼/失焦)', en: 'Technical gate', detail: 'closed-eyes · out-of-focus' },
  { k: 'score', zh: '品味分 + 連拍去重', en: 'Taste score + dedup', detail: 'classifier · taste_vector · pHash' },
  { k: 'arb', zh: 'Gemma 仲裁灰色地帶', en: 'Gemma arbitrates gray-zone', detail: 'maybe shots' },
];

// ── Safe empty defaults (overwritten by pv-boot.jsx with real data) ──
const PROFILES = [];
const PRESETS = [];
const THRESHOLDS = {
  keepRate: 0, keepRating: 3, burstRetain: 0, burstPosBias: 'even',
  sharpnessFloor: null, isoTolerance: null,
  apertures: [], focals: [], isoBuckets: [],
};
const PROFILE_MD = '';
const SHOOT = { name: '—', en: '', frames: 0, bursts: [] };
const ALL_SHOTS = [];
const BAND_COUNTS = { keep: 0, maybe: 0, reject: 0, total: 0 };

Object.assign(window, {
  PROFILES, PRESETS, THRESHOLDS, PROFILE_MD,
  LEARN_STEPS, CULL_STEPS, SHOOT, ALL_SHOTS, BAND_COUNTS,
});
