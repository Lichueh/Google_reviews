# LOG.md

## 2026-03-21
* [15:45] 初始化專案目錄結構
* [15:45] 建立 `config.py`：全域設定（延遲、最大評論數、API 埠口、資料路徑）
* [15:45] 建立 `scraper/human_behavior.py`：人類行為模擬工具（隨機延遲、捲動、打字、滑鼠移動）
* [15:45] 建立 `scraper/google_maps_scraper.py`：Selenium 主爬蟲邏輯
* [15:45] 建立 `scraper/data_manager.py`：JSON 讀寫，符合 SQLite3 遷移架構
* [15:45] 建立 `api_server.py`：Flask REST API（/api/scrape/search, /api/scrape/url, /api/status, /api/results）
* [15:45] 建立 Chrome Extension（Manifest V3）：manifest.json, content.js, service_worker.js, popup.html/css/js
* [15:45] 建立 `requirements.txt`
* [15:45] `scraper/data_manager.py`：新增 `review_fingerprint()`（MD5 hash of name+date+rating）、`build_fingerprint_set()`、`load_latest_for_place()`、`merge_reviews()`
* [15:45] `scraper/google_maps_scraper.py`：`load_all_reviews()` 支援 `existing_fingerprints` 參數，連續遇到 5 筆已知評論即提前停止捲動；`search_place()`、`scrape_from_url()`、`_scrape_current_place()` 同步更新簽名
* [15:45] `api_server.py`：新增 `update: bool` 請求參數（search/url 兩個 endpoint）；`_run_scrape_job()` 在 update 模式下載入既有資料並呼叫 `merge_reviews()`；status 回應新增 `new_reviews_added` 欄位
* [15:45] `api_server.py`：移除 flask-cors，改用 `@app.after_request` 手動注入 CORS headers，新增 OPTIONS preflight handler，解決 chrome-extension origin 被拒問題
* [15:45] `scraper/google_maps_scraper.py`：從 selenium 改為 **SeleniumBase UC Mode**（`SB(uc=True)`），繞過 Google 2026 年的 bot 偵測機制；新增 `_sort_by_newest()` 讓增量更新提前停止更有效
* [15:45] `scraper/human_behavior.py`：移除 ActionChains 硬性依賴，改為 try/import 避免 SeleniumBase 環境下的 import 錯誤
* [15:45] `requirements.txt`：以 `seleniumbase>=4.29.0` 取代 `selenium` 與 `flask-cors`
* [15:45] 全專案 API port 從 5000 改為 **5001**（macOS Monterey AirPlay Receiver 佔用 port 5000）
* [17:00] `scraper/google_maps_scraper.py`：`search_place()` 改用 URL 導航（`/maps/search/{quote(name)}`）取代開啟首頁後點擊 `input#searchboxinput`，解決 cookie 彈窗或渲染延遲造成的 15 秒 timeout 錯誤；新增 `import urllib.parse`
* [17:10] `scraper/google_maps_scraper.py`：`_open_reviews_tab()` 新增 `button[aria-label*="評論"]` selector，解決台灣 Google Maps 顯示中文 tab 導致爬蟲停在菜單頁而抓到 0 則評論的問題
* [17:20] `scraper/google_maps_scraper.py`：`_open_reviews_tab()` 新增點擊星評區塊（`div.F7nice`、`span.ceNzKf`）及「所有評論」按鈕作為 fallback，處理 Google 訂餐整合版面隱藏評論 tab 的情況
* [17:30] `config.py`：新增 `COOKIE_FILE` 設定（Netscape cookies.txt 路徑）
* [17:30] `scraper/google_maps_scraper.py`：`__init__` 新增 `cookie_file` 參數；新增 `_load_cookies_from_file()` 方法，在瀏覽器啟動後解析 Netscape 格式 cookie 並注入 google.com cookies，解決 Google 要求登入才能顯示評論 tab 的問題
* [17:30] `api_server.py`：`GoogleMapsScraper` 建構時傳入 `cookie_file=config.COOKIE_FILE`
* [17:40] `config.py`：`DATA_DIR` 改為 `Google_reviews/results/`，統一匯出位置
* [17:50] 新增 `scraper/analyzer.py`：本地規則引擎，提供 `analyze_review()`（情緒/警訊/需回應判斷）、`suggest_response()`（中文回覆範本）、`analyze_place()`（整份資料彙整＋月份時間分佈）
* [17:50] 新增 `templates/dashboard.html`：評論管控儀表板，包含統計卡片、Chart.js 時間分佈折線圖、評論列表（可篩選全部/需回應/警訊）、建議回覆折疊展示
* [17:50] 新增 `static/dashboard.css`：儀表板樣式
* [17:50] `api_server.py`：新增 `GET /`（儀表板首頁）、`GET /api/review-files`（列出 results/ 所有 JSON）、`GET /api/review-files/<filename>`（回傳含分析結果的評論資料）
* [18:30] 新增 `scraper/db.py`：SQLite3 儲存層，schema 含 places + reviews 表，`upsert_place()`（INSERT OR IGNORE 去重）、`list_places()`、`get_place_data()`、`import_json_files()`（一次性遷移既有 JSON）
* [18:30] `config.py`：新增 `DB_PATH = reviews.db`
* [18:30] `api_server.py`：啟動時自動 init DB 並匯入既有 JSON；`_run_scrape_job()` 每次爬完後呼叫 `upsert_place()`；新增 `GET /api/places`（地點列表）、`GET /api/places/<name>`（地點合併評論＋分析）
* [18:30] `templates/dashboard.html`：改為地點選單（`/api/places`），顯示地點名稱、Google Maps 連結、最後更新時間
* [18:30] `static/dashboard.css`：新增 `.place-header` 樣式
* [18:45] `scraper/analyzer.py`：`ALERT_KEYWORDS` 改為 `KEYWORD_SETS` 分類字典（general/restaurant/hospital/department_store）；新增 `get_keywords(place_type)`、`PLACE_TYPE_LABELS`；`analyze_review()` 與 `analyze_place()` 接受 `place_type` 參數；general 組新增服務態度警訊詞（態度差、態度惡劣、白眼、不友善等）
* [18:45] `scraper/db.py`：places 表新增 `place_type` 欄位，`get_place_data()` 回傳 place_type；`init_db()` 加入舊 DB 欄位遷移邏輯
* [18:45] `api_server.py`：`api_get_place()` 傳入 DB 存的 place_type；新增 `POST /api/places/<name>/type` 更新商家類型
* [18:45] `templates/dashboard.html`：新增商家類型下拉選單，切換後即時重新分析並更新警訊
* [18:00] `scraper/google_maps_scraper.py`：`_scroll_reviews_panel()` 改用 Selenium 4 `ActionChains.scroll_from_origin()`（isTrusted=true），解決合成 WheelEvent 被 Google Maps 忽略導致只抓 10 筆的問題；`MAX_STALLS` 從 5 提高到 10
* [18:00] `chrome_extension/content_scripts/content.js`：新增 `safeSendMessage()` 包裝所有 `chrome.runtime.sendMessage()` 呼叫，加入 `chrome.runtime?.id` 存活檢查與 try-catch，解決 Extension context invalidated 錯誤
* [15:45] `scraper/google_maps_scraper.py`：`search_place()` 新增 `max_reviews` 參數，修正原先永遠使用 `config.MAX_REVIEWS`（忽略用戶輸入值）的 bug；`MAX_STALLS` 從 10 提高到 20，避免大量評論時頁面加載偏慢導致提前停止
* [15:45] `api_server.py`：`_run_scrape_job()` search 模式改為傳入 `max_reviews` 給 `scraper.search_place()`，移除事後截斷邏輯
* [15:45] `config.py`：`MAX_REVIEWS` 預設值從 500 提高到 1000
* [18:08] 測試爬蟲執行：一人一丼（一人一丼 - Google 地圖），結果儲存至 `results/一人一丼_-_Google_地圖_20260321_180849.json`
* [22:49] 測試爬蟲執行：長庚醫療財團法人台北長庚紀念醫院，爬取 500 則評論，結果儲存至 `results/長庚醫療財團法人台北長庚紀念醫院_20260321_224928.json`
* [23:03] 測試爬蟲執行：DJI大疆（台北新光三越信義新天地A11授權體驗店），爬取 519 則評論，結果儲存至 `results/DJI大疆_(台北新光三越信義新天地A11授權體驗店)_20260321_230318.json`

