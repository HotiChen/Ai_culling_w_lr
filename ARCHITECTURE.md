# PhotoVault — 個人化選片 / 預調引擎

> 一個**本地、離線**的應用程式：從你的 Lightroom 歷史編目檔「學會你的眼睛」，
> 之後對任何新照片資料夾自動選圖 + 套用你的風格。
> 目標平台：**Apple Silicon (M2) Mac，無 CUDA**。語言：Python 3.11+。

-----

## 0. 核心概念

整個系統圍繞一個持久化的產物 —— **Taste Profile（品味檔案）**。

```
階段 A（學習，一次性）   編目檔資料夾  ──►  [學習管線]  ──►  Taste Profile（存檔）
階段 B（套用，可反覆）   新照片資料夾  ──►  [評分管線] ◄── 讀取 Taste Profile  ──►  選好的圖 + XMP
```

這個分離正是你要的「乾淨啟動 → 學一次 → 之後一直用」。Profile 一旦建好，
階段 B 完全不需要再碰編目檔。

### 三層邏輯（決定每一層的資料來源）

|層               |內容                        |階段 A 來源                          |需要原始檔？ |
|----------------|--------------------------|---------------------------------|-------|
|L1 風格           |develop settings → presets|編目檔 SQLite                       |❌ 不需要  |
|L2 metadata 選片邏輯|光圈/ISO/焦段/連拍/留退率          |編目檔 SQLite                       |❌ 不需要  |
|L3 像素品味         |清晰/閉眼/構圖/美感               |**預覽快取**（Smart Preview / .lrprev）|❌ 用預覽即可|


> **原始檔已刪也能學**：L1、L2 本來就只住在編目檔；L3 改讀預覽快取的像素。
> 階段 B 處理的是「新拍的照片」，那些原檔本來就在你手上，所以是全畫質分析。

-----

## 1. 技術選型（皆為 Apple Silicon 友善、可離線）

|用途             |套件                                           |備註                                            |
|---------------|---------------------------------------------|----------------------------------------------|
|編目檔讀取          |`sqlite3`（標準庫）                               |唯讀 `immutable=1`，不動原檔                         |
|RAW 解碼         |`rawpy`(libraw) + `Pillow`                   |階段 B 新照片                                      |
|預覽抽取           |自製 `.lrprev`→JPEG / Smart Preview DNG→`rawpy`|階段 A                                          |
|清晰度            |`opencv-python`（Laplacian variance）          |CPU 即可                                        |
|臉/閉眼           |`mediapipe` Face Mesh（EAR 眨眼偵測）              |M2 CPU 順暢                                     |
|重複片            |`imagehash`（pHash）                           |連拍去重                                          |
|語意/美感 embedding|`open-clip-torch`，**PyTorch MPS** backend    |可選 `mlx-clip` 更快                              |
|向量庫            |`chromadb`（本地持久化）                            |存 keeper embeddings                           |
|表格學習器          |`scikit-learn`（LogReg / GBDT）                |學 metadata 決策邊界                               |
|**本地 LLM**     |**Ollama** 或 **llama.cpp**（Metal 加速）         |**單一多模態 `gemma4:12b`**（文字＋視覺共用）|
|設定/驗證          |`pydantic-settings`                          |                                              |
|CLI            |`typer`                                      |階段一介面                                         |
|Web UI（可選）     |`FastAPI` + 簡易前端                             |你熟的 stack，M5 再做                               |
|測試             |`pytest`，TDD，合成編目檔 fixture                   |                                              |


> **MPS 注意**：CLIP 用 `torch.device("mps")`。首次跑會慢（編譯 kernel），之後正常。
> 若遇到 MPS 不支援的 op，設 `PYTORCH_ENABLE_MPS_FALLBACK=1` 退回 CPU。

-----

## 2. 本地 LLM 的角色（關鍵設計）

> **模型選擇：單一多模態 Gemma 4 12B（`gemma4:12b`）。**
> Gemma 4 的 12B 版本本身具備視覺能力，**同一個模型**就能同時做文字推理與看圖判斷，
> 因此不再需要原本「文字模型 + 視覺模型」兩支的設計。可用
> `PHOTOVAULT_LLM__MODEL` 覆寫成其他 tag（Apple Silicon 可用 `gemma4:12b-mlx`）。
> 用 `photovault doctor` / `GET /api/llm` 確認 host 通、且該 tag 真的已安裝 ——
> 否則 LLM 失敗只會表現成一份 placeholder `profile.md`，很難察覺。
> 部署可選 **Ollama**（`/api/generate`，預設）或 **llama.cpp** server
> （OpenAI 相容 `/v1/chat/completions`，支援 QAT + MTP 加速、mmproj 多模態）。

