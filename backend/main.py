"""
世界杯预测系统 — FastAPI 后端
支持：历史数据查询、AI预测（Google Gemini / OpenAI）、新闻分析
"""
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import json
import os
import redis
import hashlib
import asyncio
from datetime import datetime, timedelta

app = FastAPI(title="WorldCup Oracle API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 配置 ────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-pro")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
NEWS_API_KEY   = os.getenv("NEWS_API_KEY", "")
REDIS_URL      = os.getenv("REDIS_URL", "redis://localhost:6379")
AI_PROVIDER    = os.getenv("AI_PROVIDER", "gemini")  # gemini | openai

try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
except Exception:
    r = None

# ─── 模型 ────────────────────────────────────────────────
class PredictionRequest(BaseModel):
    team_a: str
    team_b: str
    match_date: Optional[str] = None
    include_news: bool = True

class PredictionResponse(BaseModel):
    team_a: str
    team_b: str
    win_a_pct: float
    draw_pct: float
    win_b_pct: float
    prediction: str
    confidence: float
    analysis: str
    key_factors: list[str]
    historical_summary: dict
    news_insights: list[str]
    generated_at: str

# ─── 历史数据（简化版，实际应从 PostgreSQL 查询）────────
HISTORICAL_DATA = {
    ("Brazil", "Argentina"): {"h2h": 41, "brazil_wins": 19, "draws": 11, "arg_wins": 11, "brazil_goals": 68, "arg_goals": 52},
    ("Germany", "France"):   {"h2h": 29, "ger_wins": 13, "draws": 7,  "fra_wins": 9,  "ger_goals": 48, "fra_goals": 40},
    ("England", "Portugal"): {"h2h": 24, "eng_wins": 8,  "draws": 9,  "por_wins": 7,  "eng_goals": 32, "por_goals": 31},
    ("Spain",   "Croatia"):  {"h2h": 12, "spa_wins": 7,  "draws": 3,  "cro_wins": 2,  "spa_goals": 26, "cro_goals": 14},
}

def get_historical(team_a: str, team_b: str) -> dict:
    key = (team_a, team_b)
    rev = (team_b, team_a)
    return HISTORICAL_DATA.get(key) or HISTORICAL_DATA.get(rev) or {"h2h": 0, "note": "No historical data found"}

# ─── 新闻抓取 ─────────────────────────────────────────────
async def fetch_news(team_a: str, team_b: str) -> list[str]:
    if not NEWS_API_KEY:
        return ["无法加载最新新闻（未配置 News API Key）"]
    url = (f"https://newsapi.org/v2/everything?"
           f"q={team_a}+{team_b}+football&"
           f"language=zh&sortBy=publishedAt&pageSize=5&"
           f"apiKey={NEWS_API_KEY}")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            data = resp.json()
            return [a["title"] for a in data.get("articles", [])[:3]]
    except Exception:
        return ["新闻加载失败，使用历史数据分析"]

# ─── Gemini AI 预测 ───────────────────────────────────────
async def predict_with_gemini(team_a: str, team_b: str, history: dict, news: list) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API Key 未配置")

    prompt = f"""你是世界顶级足球数据分析师，专注世界杯赛事预测。

比赛：{team_a} vs {team_b}

历史交锋数据：
{json.dumps(history, ensure_ascii=False, indent=2)}

最新相关新闻：
{chr(10).join(f'- {n}' for n in news)}

请输出以下 JSON 格式（仅输出 JSON，不要其他内容）：
{{
  "win_a_pct": 数字(0-100),
  "draw_pct": 数字(0-100),
  "win_b_pct": 数字(0-100),
  "prediction": "预测获胜方名称或平局",
  "confidence": 数字(50-95),
  "analysis": "200字以内中文深度分析",
  "key_factors": ["因素1", "因素2", "因素3"]
}}
确保 win_a_pct + draw_pct + win_b_pct = 100"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    raw = raw.strip().lstrip("```json").rstrip("```").strip()
    return json.loads(raw)

# ─── OpenAI AI 预测 ───────────────────────────────────────
async def predict_with_openai(team_a: str, team_b: str, history: dict, news: list) -> dict:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API Key 未配置")

    prompt = f"""你是世界顶级足球数据分析师。分析以下比赛并给出预测。

