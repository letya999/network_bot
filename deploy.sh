#!/bin/bash
set -euo pipefail

# NetworkBot Production Deployment Script for Digital Ocean
# Usage: ./deploy.sh [setup|deploy|migrate|ssl|logs|status]

APP_NAME="network_bot"
COMPOSE_FILE="docker-compose.prod.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $1"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $1"; }

check_env() {
    if [ ! -f .env ]; then
        error ".env file not found!"
        echo "Copy .env.example to .env and fill in the values:"
        echo "  cp .env.example .env"
        echo "  nano .env"
        exit 1
    fi

    # Check required vars
    local required_vars=("POSTGRES_USER" "POSTGRES_PASSWORD" "TELEGRAM_BOT_TOKEN")
    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=your_" .env; then
            error "Required variable ${var} not set in .env"
            exit 1
        fi
    done
    log "Environment check passed"
}

setup() {
    log "Setting up production environment..."

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        log "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        rm get-docker.sh
        systemctl enable docker
        systemctl start docker
    fi

    # Install docker-compose plugin if not present
    if ! docker compose version &> /dev/null; then
        log "Installing Docker Compose..."
        apt-get update && apt-get install -y docker-compose-plugin
    fi

    # Create directories
    mkdir -p nginx/conf.d certbot/www certbot/conf

    # Create swap if < 2GB RAM
    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    if [ "$TOTAL_MEM" -lt 2048 ] && [ ! -f /swapfile ]; then
        log "Creating 2GB swap file..."
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi

    # Configure firewall
    if command -v ufw &> /dev/null; then
        log "Configuring firewall..."
        ufw allow 22/tcp
        ufw allow 80/tcp
        ufw allow 443/tcp
        ufw --force enable
    fi

    log "Setup complete!"
}

ssl() {
    local domain="${1:-}"
    if [ -z "$domain" ]; then
        error "Usage: ./deploy.sh ssl <your-domain.com>"
        exit 1
    fi

    log "Obtaining SSL certificate for ${domain}..."

    # First, start nginx without SSL
    docker compose -f ${COMPOSE_FILE} up -d nginx

    # Get certificate
    docker compose -f ${COMPOSE_FILE} run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        -d "${domain}" \
        --email "admin@${domain}" \
        --agree-tos \
        --no-eff-email

    # Restart nginx with SSL
    docker compose -f ${COMPOSE_FILE} restart nginx

    log "SSL certificate obtained for ${domain}"
}

migrate() {
    log "Running database migrations..."
    docker compose -f ${COMPOSE_FILE} --profile migrate run --rm migrate
    log "Migrations complete"
}

deploy() {
    check_env

    log "Deploying ${APP_NAME}..."

    # Build images
    log "Building images..."
    docker compose -f ${COMPOSE_FILE} build

    # Start infrastructure first
    log "Starting database and redis..."
    docker compose -f ${COMPOSE_FILE} up -d db redis
    sleep 5

    # Run migrations
    migrate

    # Start all services
    log "Starting all services..."
    docker compose -f ${COMPOSE_FILE} up -d

    log "Deployment complete!"
    status
}

status() {
    log "Service status:"
    docker compose -f ${COMPOSE_FILE} ps

    echo ""
    log "Health check:"
    curl -sf http://localhost:8000/health 2>/dev/null && echo " - API: OK" || echo " - API: DOWN"
}

logs() {
    local service="${1:-}"
    if [ -n "$service" ]; then
        docker compose -f ${COMPOSE_FILE} logs -f "${service}"
    else
        docker compose -f ${COMPOSE_FILE} logs -f
    fi
}

stop() {
    log "Stopping all services..."
    docker compose -f ${COMPOSE_FILE} down
    log "All services stopped"
}

restart() {
    log "Restarting services..."
    docker compose -f ${COMPOSE_FILE} restart
    log "Services restarted"
    status
}

backup() {
    log "Creating database backup..."
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="backup_${timestamp}.sql.gz"

    docker compose -f ${COMPOSE_FILE} exec -T db \
        pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-network_bot}" | gzip > "${backup_file}"

    log "Backup saved to ${backup_file}"
}

# Main
case "${1:-help}" in
    setup)   setup ;;
    deploy)  deploy ;;
    migrate) migrate ;;
    ssl)     ssl "${2:-}" ;;
    logs)    logs "${2:-}" ;;
    status)  status ;;
    stop)    stop ;;
    restart) restart ;;
    backup)  backup ;;
    *)
        echo "Usage: ./deploy.sh <command>"
        echo ""
        echo "Commands:"
        echo "  setup    - Initial server setup (Docker, firewall, swap)"
        echo "  deploy   - Build and deploy all services"
        echo "  migrate  - Run database migrations"
        echo "  ssl      - Obtain SSL certificate (./deploy.sh ssl domain.com)"
        echo "  logs     - View logs (./deploy.sh logs [service])"
        echo "  status   - Show service status"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  backup   - Create database backup"
        ;;
esac
