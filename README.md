# PhotoVault — 個人化選片 / 預調引擎

本地、離線的選片與預調引擎：從你的 Lightroom 編目檔「學會你的眼睛」，
之後對任何新照片資料夾自動選圖 + 套用你的風格。
目標平台：Apple Silicon (M2) Mac，無 CUDA。語言：Python 3.11+。

完整設計見 [`ARCHITECTURE.md`](./ARCHITECTURE.md)。

## 目前進度

| M | 內容 | 狀態 |
|---|------|------|
| **M1** | 編目檔 → Profile（presets + L2 統計 + 標籤 CSV） | ✅ 完成 |
| **M2** | 預覽抽取 + 像素特徵 + CLIP → taste_vector + Chroma | ✅ 完成 |
| **M3** | 階段 B 評分引擎 + XMP 輸出 | ✅ 完成 |
| **M4** | Gemma：profile.md 生成 + 灰色地帶視覺仲裁 | ✅ 完成 |
| **M5** | FastAPI + Web UI（輸入資料夾路徑、視覺化審片） | ✅ 完成 |

## 安裝

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # M1 核心（純 Python + numpy）
pip install -e ".[pixels]"  # M2 起：rawpy / opencv / mediapipe / open-clip / chroma
pip install -e ".[web]"     # M5：fastapi / uvicorn / Pillow（本地 Web UI）
pip install -e ".[dev]"     # pytest / httpx
```

## LLM：單一多模態 Gemma

本專案用**一個多模態 Gemma 4 模型**（預設 `gemma4:12b`，透過 Ollama / Metal 加速）
同時負責兩件事，不再需要分文字模型 + 視覺模型：

- **階段 A**：讀 L1/L2/L3 統計 → 生成人類看得懂的品味規則書 `profile.md`
- **階段 B**：只對「灰色地帶」那一疊看圖仲裁 keep/reject + 一句理由

沒有 LLM 也能跑：管線會自動退回純 CV+CLIP baseline 並寫入 placeholder `profile.md`。

```bash
# 先在本機跑起 Ollama 並抓模型
ollama pull gemma4:12b
# Apple Silicon 可改用 MLX 變體加速：ollama pull gemma4:12b-mlx
# 覆寫預設（可選）
export PHOTOVAULT_LLM__MODEL=gemma4:12b
export PHOTOVAULT_LLM__HOST=http://localhost:11434
```

> 也可用 **llama.cpp**（OpenAI 相容 API）搭配 Gemma 4 12B QAT + MTP 加速本地部署 —— 見下方「llama.cpp 後端」。

## 使用

```bash
# 階段 A：從編目檔資料夾學一個 Taste Profile
photovault learn <編目檔資料夾> --name 熱茶
photovault learn <編目檔資料夾> --name 熱茶 --no-llm   # 跳過 Gemma

# 檢視學到的 profile
photovault inspect --name 熱茶

# 階段 B：對新照片資料夾評分
photovault apply <新照片資料夾> --name 熱茶

# 開啟本地 Web UI（M5）
photovault serve
```

學完後的產物（見 ARCHITECTURE.md §3）：

```
~/.photovault/profiles/<name>/
├── meta.json          # 來源編目檔、樣本數、建立時間
├── presets/*.xmp      # L1 風格 presets + signature 簽名檔
├── thresholds.json    # L2 統計：keep_rate、光圈/ISO/焦段分佈、連拍留存與位置偏好
├── labels.csv         # (features, label) 訓練資料集
└── profile.md         # Gemma 生成的品味規則書（或 placeholder）
```

## Web UI（M5）

本地、離線的圖形介面：左側列出所有 Taste Profile，右側照工作流程
（檔案總覽 → 選片 → 審片 → 仲裁 → 匯出）操作。所有運算都在本機，照片不出機。

```bash
pip install -e ".[web]"
photovault serve                       # http://127.0.0.1:8000
photovault serve --host 0.0.0.0 --port 9000
```

設計重點：

- **後端** `photovault/api/`：`create_app(settings=None)` 工廠（lazy import
  fastapi/uvicorn/Pillow，所以 `import photovault.core.*` 不需要這些套件）。
  端點 — `GET /api/profiles`、`GET /api/profiles/{name}`、`GET /api/settings`、
  `POST /api/learn`、`POST /api/apply`、`GET /api/thumb`，並把 React SPA
  以靜態檔掛載在 `/`。
- **純 mappers** `photovault/api/mappers.py`：把 `LoadedProfile` / `Settings` /
  `ApplyReport` 轉成前端消費的 JSON 形狀（主要的 TDD 對象）。
- **前端** `photovault/api/static/`：沿用既有設計（CSS/React 元件原封不動），
  只把 mock 資料層換成抓 `/api/*` 的 `pv-boot.jsx`。
- **資料夾選擇**：瀏覽器無法讀本機絕對路徑，所以「學習 / 選片」改用文字框
  輸入資料夾的**絕對路徑**（保留 dropzone 視覺）。
- **縮圖安全**：`/api/thumb` 只服務「最後一次 apply 的資料夾」內、且確實被
  評分過的檔案（resolve + is-within 檢查），其餘一律 403/404，杜絕路徑穿越。

## 設定

所有設定可用環境變數（前綴 `PHOTOVAULT_`，巢狀用 `__`）或 `.env` 覆寫。
見 [`photovault/settings.py`](./photovault/settings.py)：`cull`（選片門檻）、
`style`（presets 數）、`llm`（Gemma 模型/host）。

## 測試

```bash
pytest          # 161 tests，使用合成 .lrcat fixture，無需真實編目檔
```
