"""
Production build script for AMS
"""
import os
import re
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path



class ProductionBuilder:
    """Builds AMS for production deployment"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / 'build'
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
    def run_command(self, command: str, cwd: Path = None) -> bool:
        """Run a shell command and return success status"""
        print(f"Running: {command}")
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or self.project_root,
                capture_output=True,
                text=True,
                check=True
            )
            print(f"✓ {command}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ {command}")
            print(f"Error: {e.stderr}")
            return False
    
    def check_environment(self) -> bool:
        """Check if environment is ready for build"""
        print("Checking environment...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            print("✗ Python 3.8+ is required")
            return False
        print(f"✓ Python {sys.version}")
        
        # Check required files
        required_files = ['requirements.txt', 'run.py', 'app/__init__.py']
        for file in required_files:
            if not (self.project_root / file).exists():
                print(f"✗ Required file missing: {file}")
                return False
        print("✓ Required files present")
        
        # Check environment variables
        env_vars = ['SECRET_KEY', 'DATABASE_URL']
        missing_vars = []
        for var in env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"✗ Missing environment variables: {', '.join(missing_vars)}")
            return False
        print("✓ Environment variables configured")
        
        return True
    
    def clean_build(self) -> bool:
        """Clean previous build artifacts"""
        print("Cleaning previous build...")
        
        # Remove build directory
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        
        # Remove Python cache
        cache_dirs = [
            self.project_root / '__pycache__',
            self.project_root / 'app' / '__pycache__',
            self.project_root / '.pytest_cache'
        ]
        
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
        
        # Remove compiled Python files
        for pyc_file in self.project_root.rglob('*.pyc'):
            pyc_file.unlink()
        
        print("✓ Build cleaned")
        return True
    
    def install_dependencies(self) -> bool:
        """Install production dependencies"""
        print("Installing production dependencies...")
        
        # Upgrade pip
        if not self.run_command(f"{sys.executable} -m pip install --upgrade pip"):
            return False
        
        # Install requirements
        if not self.run_command(f"{sys.executable} -m pip install -r requirements.txt"):
            return False
        
        # Install development dependencies if available
        dev_requirements = self.project_root / 'requirements-dev.txt'
        if dev_requirements.exists():
            if not self.run_command(f"{sys.executable} -m pip install -r requirements-dev.txt"):
                return False
        
        print("✓ Dependencies installed")
        return True
    
    def run_tests(self) -> bool:
        """Run test suite"""
        print("Running tests...")
        
        # Check if pytest is available
        try:
            import pytest
        except ImportError:
            print("⚠ pytest not found, skipping tests")
            return True
        
        # Run tests with coverage
        if not self.run_command(f"{sys.executable} -m pytest tests/ --cov=app --cov-report=html --cov-report=term"):
            return False
        
        print("✓ Tests passed")
        return True
    
    def run_migrations(self) -> bool:
        """Run database migrations"""
        print("Running database migrations...")
        
        # Check if flask command is available
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'flask', '--version'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print("⚠ Flask CLI not available, skipping migrations")
                return True
        except Exception:
            print("⚠ Flask CLI not available, skipping migrations")
            return True
        
        # Run migrations
        if not self.run_command(f"{sys.executable} -m flask db upgrade"):
            return False
        
        print("✓ Migrations completed")
        return True
    
    def collect_static(self) -> bool:
        """Collect and optimize static files"""
        print("Collecting static files...")
        
        # Create build directory
        self.build_dir.mkdir(exist_ok=True)
        
        # Copy static files
        static_src = self.project_root / 'app' / 'static'
        static_dst = self.build_dir / 'static'
        
        if static_src.exists():
            if static_dst.exists():
                shutil.rmtree(static_dst)
            shutil.copytree(static_src, static_dst)
        
        # Minify CSS if available
        css_files = list(static_dst.rglob('*.css'))
        for css_file in css_files:
            # Basic CSS minification (remove comments and extra whitespace)
            try:
                with open(css_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Remove comments
                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                # Remove extra whitespace
                content = re.sub(r'\s+', ' ', content)
                content = content.strip()
                
                with open(css_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✓ Minified {css_file.name}")
            except Exception as e:
                print(f"⚠ Could not minify {css_file.name}: {e}")
        
        print("✓ Static files collected")
        return True
    
    def create_production_config(self) -> bool:
        """Create production configuration files"""
        print("Creating production configuration...")
        
        # Create production environment file template
        env_template = self.build_dir / '.env.template'
        with open(env_template, 'w') as f:
            f.write("""# AMS Production Environment Configuration
# Copy this file to .env and fill in the values

# Core Configuration
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=your-secret-key-here
PORTAL_VERSION=1.0.0

# Database Configuration
DATABASE_URL=postgresql://postgres:CHANGE_THIS_PASSWORD@localhost:5432/ams_db

