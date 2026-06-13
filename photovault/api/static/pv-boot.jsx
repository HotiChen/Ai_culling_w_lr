// pv-boot.jsx — M5 real-data bootstrap.
//
// Fetches the real backend data into the same window.* globals the design's
// components already read, THEN renders <App/>. Also exposes a few async
// helpers the views call (load a profile's detail, run learn / apply). The
// look of the app is unchanged — this only swaps the data source.

async function pvGetJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

// Map a profile-detail response into the THRESHOLDS / PRESETS / PROFILE_MD
// globals the InspectorView reads. The backend already returns the UI shape.
function pvApplyProfileDetail(detail) {
  window.THRESHOLDS = detail.thresholds;
  window.PRESETS = (detail.presets || []).map((p, i) => ({
    id: p.id, name: p.name, en: p.name, sig: !!p.sig,
    settings: p.settings || {},
    // a neutral swatch gradient (real develop look is in p.settings)
    grad: 'linear-gradient(135deg,#2b2620,#5a4a39 55%,#caa978)',
    share: 0,
  }));
  window.PROFILE_MD = detail.profileMd || '';
}

// Load + activate a profile by name (called on first boot and on sidebar switch).
window.pvLoadProfile = async function (name) {
  const detail = await pvGetJSON('/api/profiles/' + encodeURIComponent(name));
  pvApplyProfileDetail(detail);
  return detail;
};

// Run stage B and populate SHOOT / ALL_SHOTS / BAND_COUNTS from the response.
window.pvApply = async function (photoFolder, name, opts) {
  opts = opts || {};
  window.__LAST_FOLDER = photoFolder;
  window.__LAST_PROFILE = name;
  const payload = await pvGetJSON('/api/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      photo_folder: photoFolder, name: name,
      no_llm: !!opts.no_llm, sort: !!opts.sort, report: !!opts.report,
    }),
  });
  window.SHOOT = {
    name: payload.shoot.name, en: payload.shoot.en,
    frames: payload.shoot.frames, bursts: payload.bursts,
  };
  window.ALL_SHOTS = payload.frames;
  window.BAND_COUNTS = payload.bandCounts;
  return payload;
};

// Run stage A (learn). Returns the LearnReport JSON.
window.pvLearn = async function (catalogFolder, name, opts) {
  opts = opts || {};
  return pvGetJSON('/api/learn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      catalog_folder: catalogFolder, name: name, no_llm: !!opts.no_llm,
    }),
  });
};

async function pvBoot() {
  // Settings + profile list are always available.
  try {
    window.SETTINGS = await pvGetJSON('/api/settings');
  } catch (e) { window.SETTINGS = null; }

  let profiles = [];
  try { profiles = await pvGetJSON('/api/profiles'); } catch (e) { profiles = []; }
  window.PROFILES = profiles;

  if (profiles.length) {
    window.__INITIAL_PROFILE = profiles[0].id;
    try { await window.pvLoadProfile(profiles[0].id); } catch (e) {}
  } else {
    window.__INITIAL_PROFILE = null;
  }

  ReactDOM.createRoot(document.getElementById('root')).render(<App />);
}

pvBoot();
