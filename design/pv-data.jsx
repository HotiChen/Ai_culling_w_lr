// pv-data.jsx — PhotoVault mock data layer
// All numbers/labels mirror the real backend vocabulary:
// Taste Profile, Stage A (learn) / Stage B (apply), keep/maybe/reject bands,
// presets (L1), thresholds (L2/L3), taste_vector, Gemma arbitration, burst dedup.

// ── Taste Profiles (品味檔案) ─────────────────────────────────────────
const PROFILES = [
  {
    id: 'hotcha', name: '熱茶', en: 'Hot Tea', active: true, samples: 1842,
    catalogs: 3, keepRate: 0.22, built: '2026-05-30', accent: '#C98A3C',
    blurb: '暖膚淺景深人像 · 連拍留後段',
  },
  { id: 'street', name: '街拍', en: 'Street', active: false, samples: 980,
    catalogs: 2, keepRate: 0.31, built: '2026-04-18', accent: '#6E8BA8',
    blurb: '高對比抓拍 · 容忍高 ISO' },
  { id: 'mono', name: '黑白', en: 'Mono', active: false, samples: 540,
    catalogs: 1, keepRate: 0.27, built: '2026-03-02', accent: '#9A938A',
    blurb: '高反差黑白 · 重結構' },
];

// ── L1 風格 presets (develop settings → 代表 look) ────────────────────
const PRESETS = [
  { id: 'p1', name: '暖膚人像', en: 'Warm Skin', share: 0.41, sig: true,
    grad: 'linear-gradient(135deg,#3a2417,#9c6b3f 55%,#e6c79a)',
    settings: { Temp: '+18', Tint: '+6', Exposure: '+0.35', Contrast: '+12', Highlights: '−40', Shadows: '+30', Vibrance: '+8' } },
  { id: 'p2', name: '低飽日系', en: 'Muted Film', share: 0.23,
    grad: 'linear-gradient(135deg,#2b2f2c,#7d837a 55%,#cfd2c4)',
    settings: { Temp: '+4', Tint: '−2', Exposure: '+0.20', Contrast: '−8', Highlights: '−20', Shadows: '+40', Vibrance: '−14' } },
  { id: 'p3', name: '暮光暖調', en: 'Dusk Warm', share: 0.16,
    grad: 'linear-gradient(135deg,#241318,#a14b3a 55%,#e8a06a)',
    settings: { Temp: '+26', Tint: '+10', Exposure: '−0.15', Contrast: '+18', Highlights: '−55', Shadows: '+22', Vibrance: '+16' } },
  { id: 'p4', name: '室內燭光', en: 'Candlelit', share: 0.12,
    grad: 'linear-gradient(135deg,#1c130a,#7a4f24 55%,#d7a14e)',
    settings: { Temp: '+34', Tint: '+8', Exposure: '+0.10', Contrast: '+6', Highlights: '−30', Shadows: '+18', Vibrance: '+4' } },
  { id: 'p5', name: '高對比黑白', en: 'Mono Contrast', share: 0.08,
    grad: 'linear-gradient(135deg,#0e0e0e,#6e6e6e 55%,#e8e8e8)',
    settings: { Temp: '0', Tint: '0', Exposure: '+0.25', Contrast: '+34', Highlights: '−60', Shadows: '+44', Saturation: '−100' } },
];

// ── L2/L3 學到的門檻 (thresholds.json) ───────────────────────────────
const THRESHOLDS = {
  keepRate: 0.22,
  keepRating: 3,
  burstRetain: 1.4,           // avg frames kept per burst
  burstPosBias: 'late',       // 留片位置偏好：後段
  sharpnessFloor: 118,        // Laplacian variance
  isoTolerance: 6400,
  closedEyes: 'never-keep',
  apertures: [                // distribution
    { k: 'f/1.4', v: 0.18 }, { k: 'f/2.0', v: 0.34 }, { k: 'f/2.8', v: 0.27 },
    { k: 'f/4.0', v: 0.13 }, { k: 'f/5.6', v: 0.08 },
  ],
  focals: [
    { k: '35mm', v: 0.29 }, { k: '50mm', v: 0.41 }, { k: '85mm', v: 0.22 }, { k: '135mm', v: 0.08 },
  ],
  isoBuckets: [
    { k: '100', v: 0.22 }, { k: '400', v: 0.31 }, { k: '800', v: 0.20 },
    { k: '1600', v: 0.14 }, { k: '3200', v: 0.09 }, { k: '6400', v: 0.04 },
  ],
};

