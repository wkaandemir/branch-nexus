# BranchNexus

Birden fazla Git dalını (branch) izole worktree'ler ve tmux oturumlarıyla eş zamanlı olarak yönetmek için çoklu dal çalışma alanı düzenleyicisi.

## Özellikler

- **Çoklu Dal Çalışma Alanı**: Birden fazla Git dalını izole worktree'ler kullanarak paralel olarak çalışma
- **WSL Çalışma Zamanı**: Windows Subsystem for Linux ortamlarında işlemleri çalıştırma
- **Docker Çalışma Zamanı**: Alternatif konteyner tabanlı çalışma zamanı desteği
- **Tmux Entegrasyonu**: Özelleştirilebilir düzenlerle (yatay, dikey, ızgara) dalları terminal bölmelerinde organize etme
- **GUI Arayüzü**: Görsel dal seçimi ve çalışma alanı yapılandırması
- **VSCode Entegrasyonu**: Dalları doğrudan VSCode'da açma
- **Git İşlemleri**: Uzak dal materyalizasyonu ve depo keşfi

## Kurulum

```bash
# Sanal ortam oluşturma ve etkinleştirme
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# Windows: .venv\Scripts\activate

# Geliştirme bağımlılıklarıyla paketi kurma
python -m pip install -e ".[dev]"

# Kurulumu doğrulama
branchnexus --help
```

## Kullanım

### CLI

```bash
# GUI'yi başlatma (varsayılan)
branchnexus

# Yeni yapılandırmayla başlatma
branchnexus --fresh

# Düzen ve bölmeleri belirtme
branchnexus --layout grid --panes 4

# Temizlik politikasını ayarlama
branchnexus --cleanup session  # veya 'persistent'

# Özel terminal şablonu
branchnexus --terminal-template 4 --max-terminals 16
```

### Python Modülü

```bash
python -m branchnexus --help
```

## Proje Yapısı

```
src/branchnexus/
├── cli.py              # Komut satırı arayüzü
├── orchestrator.py     # Uçtan uca çalışma alanı orkestrasyonu
├── config.py           # Yapılandırma yönetimi
├── session.py          # Oturum durumu yönetimi
├── git/                # Git işlemleri
│   ├── branch_provider.py
│   ├── materialize.py
│   ├── remote_provider.py
│   ├── remote_workspace.py
│   └── repo_discovery.py
├── runtime/            # Çalışma zamanı ortamları
│   ├── wsl_runtime.py
│   ├── wsl_discovery.py
│   └── profile.py
├── tmux/               # Tmux entegrasyonu
│   ├── bootstrap.py
│   └── layouts.py
├── ui/                 # GUI bileşenleri
│   ├── app.py
│   └── state.py
├── workspace/           # Çalışma alanı yönetimi
│   └── vscode.py
├── docker/             # Docker çalışma zamanı
└── worktree/           # Git worktree yönetimi
    └── manager.py
```

## Geliştirme

### Testleri Çalıştırma

```bash
# Tam test paketi
pytest -q

# Yalnızca entegrasyon testleri
pytest -q tests/integration

# Coverage ile
pytest --cov=src/branchnexus tests/
```

### Kod Kalitesi

```bash
# Ruff ile lint
ruff check src tests

# Güvenlik linting
bandit -q -r src -ll
```

### Derleme

```bash
# Wheel dosyası oluşturma
python -m pip wheel . -w dist --no-deps

# Windows executable
build_windows_installer.bat
```

### Windows .exe Oluşturma

Windows'ta çalıştırılabilir bir .exe dosyası oluşturmak için `build_windows_installer.bat` betiğini kullanın:

```bash
# Proje dizininde çalıştırın
build_windows_installer.bat
```

Bu betik şu adımları otomatik olarak gerçekleştirir:
1. Python yüklü değilse winget ile Python 3.12 kurulumu yapar
2. Sanal ortam (.venv) oluşturur
3. Gerekli paketleri yükler
4. PyInstaller ile BranchNexus.exe dosyasını derler

**Çıktı:** `dist\BranchNexus.exe`

Oluşturulan .exe dosyasını çift tıklayarak veya komut satırından çalıştırarak GUI arayüzünü başlatabilirsiniz.

## Gereksinimler

- Python >= 3.10
- pydantic >= 2
- tmux (terminal oturumu yönetimi için)
- WSL (Windows geliştirme ortamları için)

## Lisans

MIT