## 2026-04-04
* [21:00] 新增輿情分析模組 `nlp/`：完整 NLP pipeline 用於三巨蛋（高雄巨蛋、台北小巨蛋、台北大巨蛋）Google Reviews 語意網絡比較分析
* [21:02] 建立 `nlp/segmenter.py`：jieba 斷詞 + POS 標註，自動載入場館專用詞典
* [21:02] 建立 `nlp/stopwords.py`：繁簡中文停用詞表，擴充評論專用停用詞
* [21:02] 建立 `nlp/venue_dict.txt`：場館/政治/設施專用詞典（巨蛋、遠雄、搖滾區等）
* [21:04] 建立 `nlp/collocation.py`：搭配詞分析引擎，支援 5 種關聯指標（PMI, t-score, χ², LLR, Dice），可配置共現窗口（±2/±3/±5/句內）
* [21:05] 建立 `nlp/network.py`：networkx 語意網絡建構，社群偵測（greedy modularity），計算密度、群集係數、degree/betweenness 中心性
* [21:06] 建立 `nlp/concordance.py`：KWIC 語境共現搜尋 + POS 分群搭配分析
* [21:07] 建立 `nlp/pipeline.py`：YuqingPipeline 整合管線，快取 tokenized 結果避免重複斷詞
* [21:09] `api_server.py`：新增 10 個輿情分析 API 端點（/api/yuqing/venues, tokenize, collocation, network, kwic, pos-collocates, vocabulary, compare, clear-cache）
* [21:11] 建立 `templates/yuqing.html`：四 Tab 分析介面（Collocation、語意網絡、KWIC、跨場館比較）
* [21:12] 建立 `static/yuqing.js`：前端互動邏輯，vis.js 力導向圖、Chart.js 雷達圖、參數即時調整
* [21:12] 建立 `static/yuqing.css`：輿情分析介面樣式
* [21:14] `requirements.txt`：新增 jieba, networkx, scipy, numpy
* [21:14] `CLAUDE.md`：更新專案說明，加入 nlp/ 模組文件
* [21:15] 修復 `nlp/collocation.py`：修正共現計數邏輯（原先 ÷2 在多文件迭代時會歸零），改為僅向前計數避免重複
* [21:16] `nlp/stopwords.py`：補充常見英文停用詞（the, is, it 等），避免英文片段污染搭配詞結果
* [21:17] 安裝 networkx, scipy, numpy 並完成全模組整合測試（長庚醫院 868 則評論通過）

