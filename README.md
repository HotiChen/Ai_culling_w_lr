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
| M5 | FastAPI + Web UI | ⬜（可選） |

## 安裝

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # M1 核心（純 Python + numpy）
pip install -e ".[pixels]"  # M2 起：rawpy / opencv / mediapipe / open-clip / chroma
pip install -e ".[dev]"     # pytest
```

## LLM：單一多模態 Gemma

本專案用**一個多模態 Gemma 模型**（預設 `gemma3:12b`，透過 Ollama / Metal 加速）
同時負責兩件事，不再需要分文字模型 + 視覺模型：

- **階段 A**：讀 L1/L2/L3 統計 → 生成人類看得懂的品味規則書 `profile.md`
- **階段 B**：只對「灰色地帶」那一疊看圖仲裁 keep/reject + 一句理由

沒有 Ollama 也能跑：管線會自動退回純 CV+CLIP baseline 並寫入 placeholder `profile.md`。

```bash
# 先在本機跑起 Ollama 並抓模型
ollama pull gemma3:12b
# 覆寫預設（可選）
export PHOTOVAULT_LLM__MODEL=gemma3:12b
export PHOTOVAULT_LLM__HOST=http://localhost:11434
```

## 使用

```bash
# 階段 A：從編目檔資料夾學一個 Taste Profile
photovault learn <編目檔資料夾> --name 熱茶
photovault learn <編目檔資料夾> --name 熱茶 --no-llm   # 跳過 Gemma

# 檢視學到的 profile
photovault inspect --name 熱茶

# 階段 B：對新照片資料夾評分（M3 實作中）
photovault apply <新照片資料夾> --name 熱茶
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

## 設定

所有設定可用環境變數（前綴 `PHOTOVAULT_`，巢狀用 `__`）或 `.env` 覆寫。
見 [`photovault/settings.py`](./photovault/settings.py)：`cull`（選片門檻）、
`style`（presets 數）、`llm`（Gemma 模型/host）。

## 測試

```bash
pytest          # 39 tests，使用合成 .lrcat fixture，無需真實編目檔
```
