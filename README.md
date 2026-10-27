# Bitget 即時強弱雷達

Bitget USDT 永續的即時掃描器：熱門前 50（依 24h 成交額）外加 CLUSDT / NATGASUSDT / MUUSDT。

單一 HTML 檔，無建置流程、無相依套件、**不含也不需要任何 API key**。所有資料由瀏覽器直接向 Bitget 公開 API 取得。

## 用法

- **本機**：直接用瀏覽器開 `index.html`。
- **上架**：把 `index.html` 放到任何靜態空間（GitHub Pages、Cloudflare Pages、Netlify）即可從手機開啟。

## 內容

| 欄位 | 說明 |
|---|---|
| 推薦指數 | 0–100，附方向（做多／做空／觀望），<25 一律標觀望 |
| 相對強度 | 對 BTC、對 ETH 的 24h 超額報酬，分開顯示 |
| 買方主導 | 24h 區間位置 0.65 ＋ 最佳買賣盤量失衡 0.35 |
| 資金費率 | 每 8h 與年化，**反向計分** |
| 散戶情緒 | 多倉帳戶比，**反向計分** |
| 成交量能 | 24h 成交額、未平倉名目值、轉手率 |

展開任一列可看六個成分的 −1…+1 拆解，以及最近 100 筆成交的主動買賣量。點幣種名開 TradingView 的 `BITGET:<SYM>.P` 盤面。

## 資料來源

Bitget 公開 API，皆為免金鑰端點：

- `/api/v2/mix/market/tickers` — 價格、24h、成交額、資金費率、未平倉、盤口
- `/api/v2/mix/market/account-long-short` — 散戶多空帳戶比
- `/api/v2/mix/market/fills` — 近期成交（含主動方向）

## 已知限制

1. **CL / NATGAS / MU 的 `fundingRate` 恆為 0** —— 傳統市場永續沒有資金費率機制，該成分標為 N/A 並退出加權。
2. 散戶情緒是**帳戶數**比例，不是倉位金額比例。
3. 盤口失衡是瞬時值，在薄盤上會出現極端讀數，所以只佔「買方主導」的 0.35；展開列的主動買賣量較可靠。
4. **Bitget 的 CDN 會對特定 URL 供應過期快取。** 本頁每個請求都帶時間戳破快取，並顯示資料時間與落後秒數；超過 120 秒會變紅示警。

## 這不是什麼

這是**掃描器**，用來從 53 支縮小到少數值得細看的標的。它不產出限價／停損／目標／部位。推薦指數高只代表「現在值得看」，不代表「現在可以進」。非投資建議。

## K 線鏡像（給排程用，2026-10-27 起）

`.github/workflows/candles.yml` 每小時在 GitHub Actions 上向 Bitget 抓 K 線，驗證後寫入 **`data` 分支**：

- `BTCUSDT / ETHUSDT / CLUSDT / NATGASUSDT / MUUSDT` 的 `_1D.csv`、`_4H.csv`（每小時）
- 16 支觀察名單的 `_1W.csv`（每週一）
- `status.json`：每個檔案的筆數、最後一根、檢查結果

欄位 `ts,open,high,low,close,volume`，ts 為開盤時間（毫秒），只含已收盤 K，日／週線以 UTC+8 00:00 為界。
驗證沒過（時間缺口、open≠前收、日界錯位）就不覆寫舊檔。

`tools/` 裡是排程每天跑的固定腳本：`verdict.py`、`verdict_tradfi.py`、`levels.py`（判定與水位）、
`ledger.py`（紀錄簿新增與結算，含重複單判定）、`check_fresh.py`（資料新鮮度）。
規則凍結，改動以 git 紀錄為準。
