#!/usr/bin/env bash
# setup.sh — Instala y despliega Despacha en un nuevo servidor
# Uso: bash setup.sh [prod|dev]
set -euo pipefail

# ── colores ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✗ ERROR:${NC} $*"; exit 1; }

# ── instalar dependencias automáticamente ─────────────────────────────────
install_deps() {
    # Solo soporta Debian/Ubuntu
    if ! command -v apt-get &>/dev/null; then
        die "Instalación automática solo soporta Debian/Ubuntu. Instala Docker y Git manualmente."
    fi

    # Git
    if ! command -v git &>/dev/null; then
        info "Instalando Git..."
        ${SUDO_CMD} apt-get update -qq && ${SUDO_CMD} apt-get install -y -qq git
        ok "Git instalado ($(git --version))"
    else
        ok "Git ya instalado ($(git --version))"
    fi

    # OpenSSL (casi siempre presente, pero por si acaso)
    if ! command -v openssl &>/dev/null; then
        info "Instalando OpenSSL..."
        ${SUDO_CMD} apt-get install -y -qq openssl
        ok "OpenSSL instalado"
    fi

    # Docker
    if ! command -v docker &>/dev/null; then
        info "Instalando Docker (puede tardar 1-2 minutos)..."
        curl -fsSL https://get.docker.com | ${SUDO_CMD} bash
        if [[ -n "${SUDO_USER:-}" ]]; then
            ${SUDO_CMD} usermod -aG docker "$SUDO_USER"
            warn "Usuario '$SUDO_USER' agregado al grupo docker."
            warn "Cuando termine el setup, cierra sesión y vuelve a entrar para usar docker sin sudo."
        fi
        ok "Docker instalado ($(docker --version))"
    else
        ok "Docker ya instalado ($(docker --version))"
    fi

    # Docker Compose plugin v2
    if ! docker compose version &>/dev/null; then
        info "Instalando Docker Compose plugin..."
        ${SUDO_CMD} apt-get install -y -qq docker-compose-plugin
        ok "Docker Compose instalado ($(docker compose version))"
    else
        ok "Docker Compose ya instalado ($(docker compose version))"
    fi
}

# ── verificar que todo esté listo ──────────────────────────────────────────
check_deps() {
    for cmd in docker git openssl; do
        command -v "$cmd" &>/dev/null || die "Falta '$cmd' después de la instalación. Algo salió mal."
    done
    docker compose version &>/dev/null || die "Falta 'docker compose' plugin v2."
    ok "Dependencias verificadas"
}

# ── verificar root para instalar paquetes ─────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    warn "No se está ejecutando como root. Si faltan Docker o Git, el script pedirá sudo."
    SUDO_CMD="sudo"
else
    SUDO_CMD=""
fi

# Instalar lo que falte
install_deps
check_deps

# ── modo (prod / dev) ──────────────────────────────────────────────────────
MODO="${1:-}"
if [[ -z "$MODO" ]]; then
    echo ""
    echo "¿Qué entorno deseas configurar?"
    echo "  1) prod  — producción en /opt/despacha    (puerto 8000)"
    echo "  2) dev   — desarrollo en /opt/despacha-dev (puerto 8001)"
    read -rp "Elige [1/2]: " OPCION
    case "$OPCION" in
        1) MODO=prod ;;
        2) MODO=dev  ;;
        *) die "Opción inválida." ;;
    esac
fi

case "$MODO" in
    prod)
        INSTALL_DIR="/opt/despacha"
        PORT="8000"
        DB_NAME="despacha"
        DB_USER="despacha"
        POSTGRES_DATA="/home/despachos/postgres-data"
        SECRETS_PATH="/opt/despacha/secrets"
        LOGS_PATH="/opt/despacha/logs"
        ENVIRONMENT="production"
        DEBUG="False"
        ;;
    dev)
        INSTALL_DIR="/opt/despacha-dev"
        PORT="8001"
        DB_NAME="despacha_dev"
        DB_USER="despacha_dev"
        POSTGRES_DATA="/home/despachos/postgres-data-dev"
        SECRETS_PATH="/opt/despacha-dev/secrets"
        LOGS_PATH="/opt/despacha-dev/logs"
        ENVIRONMENT="development"
        DEBUG="True"
        ;;
    *)
        die "Modo inválido: '$MODO'. Usa 'prod' o 'dev'."
        ;;
esac

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Configurando entorno: ${GREEN}${MODO}${NC}"
echo -e "  Directorio: ${INSTALL_DIR}"
echo -e "  Puerto:     ${PORT}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── clonar o actualizar ────────────────────────────────────────────────────
REPO="git@github.com:Proasepsis/despacha.git"

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Repositorio ya existe — actualizando..."
    git -C "$INSTALL_DIR" pull --ff-only
    ok "Código actualizado"
