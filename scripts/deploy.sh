#!/bin/bash
# ============================================================
# WorldCup Oracle — Ubuntu 一键部署脚本
# 适用于 Ubuntu 22.04 LTS
# 使用方法: sudo bash deploy.sh
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo -e "\n${GREEN}====== WorldCup Oracle 部署开始 ======${NC}\n"

# 检查是否为 root
[[ $EUID -eq 0 ]] || err "请使用 sudo 运行此脚本"

# 1. 系统更新
log "更新系统包..."
apt-get update -q && apt-get upgrade -yq

# 2. 安装 Docker
if ! command -v docker &> /dev/null; then
    log "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker && systemctl start docker
    log "Docker 安装完成: $(docker --version)"
else
    log "Docker 已安装: $(docker --version)"
fi

# 3. 安装 Docker Compose
if ! command -v docker-compose &> /dev/null; then
    log "安装 Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    log "Docker Compose 安装完成"
fi

# 4. 配置防火墙
log "配置 UFW 防火墙..."
ufw allow OpenSSH
ufw allow 8021/tcp
ufw allow 8022/tcp
ufw --force enable
log "防火墙配置完成"

# 5. 生成 .env 配置
if [ ! -f .env ]; then
    log "生成 .env 配置文件..."
    DB_PWD=$(openssl rand -base64 16)
    cat > .env << EOF
# AI 配置（至少填写一个）
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
NEWS_API_KEY=your_newsapi_key_here
AI_PROVIDER=gemini

# 数据库
DB_PASSWORD=${DB_PWD}

# 域名（可选）
DOMAIN=your-domain.com
EOF
    warn "已生成 .env 文件，请编辑填写 API Key: nano .env"
fi

# 6. 构建并启动
log "构建 Docker 镜像..."
docker-compose build --no-cache

log "启动所有服务..."
docker-compose up -d

# 7. 等待服务就绪
log "等待服务启动..."
sleep 10

# 健康检查
if curl -sf http://localhost:8022/health > /dev/null; then
    log "后端 API 服务正常运行 ✓"
else
    warn "后端服务可能未完全就绪，请检查: docker-compose logs backend"
fi

# 8. 设置 SSL（Let's Encrypt，需要域名）
setup_ssl() {
    local domain=$1
    log "为 $domain 申请 SSL 证书..."
    apt-get install -yq certbot python3-certbot-nginx
    docker-compose stop frontend
    certbot certonly --standalone -d $domain --non-interactive --agree-tos -m admin@$domain
    mkdir -p nginx/ssl
    cp /etc/letsencrypt/live/$domain/fullchain.pem nginx/ssl/
    cp /etc/letsencrypt/live/$domain/privkey.pem nginx/ssl/
    docker-compose start frontend
    # 自动续期
    echo "0 0,12 * * * root certbot renew --quiet && docker-compose restart frontend" >> /etc/crontab
    log "SSL 配置完成"
}

# 如果传入域名参数则配置 SSL
[ -n "$1" ] && setup_ssl "$1"

# 9. 配置开机自启
log "配置开机自启..."
cat > /etc/systemd/system/worldcup-oracle.service << EOF
[Unit]
Description=WorldCup Oracle
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=$(pwd)
ExecStart=/usr/local/bin/docker-compose up
ExecStop=/usr/local/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable worldcup-oracle
log "开机自启配置完成"

echo -e "\n${GREEN}====== 部署完成！======${NC}"
echo -e "前端访问: ${GREEN}http://$(curl -s ifconfig.me):8021${NC}"
echo -e "API 文档: ${GREEN}http://$(curl -s ifconfig.me):8022/docs${NC}"
echo -e "\n常用命令:"
echo -e "  查看日志: ${YELLOW}docker-compose logs -f${NC}"
echo -e "  重启服务: ${YELLOW}docker-compose restart${NC}"
echo -e "  停止服务: ${YELLOW}docker-compose down${NC}"
echo -e "  更新部署: ${YELLOW}git pull && docker-compose up -d --build${NC}\n"