LLM **不**逐張看圖（太慢，M2 上跑視覺模型一張要數秒）。它只做兩件「判斷」：

- **階段 A — 寫出你的品味規則書**：Gemma 讀完 L1/L2/L3 的統計結果，
  生成一份人類看得懂的 `profile.md`（例：「偏好 f/2 淣景深、暖膚調、連拍留偏後段、
  容忍高 ISO 但絕不留閉眼」）。這份同時當作階段 B 的 LLM system prompt。
- **階段 B — 只仲裁「模棱兩可」那一疊**：清楚該留 / 該丟的，由快速的 CV+CLIP 直接決定；
  只有分數落在灰色地帶的，才送 **同一個 Gemma 模型**搭配規則書去看圖做最終判斷 + 一句理由。

> 這樣設計：**沒有 LLM 也能跑**（純 CV+CLIP baseline，且自動寫 placeholder `profile.md`），
> Gemma 是可插拔的「可解釋仲裁者」。速度與成本（零 API 費用、客戶照片不出本機）都顧到。
> 實作見 `core/judge/ollama_client.py` 的 `GemmaJudge`（`write_profile` / `arbitrate`）。

-----

## 3. Taste Profile 產物結構

```
~/.photovault/profiles/<name>/
├── meta.json          # 版本、來源編目檔清單、樣本數、建立時間
├── presets/*.xmp      # L1 風格 presets（k 種代表 look + 一個 signature 簽名檔）
├── thresholds.json    # L2/L3 學到的門檻：清晰度下限、ISO 容忍、連拍留存比、留片位置偏好
├── labels.csv         # (features, label) 訓練資料集（M1）
├── taste_vector.npy   # L3 keeper 平均 CLIP 方向向量（M2）
├── classifier.pkl     # keep/reject 分類器（sklearn）（M2）
├── chroma/            # keeper embeddings（相似度查詢用）（M2）
└── profile.md         # Gemma 生成的品味規則書（也是 B 階段 system prompt）
```

-----

## 4. 模組架構

```
photovault/
├── settings.py         # pydantic-settings：cull / style / llm 設定
├── core/
│   ├── catalog/        # 編目檔讀取
│   │   ├── reader.py       # open_ro / find_catalogs / schema introspection / APEX 轉換
│   │   ├── style.py        # develop settings → 分群（自製 k-means）→ presets / XMP
│   │   ├── cull_logic.py   # EXIF/連拍 → L2 統計 + keep/reject 標籤
│   │   └── labels.py        # 匯出 (features, label) CSV 供訓練
│   ├── preview/        # Smart Preview DNG + .lrprev JPEG 抽取（M2）
│   ├── features/       # sharpness / mediapipe_blink / clip_embed / exif / phash（M2）
│   ├── profile/        # build / save / load Taste Profile（pydantic models）
│   ├── learn/          # 階段 A 管線：catalogs → Taste Profile
│   ├── score/          # 階段 B 評分 + 連拍去重 + keep/maybe/reject 分流（M3）
│   ├── judge/          # Ollama Gemma client：profile.md 生成 + 視覺仲裁 + status() 健檢
│   └── export/         # XMP sidecar 寫入 / 資料夾分流 / HTML 報告（M3）
├── cli/                # typer：photovault learn | inspect | apply | serve
├── api/                # FastAPI（M5）：app.py（factory）+ mappers.py（純）+ static/（React SPA）
└── tests/              # 每模組對應 test_*.py，合成 .lrcat fixture（make_fake.py）
```

**設計原則**：`core/` 是純函式庫、UI 無關。CLI 與 Web 都只是薄包裝。

-----

## 5. 兩條管線的資料流

### 階段 A：`photovault learn <編目檔資料夾> --name 熱茶`

