# TaiwanStockMarketData — 公開行情資料專案

本儲存庫只存放 TWSE / TPEx 官方政府開放資料集所提供的 **日線 OHLCV** 與來源核對資訊，**不可放入** App 原始碼、AI 策略、金鑰、持倉、使用者資訊。

## 免費部署

1. 在個人 GitHub 帳號建立 **Public** repository，名稱必須是 `TaiwanStockMarketData`（與 App 預設同步網址一致）。
2. 將這個 ZIP 的**內容**上傳到新儲存庫的 `main` 分支（含 `.github/workflows` 隱藏目錄）。
3. 進入 **Settings → Pages → Build and deployment → Source**，選 **GitHub Actions**（**不要**選 Deploy from a branch）。
4. 進入 **Actions → Cloud Daily Taiwan Stock OHLCV → Run workflow**，先手動執行一次，確認兩個市場的日期與檔數。工作會將行情提交到 `docs/`，並**在同一次排程直接執行 `deploy-pages` 發布網站**（避免 `GITHUB_TOKEN` 提交不觸發 Pages 建置）。
5. 確認公開索引網址：`https://<GitHub使用者名稱>.github.io/TaiwanStockMarketData/market-index.json`。站點首次部署可能需要一段時間。

排程：台灣時間週一至週五 17:07、19:07、23:07、07:15、08:05（GitHub 排程**不保證準時**）。假日沒有交易時保留最新可驗證日期；不會把請求當日當成交易日。初次部署沒有歷史 90 日，只會從最新快照逐日累積。手機既有 90 日歷史保留。

## 授權與安全

- 上市資料來源：`https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL`，對應政府資料開放平臺資料集 <https://data.gov.tw/dataset/11549>。
- 上櫃資料來源：`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes`，對應政府資料開放平臺資料集 <https://data.gov.tw/dataset/11371>。
- 來源資料集列示「政府資料開放授權條款-第1版」。保留來源、授權與取得資料的原始交易日期，請勿混用非該授權的第三方來源（例如 FinMind/Yahoo）到公開儲存庫。
- `GITHUB_TOKEN` 是 GitHub Actions 內建權杖；**不用建立 PAT 或存入任何簽章金鑰**。若推送時 403，檢查 **Settings → Actions → General → Workflow permissions** 是否允許工作流程寫入（也可能受帳號／組織政策限制）。
- 需注意 GitHub Pages 與公開儲存庫均為任何人可讀；不要提交任何個人資料。

## App 對接資料協定

`market-index.json`: `{schema:1, latest_by_market:{twse:"YYYY-MM-DD",tpex:"..."},days:[{date,path,sha256,markets:{twse:...,tpex:...}}]}`。

`daily/YYYY-MM-DD.json`: `{schema:1,date:"YYYY-MM-DD",markets:{twse:{source,license_dataset,rows:[{code,date,open,high,low,close,volume}]},tpex:...}}`。

App 按 `sha256` 驗證檔案內容，無法取得雲端時仍使用官方來源；不會使用雲端執行 AI 策略，也不會公開任何選股結果。
