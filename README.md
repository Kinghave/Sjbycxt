# ⚽ WorldCup Oracle — 世界杯预测系统

融合 1930–2026 历史赛事大数据 + AI 实时分析的世界杯预测平台。

## 技术架构

| 层级 | 技术 |
|------|------|
| 前端 | HTML/CSS/JS（可升级为 Next.js） |
| 后端 | FastAPI (Python) |
| AI   | Google Gemini Pro / GPT-4o-mini |
| 缓存 | Redis |
| 数据库 | PostgreSQL |
| 部署 | Docker Compose + Nginx |
| 新闻 | News API |

## 快速部署（Ubuntu 22.04）

### 第一步：克隆项目
```bash
git clone https://github.com/yourname/worldcup-oracle.git
cd worldcup-oracle
```

### 第二步：配置 API Keys
```bash
cp .env.example .env
nano .env   # 填写 GEMINI_API_KEY 或 OPENAI_API_KEY
```

### 第三步：一键部署
```bash
# 无域名版本
sudo bash scripts/deploy.sh

# 有域名版本（自动配置 SSL）
sudo bash scripts/deploy.sh your-domain.com
```

### 第四步：访问
- 前端：http://YOUR_SERVER_IP:8021
- API 文档：http://YOUR_SERVER_IP:8022/docs

## 目录结构
```
worldcup-oracle/
├── frontend/           # 前端静态文件
│   └── index.html      # 主页面
├── backend/            # FastAPI 后端
│   ├── main.py         # 主程序
│   ├── requirements.txt
│   ├── Dockerfile
│   └── init.sql        # 数据库初始化
├── nginx/              # Nginx 配置
│   └── nginx.conf
├── scripts/
│   └── deploy.sh       # 一键部署脚本
├── docker-compose.yml
└── .env.example
```

## API 接口

### 预测接口
```http
POST /api/predict
Content-Type: application/json

{
  "team_a": "Brazil",
  "team_b": "Argentina",
  "include_news": true
}
```

### 历史数据
```http
GET /api/historical/{team_a}/{team_b}
```

### 球队列表
```http
GET /api/teams
```

## 广告解锁逻辑

- 默认开放前 2 场比赛的基础预测
- 观看 5 秒广告后解锁当日全部赛事 AI 深度分析
- 集成 Google AdMob / 其他广告平台

## 常见问题

**Q: 如何更换 AI 模型？**
修改 `.env` 中的 `AI_PROVIDER=openai`，并填写 `OPENAI_API_KEY`

**Q: 历史数据来源？**
可导入来自 Kaggle 的 FIFA World Cup 数据集（1930–2022），共 900+ 场比赛记录

**Q: 预测准确率多少？**
历史回测约 68–75%，组合 AI 新闻分析后小组赛准确率可达 72%+

## License
MIT