1. `catalog.reader` 掃描所有 `.lrcat`（唯讀）。
1. `catalog.style` → 產 presets；`catalog.cull_logic` → 產 L2 統計 + 每張標籤。
1. `preview` 對每張 keeper 取出像素 → `features` 算 sharpness / blink / CLIP embedding。（M2）
1. `learn` 用 (keeper vs reject) 訓練 classifier、算 taste_vector、推 L3 門檻；存進 `chroma`。（M2）
1. `judge` 把 L1/L2/L3 統計丟給 **Gemma** → 寫 `profile.md`。
1. `profile.save()` 落地整包產物。

### 階段 B：`photovault apply <新照片資料夾> --name 熱茶`

1. 掃描新資料夾，依 EXIF 拍攝時間分連拍組；`features` 算每張像素特徵 + embedding。
1. `score`：
- **技術閘**（thresholds）：閉眼 / 嚴重失焦 → 直接淘汰。
- **品味分**：classifier 機率 + 與 taste_vector 相似度。
- **連拍去重**：組內 pHash 去近重複，依分數留前 K 張（K 對齊你歷史留存比）。
1. 灰色地帶 → `judge` 用 **Gemma 看圖仲裁**（可 `--no-llm` 關閉）。
1. `export`：
- 每張寫 **XMP sidecar**：星等 + 旗標 + 最匹配的 develop preset。
- 選配：分流到 `keep/ maybe/ reject/` 子資料夾。
- 產出 HTML 審片報告（縮圖 + 分數 + 理由）。
  → 你把資料夾 import 進 Lightroom，已經選好且預調好了。

-----

## 6. 開發里程碑（TDD，逐步可交付）

|M     |內容                                        |狀態                     |
|------|------------------------------------------|-----------------------|
|**M1**|編目檔 → Profile（presets + L2 統計 + 標籤 CSV）   |✅ **完成**（reader/style/cull_logic/labels/profile/learn/CLI + 39 tests）|
|**M2**|預覽抽取 + 像素特徵 + CLIP → taste_vector + Chroma|✅ **完成**（preview/features(sharpness/blink/clip/phash/exif)/taste_vector/classifier/vectorstore；Protocol 注入 + lazy import；+43 tests）|
|**M3**|階段 B 評分引擎 + XMP 輸出（先不接 LLM）               |✅ **完成**（score(gate/blend/bands)/dedup/export(xmp/report/foldering)/apply 管線/CLI；+33 tests）|
|**M4**|接 Ollama Gemma：profile.md 生成 + 灰色地帶視覺仲裁   |✅ **完成**（injectable judge + fallback；`apply_to_folder` arbitrates maybe band；`learn_from_folder` writes profile.md；CLI wired + `n_arbitrated` surfaced；133 tests）|
|**M5**|FastAPI + Web UI（輸入資料夾路徑、視覺化審片）        |✅ **完成**（`create_app(settings)` factory，lazy fastapi/uvicorn/Pillow；純 `mappers.py` 把 LoadedProfile/Settings/ApplyReport → 設計的 UI JSON；端點 `/api/profiles[/{name}]`、`/api/settings`、`/api/learn`、`/api/apply`、`/api/thumb`（路徑穿越防護）+ 靜態 SPA；前端 `pv-boot.jsx` 改抓真資料；CLI `photovault serve`；161 tests）|


> 每個 `core/` 模組配合成 fixture 編目檔（`tests/make_fake.py`）做 golden-file 測試。

-----

## 7. M1 已交付內容

- `core/catalog/reader.py`：唯讀開檔、`.lrcat` 搜尋、schema 自省、APEX→f-number/快門 轉換、
  develop-settings 文字解析。
- `core/catalog/cull_logic.py`：keep/reject 標籤規則、連拍分組、L2 統計（留存率、光圈/ISO/焦段分佈、
  連拍留存與「留片位置」偏好）。
- `core/catalog/style.py`：develop settings → 標準化 → 自製 k-means 分群 → 代表 preset（medoid）
  + median 簽名檔 → XMP 輸出。
- `core/catalog/labels.py`：匯出 `(features, label)` CSV 訓練資料集。
- `core/profile/`：pydantic 模型 + 完整 save/load。
- `core/judge/ollama_client.py`：`GemmaJudge`（單一多模態 Gemma，文字＋視覺）。
- `core/learn/pipeline.py`：階段 A 一條龍 `learn_from_folder()`。
- `cli/main.py`：`photovault learn | inspect | apply`。
- `tests/`：39 個測試，含合成 `.lrcat` fixture。