比赛：{team_a} vs {team_b}
历史数据：{json.dumps(history, ensure_ascii=False)}
新闻：{'; '.join(news)}

仅输出 JSON：
{{"win_a_pct":数字,"draw_pct":数字,"win_b_pct":数字,"prediction":"名称","confidence":数字,"analysis":"分析","key_factors":["因素1","因素2","因素3"]}}"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": OPENAI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
        )
        data = resp.json()
    raw = data["choices"][0]["message"]["content"].strip().lstrip("```json").rstrip("```").strip()
    return json.loads(raw)

# ─── 路由 ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/api/historical/{team_a}/{team_b}")
async def get_history(team_a: str, team_b: str):
    data = get_historical(team_a, team_b)
    return {"team_a": team_a, "team_b": team_b, "data": data}

@app.post("/api/predict", response_model=PredictionResponse)
async def predict(req: PredictionRequest):
    cache_key = f"pred:{hashlib.md5(f'{req.team_a}:{req.team_b}'.encode()).hexdigest()}"

    # 缓存检查（1小时缓存）
    if r:
        cached = r.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))

    history = get_historical(req.team_a, req.team_b)
    news = await fetch_news(req.team_a, req.team_b) if req.include_news else []

    try:
        if AI_PROVIDER == "openai":
            ai_result = await predict_with_openai(req.team_a, req.team_b, history, news)
        else:
            ai_result = await predict_with_gemini(req.team_a, req.team_b, history, news)
    except Exception as e:
        # Fallback：基于历史数据的简单统计预测
        h = history
        total = h.get("h2h", 0) or 1
        wa = round((h.get("brazil_wins", h.get("ger_wins", h.get("eng_wins", 40))) / total) * 100, 1)
        wd = round((h.get("draws", 20) / total) * 100, 1)
        wb = round(100 - wa - wd, 1)
        ai_result = {
            "win_a_pct": wa, "draw_pct": wd, "win_b_pct": wb,
            "prediction": req.team_a if wa > wb else ("平局" if wd > wb else req.team_b),
            "confidence": 55,
            "analysis": f"基于{total}场历史交锋统计分析（AI 服务暂时不可用）",
            "key_factors": ["历史胜率", "近期状态", "主场优势"]
        }

    result = PredictionResponse(
        team_a=req.team_a, team_b=req.team_b,
        win_a_pct=ai_result["win_a_pct"],
        draw_pct=ai_result["draw_pct"],
        win_b_pct=ai_result["win_b_pct"],
        prediction=ai_result["prediction"],
        confidence=ai_result["confidence"],
        analysis=ai_result["analysis"],
        key_factors=ai_result.get("key_factors", []),
        historical_summary=history,
        news_insights=news,
        generated_at=datetime.utcnow().isoformat()
    )

    # 写入缓存
    if r:
        r.setex(cache_key, 3600, json.dumps(result.dict(), ensure_ascii=False))

    return result

@app.get("/api/teams")
async def get_teams():
    teams = [
        {"name": "Brazil", "cn": "巴西", "flag": "🇧🇷", "rank": 1},
        {"name": "Argentina", "cn": "阿根廷", "flag": "🇦🇷", "rank": 2},
        {"name": "France", "cn": "法国", "flag": "🇫🇷", "rank": 4},
        {"name": "England", "cn": "英格兰", "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "rank": 5},
        {"name": "Spain", "cn": "西班牙", "flag": "🇪🇸", "rank": 7},
        {"name": "Germany", "cn": "德国", "flag": "🇩🇪", "rank": 3},
        {"name": "Portugal", "cn": "葡萄牙", "flag": "🇵🇹", "rank": 6},
        {"name": "Netherlands", "cn": "荷兰", "flag": "🇳🇱", "rank": 9},
        {"name": "Belgium", "cn": "比利时", "flag": "🇧🇪", "rank": 10},
        {"name": "Morocco", "cn": "摩洛哥", "flag": "🇲🇦", "rank": 11},
        {"name": "Japan", "cn": "日本", "flag": "🇯🇵", "rank": 12},
        {"name": "Croatia", "cn": "克罗地亚", "flag": "🇭🇷", "rank": 8},
    ]
    return {"teams": teams, "total": len(teams)}