const PROFILE_MD = `# 熱茶 — 品味規則書 / Taste Rule-book

**整體 (Overall).** 你偏好**暖膚調的淺景深人像**：大光圈 (f/2 為主)、
50mm 視角、暖白平衡 (+18 左右)、壓高光、提陰影的柔和對比。

**選片邏輯 (Culling).**
- 留存率約 **22%**——你下手很重，寧缺勿濫。
- **絕不留閉眼**：偵測到閉眼一律淘汰，分數再高也不留。
- 容忍高 ISO（最高約 6400 仍可留），但失焦零容忍（清晰度下限嚴格）。
- 連拍**偏好後段那張**：情緒到位、眼神最定的通常在序列尾端。

**風格 (Look).** 五個代表 preset 中，**暖膚人像**占四成、為簽名檔；
室內場景切到**暮光暖調 / 室內燭光**。黑白只在高反差結構場景偶爾出手。

> 這份規則書同時作為階段 B 灰色地帶仲裁時 Gemma 的 system prompt。`;

// ── Stage-A learn pipeline steps (for the progress view) ─────────────
const LEARN_STEPS = [
  { k: 'scan', zh: '掃描編目檔', en: 'Scan .lrcat (read-only)', detail: '3 catalogs · 24,108 photos' },
  { k: 'style', zh: '風格分群 → presets', en: 'Cluster develop settings', detail: 'k-means → 5 looks + signature' },
  { k: 'cull', zh: 'metadata 選片統計', en: 'L2 cull statistics', detail: 'keep-rate, burst, ISO/aperture' },
  { k: 'preview', zh: '抽取預覽像素', en: 'Extract preview pixels', detail: '.lrprev / Smart Preview' },
  { k: 'features', zh: '清晰 / 閉眼 / CLIP', en: 'Sharpness · blink · CLIP', detail: 'MPS · open-clip' },
  { k: 'train', zh: '訓練分類器 + taste_vector', en: 'Train classifier', detail: 'LogReg → Chroma store' },
  { k: 'gemma', zh: 'Gemma 寫品味規則書', en: 'Gemma writes profile.md', detail: 'gemma4:12b · local' },
];

// ── Stage-B cull pipeline steps ──────────────────────────────────────
const CULL_STEPS = [
  { k: 'scan', zh: '掃描資料夾 · 分連拍組', en: 'Scan folder · group bursts', detail: '36 frames → 8 bursts' },
  { k: 'features', zh: '像素特徵 + embedding', en: 'Pixel features + embedding', detail: 'sharpness · blink · CLIP' },
  { k: 'gate', zh: '技術閘 (閉眼/失焦)', en: 'Technical gate', detail: 'closed-eyes · out-of-focus' },
  { k: 'score', zh: '品味分 + 連拍去重', en: 'Taste score + dedup', detail: 'classifier · taste_vector · pHash' },
  { k: 'arb', zh: 'Gemma 仲裁灰色地帶', en: 'Gemma arbitrates gray-zone', detail: '6 maybe shots' },
];

// ── The new shoot (Stage B input) ────────────────────────────────────
// Burst groups; reuse a seed within a burst to simulate near-duplicates.
// Local placeholder photos (generated) so the design is self-contained / offline-ready.
const IMGMAP = {
  'seedA-1': 'assets/ph1.png', 'seedB-4': 'assets/ph2.png', 'seedC-6': 'assets/ph3.png',
  'seedD-7': 'assets/ph4.png', 'seedE-10': 'assets/ph5.png', 'seedF-11': 'assets/ph6.png',
  'seedF-10': 'assets/ph7.png', 'seedG-13': 'assets/ph8.png', 'seedH-14': 'assets/ph9.png',
};
function img(seed, n) {
  const path = IMGMAP[`${seed}-${n}`] || 'assets/ph1.png';
  // When running as a bundled standalone file, resources are inlined as blob URLs.
  const id = path.replace('assets/', '').replace('.png', '');
  if (typeof window !== 'undefined' && window.__resources && window.__resources[id]) {
    return window.__resources[id];
  }
  return path;
}

// helper to build a frame
let _fid = 0;
function frame(burst, seed, dupOf, o) {
  _fid += 1;
  const id = 'F' + String(_fid).padStart(3, '0');
  return {
    id, burst, seed,
    src: img(seed, dupOf == null ? _fid : dupOf),
    isDup: dupOf != null,
    score: o.score, band: o.band, stars: o.stars,
    sharp: o.sharp, blink: o.blink || false,
    iso: o.iso, ap: o.ap, focal: o.focal, sh: o.sh,
    preset: o.preset, reason: o.reason, picked: o.band === 'keep',
  };
}