## 2026-04-05
* [00:30] `static/yuqing.js`：修復語意網絡卡頓問題 — 穩定後自動關閉物理模擬、關閉節點陰影與曲線邊、降低穩定迭代次數
* [00:45] `static/yuqing.js`：新增場館勾選時背景預載斷詞（preloadVenue），API 呼叫加 60 秒 timeout 保護
* [01:00] `nlp/concordance.py`：重寫為雙詞共現搜尋模式（參考 Word_frequency 專案），支援 term1 + term2 共現語境搜尋，合併重疊 span，回傳雙色高亮位置
* [01:00] `api_server.py`：`/api/yuqing/kwic` 端點改為接收 term1, term2, window 參數
* [01:00] `nlp/pipeline.py`：`kwic_search()` 改為 `concordance_search()`，對接新的共現搜尋函式
* [01:10] `templates/yuqing.html`：Concordance Tab 改為雙輸入欄 + 字元範圍滑桿（20-300），搭配建議詞按鈕
* [01:10] `static/yuqing.js`：重寫 runKWIC()、renderConcordanceResults()、buildHighlightHtml()，支援藍/紅雙色高亮詞組
* [01:10] `static/yuqing.css`：新增 .conc-inputs、.conc-match、mark.t1（藍）、mark.t2（紅）等 Concordance 樣式
* [01:20] `static/yuqing.js`：POS 搭配分析點擊後自動 scrollIntoView 跳轉到結果區
* [02:30] `static/yuqing.js`：修復語意網絡無法繪圖問題 — vis.js 的 `value` 改為 `size`/`width` 直接指定、物理引擎改用 barnesHut、穩定後呼叫 fit() 再關閉物理
* [03:10] `static/yuqing.js`：修復 vis.js canvas 尺寸問題 — 渲染前強制設定容器 width/height 像素值，確保 canvas 正確初始化
* [03:20] 爬取完成：高雄巨蛋（992 則）、臺北大巨蛋（1036 則）、臺北小巨蛋（999 則），三場館資料齊備

