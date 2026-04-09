# CLAUDE.md

## 專案簡介

Google Reviews 輿情分析系統，包含兩大模組：

1. **爬蟲模組**（`scraper/`）：SeleniumBase UC Mode 爬取 Google Maps 評論
2. **輿情分析模組**（`nlp/`）：文本前處理、搭配詞分析、語意網絡建構、KWIC 語境分析

### 目錄結構

| 目錄/檔案 | 說明 |
|-----------|------|
| `api_server.py` | Flask REST API 主入口（爬蟲 + 輿情分析路由） |
| `config.py` | 全域設定 |
| `scraper/` | 爬蟲核心（google_maps_scraper, db, analyzer, data_manager） |
| `nlp/` | NLP 分析模組 |
| `nlp/segmenter.py` | jieba 斷詞 + POS 標註 |
| `nlp/stopwords.py` | 繁簡中文停用詞表 |
| `nlp/venue_dict.txt` | 場館專用自訂詞典 |
| `nlp/collocation.py` | 共現分析引擎（PMI, t-score, χ², LLR, Dice） |
| `nlp/network.py` | networkx 語意網絡建構 + 指標計算 |
| `nlp/concordance.py` | KWIC 語境共現 + POS 搭配分析 |
| `nlp/pipeline.py` | 分析管線整合器（含快取） |
| `templates/yuqing.html` | 輿情分析前端（vis.js 網絡 + Chart.js） |
| `static/yuqing.js` | 前端互動邏輯 |
| `static/yuqing.css` | 前端樣式 |
| `results/` | 爬蟲結果 JSON |
| `reviews.db` | SQLite3 資料庫 |

### 執行方式

詳見 `LOG.md`

## 開發日誌規範

`LOG.md` 是用來紀錄程式的開發與執行。如果程式碼有主要的變動，請用日期與時間的方式點列紀錄，格式如下：

```
## 2026-03-06
* [HH:MM] activity
* [HH:MM] activity
```