const SHOOT = {
  name: '2026-06-12 外拍', en: 'Location Shoot', frames: 36,
  bursts: [
    { id: 'B1', label: '連拍組 1', shots: [
      frame('B1','seedA',null,{score:.84,band:'keep',stars:4,sharp:212,iso:200,ap:'f/2.0',focal:'50mm',sh:'1/640',preset:'暖膚人像',reason:'眼神定、淺景深乾淨；序列中清晰度最高。'}),
      frame('B1','seedA',1,{score:.61,band:'maybe',stars:3,sharp:148,iso:200,ap:'f/2.0',focal:'50mm',sh:'1/640',preset:'暖膚人像',reason:'與留存張近重複 (pHash d=4)，分數略低。'}),
      frame('B1','seedA',1,{score:.38,band:'reject',stars:1,sharp:96,iso:200,ap:'f/2.0',focal:'50mm',sh:'1/500',preset:'暖膚人像',reason:'輕微動態模糊；同組已有更佳張。'}),
    ]},
    { id: 'B2', label: '連拍組 2', shots: [
      frame('B2','seedB',null,{score:.27,band:'reject',stars:0,sharp:64,iso:1600,ap:'f/1.8',focal:'85mm',sh:'1/200',preset:'暖膚人像',reason:'偵測到閉眼 → 技術閘直接淘汰。',blink:true}),
      frame('B2','seedB',4,{score:.79,band:'keep',stars:4,sharp:198,iso:1600,ap:'f/1.8',focal:'85mm',sh:'1/250',preset:'暮光暖調',reason:'眼神到位、膚調溫暖；符合後段留片偏好。'}),
    ]},
    { id: 'B3', label: '單張', shots: [
      frame('B3','seedC',null,{score:.55,band:'maybe',stars:3,sharp:132,iso:800,ap:'f/2.8',focal:'35mm',sh:'1/400',preset:'低飽日系',reason:'構圖中性、表情普通；落在灰色地帶待仲裁。'}),
    ]},
    { id: 'B4', label: '連拍組 3', shots: [
      frame('B4','seedD',null,{score:.88,band:'keep',stars:5,sharp:241,iso:400,ap:'f/2.0',focal:'50mm',sh:'1/800',preset:'暖膚人像',reason:'構圖與情緒俱佳，與 taste_vector 相似度 0.91。'}),
      frame('B4','seedD',7,{score:.52,band:'maybe',stars:2,sharp:120,iso:400,ap:'f/2.0',focal:'50mm',sh:'1/800',preset:'暖膚人像',reason:'近重複；表情稍弱。'}),
      frame('B4','seedD',7,{score:.31,band:'reject',stars:1,sharp:88,iso:400,ap:'f/2.0',focal:'50mm',sh:'1/640',preset:'暖膚人像',reason:'同組去重淘汰。'}),
    ]},
    { id: 'B5', label: '單張', shots: [
      frame('B5','seedE',null,{score:.73,band:'keep',stars:4,sharp:176,iso:3200,ap:'f/1.4',focal:'50mm',sh:'1/125',preset:'室內燭光',reason:'高 ISO 但在容忍範圍；氛圍佳、清晰度過關。'}),
    ]},
    { id: 'B6', label: '連拍組 4', shots: [
      frame('B6','seedF',null,{score:.49,band:'maybe',stars:2,sharp:128,iso:800,ap:'f/2.8',focal:'35mm',sh:'1/500',preset:'低飽日系',reason:'構圖可用但平淡；待 Gemma 視覺仲裁。'}),
      frame('B6','seedF',10,{score:.58,band:'maybe',stars:3,sharp:140,iso:800,ap:'f/2.8',focal:'35mm',sh:'1/500',preset:'低飽日系',reason:'兩張皆灰色地帶，分數接近。'}),
    ]},
    { id: 'B7', label: '單張', shots: [
      frame('B7','seedG',null,{score:.19,band:'reject',stars:0,sharp:52,iso:6400,ap:'f/2.0',focal:'85mm',sh:'1/80',preset:'暮光暖調',reason:'嚴重失焦，低於清晰度下限 (52 < 118)。'}),
    ]},
    { id: 'B8', label: '單張', shots: [
      frame('B8','seedH',null,{score:.66,band:'maybe',stars:3,sharp:152,iso:1600,ap:'f/1.8',focal:'85mm',sh:'1/320',preset:'暖膚人像',reason:'分數略高於門檻邊界；保留待人工確認。'}),
    ]},
  ],
};

// Flatten + derived counts
const ALL_SHOTS = SHOOT.bursts.flatMap(b => b.shots);
const BAND_COUNTS = {
  keep: ALL_SHOTS.filter(s => s.band === 'keep').length,
  maybe: ALL_SHOTS.filter(s => s.band === 'maybe').length,
  reject: ALL_SHOTS.filter(s => s.band === 'reject').length,
  total: ALL_SHOTS.length,
};

Object.assign(window, {
  PROFILES, PRESETS, THRESHOLDS, PROFILE_MD,
  LEARN_STEPS, CULL_STEPS, SHOOT, ALL_SHOTS, BAND_COUNTS,
});