else
    info "Clonando repositorio en $INSTALL_DIR..."
    git clone "$REPO" "$INSTALL_DIR"
    ok "Repositorio clonado"
fi

# ── directorios necesarios ─────────────────────────────────────────────────
info "Creando directorios..."
mkdir -p "$SECRETS_PATH" "$LOGS_PATH" "$POSTGRES_DATA"
chmod 777 "$LOGS_PATH"
ok "Directorios listos"

# ── generar .env si no existe ──────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env ya existe — se mantiene sin cambios."
    warn "Borra $ENV_FILE y vuelve a ejecutar para regenerarlo."
else
    info "Generando claves seguras con openssl..."
    SECRET_KEY=$(openssl rand -base64 50 | tr -d '\n')
    DB_PASSWORD=$(openssl rand -base64 24 | tr -d '\n/+=' | cut -c1-32)
    SUPER_PASS=$(openssl rand -base64 16 | tr -d '\n/+=' | cut -c1-20)

    echo ""
    if [[ "$MODO" == "prod" ]]; then
        read -rp "Dominio público (ej: despacha.empresa.com.co): " DOMINIO
        ALLOWED_HOSTS="localhost,127.0.0.1,${DOMINIO}"
        CSRF_ORIGINS="https://${DOMINIO}"
    else
        DOMINIO="localhost"
        ALLOWED_HOSTS="localhost,127.0.0.1"
        CSRF_ORIGINS="http://localhost:${PORT},http://127.0.0.1:${PORT}"
    fi

    read -rp "Email del superusuario [admin@${DOMINIO}]: " SUPER_EMAIL
    SUPER_EMAIL="${SUPER_EMAIL:-admin@${DOMINIO}}"

    if [[ "$MODO" == "prod" ]]; then
        read -rp "Email SMTP para notificaciones (Gmail): " EMAIL_USER
        read -rsp "Contraseña de app Gmail: " EMAIL_PASS
        echo ""
    else
        EMAIL_USER=""
        EMAIL_PASS=""
    fi

    cat > "$ENV_FILE" <<EOF
# Generado por setup.sh el $(date '+%Y-%m-%d %H:%M:%S')
DEBUG=${DEBUG}
SECRET_KEY=${SECRET_KEY}
ALLOWED_HOSTS=${ALLOWED_HOSTS}
CSRF_TRUSTED_ORIGINS=${CSRF_ORIGINS}
TIME_ZONE=America/Bogota
ENVIRONMENT=${ENVIRONMENT}

# Base de datos
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=db
DB_PORT=5432

# Rutas (docker-compose las lee)
PORT=${PORT}
POSTGRES_DATA_PATH=${POSTGRES_DATA}
SECRETS_PATH=${SECRETS_PATH}
LOGS_PATH=${LOGS_PATH}

# Google Drive (opcional — colocar JSON de cuenta de servicio en ${SECRETS_PATH}/drive-sa.json)
DRIVE_SERVICE_ACCOUNT_JSON=/secrets/drive-sa.json
DRIVE_ROOT_FOLDER_ID=

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=${EMAIL_USER}
EMAIL_HOST_PASSWORD=${EMAIL_PASS}
DEFAULT_FROM_EMAIL=Despacha <${EMAIL_USER:-no-reply@localhost}>

# Superusuario inicial
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=${SUPER_PASS}
DJANGO_SUPERUSER_EMAIL=${SUPER_EMAIL}
EOF

    ok ".env generado en $ENV_FILE"
    echo ""
    echo -e "${YELLOW}━━━━ GUARDA ESTAS CREDENCIALES ━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Superusuario:  admin"
    echo -e "  Contraseña:    ${GREEN}${SUPER_PASS}${NC}"
    echo -e "  DB password:   ${GREEN}${DB_PASSWORD}${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
fi

# ── construir y levantar ───────────────────────────────────────────────────
info "Construyendo imagen y levantando contenedores..."
cd "$INSTALL_DIR"
docker compose up --build -d

# ── esperar a que gunicorn arranque ───────────────────────────────────────
info "Esperando que el servidor arranque..."
for i in {1..20}; do
    if docker compose logs web 2>&1 | grep -q "Booting worker"; then
        break
    fi
    sleep 2
done

# ── verificar ─────────────────────────────────────────────────────────────
if docker compose logs web 2>&1 | grep -q "Booting worker"; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}¡Despacha [${MODO}] desplegado correctamente!${NC}"
    echo -e "  URL: http://$(hostname -I | awk '{print $1}'):${PORT}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    die "El servidor no arrancó correctamente. Revisa: docker compose -f $INSTALL_DIR/docker-compose.yml logs web"
fi
