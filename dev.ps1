# dev.ps1 — Build local completo + servidor de desenvolvimento
# Uso: .\dev.ps1 (da raiz do projeto)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

Write-Host "`n[1/4] Sincronizando site/ → dist/ ..." -ForegroundColor Cyan
robocopy site dist /E /IS /IT /NFL /NDL /NJH /NJS | Out-Null

Write-Host "[2/4] Criando rotas de URL limpas ..." -ForegroundColor Cyan
foreach ($page in @("metricas","predicao","rotas","financeiro")) {
    $dir = "dist\$page"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Copy-Item "dist\$page.html" "$dir\index.html" -Force
}

Write-Host "[3/4] Rodando scripts Python ..." -ForegroundColor Cyan
python scripts/build_metrics.py
python scripts/build_financeiro.py
# Descomente se quiser rodar também predicao e rotas:
# python scripts/build_prediction.py
# python scripts/geocode_addresses.py

Write-Host "[4/4] Subindo servidor em http://localhost:8000 ..." -ForegroundColor Green
Write-Host "      Acesse: http://localhost:8000/metricas/" -ForegroundColor Yellow
Write-Host "              http://localhost:8000/financeiro/" -ForegroundColor Yellow
Write-Host "      Ctrl+C para parar.`n" -ForegroundColor Gray

Push-Location dist
try {
    python -c "
import http.server, socketserver

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, fmt, *args):
        print(fmt % args)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(('', 8000), NoCacheHandler) as httpd:
    httpd.serve_forever()
"
} finally {
    Pop-Location
}