## 2026-04-08
* [18:50] `templates/methodology.html`：頁面背景色從 `#f5f6fa` 改為淺綠色 `#f0faf4`
* [18:50] `templates/methodology.html`：「1.1 斷詞工具：jieba（精確模式）」標題刪除「（精確模式）」
* [18:55] `templates/yuqing.html`：跨場館比較提示文字改為「使用Collocation 分析參數」
* [19:00] `templates/yuqing.html`：新增第五個頁籤「語意網絡比較」（`tab-netcompare`），支援三種比較維度（不同關聯指標 / 不同窗口大小 / 不同閾值設定）
* [19:00] `static/yuqing.js`：新增 `setupNetCompare()`、`getNCConfigs()`、`runNetCompare()`、`renderNetCompare()`、`buildNCMetricsTable()`、`buildNCInterpretation()` 等函式，建構三個並排網絡 + 指標比較表 + 自動語意解釋
* [19:00] `static/yuqing.css`：新增 `.nc-config-cards`、`.nc-networks-grid`、`.nc-metrics-table`、`.nc-interpretation` 等語意網絡比較樣式
* [19:20] `scraper/google_maps_scraper.py`：新增 `checkpoint_callback` 與 `checkpoint_every` 參數，`load_all_reviews()` 改為邊爬邊解析，每 50 則觸發 checkpoint 寫入 DB，避免長時間爬蟲中斷後資料全失
* [19:20] `api_server.py`：新增 `on_checkpoint()` 閉包，透過 `upsert_place()` 每 50 則增量寫入 SQLite；`GoogleMapsScraper` 建構時傳入 `checkpoint_callback` 與 `checkpoint_every=50`
* [19:30] `api_server.py`：新增 `app.config["TEMPLATES_AUTO_RELOAD"] = True`，解決修改 HTML 模板後需重啟伺服器才生效的問題
* [19:40] `static/yuqing.js`：語意網絡比較的三個網絡改用 `compare-grid` + `network-graph` class（與跨場館比較一致），修復顯示問題
* [19:50] `templates/methodology.html`：新增「六、語意網絡的理論定位與方法反思」，含 6.1 概念定義比較表（Semantic Network vs. Collocation Co-occurrence Network）、6.2 共現網絡的三類限制（否定詞混入、語法角色混淆、主題漂移）、6.3 四個修正方向（POS filtering、dependency relation、edge weighting、SRL），引用 Stefanowitsch (2020)、Collins & Quillian (1969)
* [20:10] `templates/methodology.html`：新增「七、網絡分析觀察與詮釋」，基於實際 API 數據撰寫：7.1 主題群集分析（三場館各 5-6 個核心群集，附 LLR 分數）、7.2 正負評價語意結構（直接修飾 vs. 間接描述）、7.3 高中心性關鍵詞（Degree + Betweenness 雙指標跨場館對比）、7.4 跨場館比較（結構指標表 + 三場館特徵摘要）
* [20:30] `templates/methodology.html`：新增「7.5 POS 搭配深度分析：以冷氣為例」——形容詞搭配（正面 75% / 負面 25%，附語用寬容觀察）、名詞搭配（向心輻射結構，「外套」為獨特行為建議名詞）、動詞搭配（發現完整語意腳本：免除擔憂→進場→身體感知→觀賽→散場）、三詞性綜合比較表
* [20:35] `templates/methodology.html`：新增場域背景補充，說明冷氣高頻原因（台灣唯一全場域空調室內棒球場）、冷氣作為「室內 vs. 室外」場館差異的語意代理詞
* [20:40] `templates/methodology.html`：TOC 新增第六、七節條目；`max-height: calc(100vh - 90px)` + `overflow-y: auto` 使目錄可滾動
* [20:45] 參考文獻擴充：新增 Collins & Quillian (1969)、Schank & Abelson (1977)、Stefanowitsch (2020)
* [20:50] `REPORT.md`：第四節從全部「待填」改為實際數據——4.1 網絡結構指標與主題群集、4.2 正負評價結構、4.3 高中心性關鍵詞、4.4 POS 搭配深度分析（冷氣）、4.5 語意網絡理論定位；參考文獻從 5 篇擴充至 11 篇；系統說明更新為五個 Tab