# Redis Configuration (for rate limiting)
REDIS_URL=redis://localhost:6379/0

# File Upload Configuration
UPLOAD_FOLDER=/var/lib/ams/uploads
MAX_CONTENT_LENGTH=64424509400  # 60GB

# Security Configuration
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Strict
WTF_CSRF_ENABLED=true

# Rate Limiting
RATELIMIT_STORAGE_URL=redis://localhost:6379/1
RATELIMIT_DEFAULT=200 per day, 50 per hour

# CORS Configuration
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Monitoring
ENABLE_METRICS=true
METRICS_PORT=9090

# Logging
LOG_LEVEL=INFO
""")
        
        # Create systemd service file
        service_file = self.build_dir / 'ams.service'
        with open(service_file, 'w') as f:
            f.write(f"""[Unit]
Description=AMS Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory={self.project_root}
Environment=PATH={self.project_root}/.venv/bin
ExecStart={sys.executable} {self.project_root}/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
""")
        
        # Create nginx configuration template
        nginx_file = self.build_dir / 'nginx.conf'
        with open(nginx_file, 'w') as f:
            f.write("""server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL Configuration
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;
    
    # Application
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # Rate limit auth endpoints
    location /auth/ {
        limit_req zone=auth burst=5 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static files
    location /static/ {
        alias {static_path}/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        gzip_static on;
    }
    
    # Health check
    location /health {
        access_log off;
        proxy_pass http://127.0.0.1:5000;
    }
}
""".format(static_path=str(self.build_dir / 'static')))
        
        print("✓ Production configuration created")
        return True
    
    def create_deployment_scripts(self) -> bool:
        """Create deployment helper scripts"""
        print("Creating deployment scripts...")
        
        # Deploy script
        deploy_script = self.build_dir / 'deploy.sh'
        with open(deploy_script, 'w') as f:
            f.write(f"""#!/bin/bash
# AMS Deployment Script

set -e

echo "Starting AMS deployment..."

# Stop existing service
sudo systemctl stop ams || true

# Backup current version
if [ -d "/var/lib/ams" ]; then
    sudo cp -r /var/lib/ams /var/lib/ams.backup.$(date +%Y%m%d_%H%M%S)
fi

# Copy new files
sudo mkdir -p /var/lib/ams
sudo cp -r {self.project_root}/* /var/lib/ams/
sudo cp -r {self.build_dir}/static /var/lib/ams/app/

# Set permissions
sudo chown -R www-data:www-data /var/lib/ams
sudo chmod -R 755 /var/lib/ams

# Install dependencies
cd /var/lib/ams
sudo -u www-data {sys.executable} -m pip install -r requirements.txt

# Run migrations
sudo -u www-data {sys.executable} -m flask db upgrade

# Start service
sudo systemctl daemon-reload
sudo systemctl enable ams
sudo systemctl start ams

echo "Deployment completed!"
echo "Check status with: sudo systemctl status ams"
""")
        
        deploy_script.chmod(0o755)
        
        # Backup script
        backup_script = self.build_dir / 'backup.sh'
        with open(backup_script, 'w') as f:
            f.write("""#!/bin/bash
# AMS Backup Script

set -e

BACKUP_DIR="/var/backups/ams"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Database backup
pg_dump "$DATABASE_URL" > "$BACKUP_DIR/db_$DATE.sql"

# Files backup
tar -czf "$BACKUP_DIR/files_$DATE.tar.gz" /var/lib/ams/uploads

# Clean old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.sql" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
""")
        
        backup_script.chmod(0o755)
        
        print("✓ Deployment scripts created")
        return True
    
    def build(self) -> bool:
        """Run the complete build process"""
        print(f"Building AMS for production - {self.timestamp}")
        print("=" * 50)
        
        steps = [
            self.check_environment,
            self.clean_build,
            self.install_dependencies,
            self.run_tests,
            self.run_migrations,
            self.collect_static,
            self.create_production_config,
            self.create_deployment_scripts
        ]
        
        for step in steps:
            if not step():
                print(f"Build failed at {step.__name__}")
                return False
        
        print("=" * 50)
        print("✓ Build completed successfully!")
        print(f"Build artifacts located in: {self.build_dir}")
        print("\nNext steps:")
        print("1. Review configuration files in build directory")
        print("2. Copy .env.template to .env and configure")
        print("3. Run ./deploy.sh to deploy to production")
        
        return True


def main():
    """Main build function"""
    builder = ProductionBuilder()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'clean':
            builder.clean_build()
        elif command == 'test':
            builder.run_tests()
        elif command == 'migrate':
            builder.run_migrations()
        elif command == 'static':
            builder.collect_static()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: clean, test, migrate, static")
            sys.exit(1)
    else:
        success = builder.build()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
