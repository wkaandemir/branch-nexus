# BranchNexus

BranchNexus, birden fazla Git branch'i ayni anda izole worktree'lerde acip tmux panelleriyle yonetmenizi kolaylastirir.

## Ne Ise Yarar?

- Branch bazli izole calisma alanlari olusturur.
- WSL uzerinde repo/branch hazirligini otomatik yapar.
- Secilen duzene gore tmux panel oturumu baslatir.
- Oturum sonu temizleme davranisini (session/persistent) yonetir.

## Hizli Baslangic

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
branchnexus
```

## Temel Kullanim

```bash
# GUI baslat
branchnexus

# Ayarlari sifirlayip GUI baslat
branchnexus --fresh

# Ornek ayarlarla calistir
branchnexus --layout grid --panes 4 --cleanup session
```

Desteklenen temel secenekler:

- `--layout`: `horizontal`, `vertical`, `grid`
- `--panes`: `2-6`
- `--cleanup`: `session` veya `persistent`
- `--terminal-template`: hazir terminal sayisi
- `--max-terminals`: maksimum terminal limiti

## Kisa Calisma Akisi

1. Konfigurasyon yuklenir (`~/.config/branchnexus/config.toml`).
2. WSL dagitimi ve tmux uygunlugu kontrol edilir.
3. Repo/branch secimleri hazirlanir (gerekirse clone/fetch).
4. Panel basina worktree olusturulur veya var olan kullanilir.
5. tmux oturumu secilen duzende baslatilir.
6. Oturum sonunda cleanup politikasi uygulanir.

## Proje Yapisi (Ozet)

```text
src/branchnexus/
├── cli.py
├── orchestrator.py
├── config.py
├── runtime/
├── tmux/
├── worktree/
└── ui/
```

## Gelistirme

```bash
pytest -q
ruff check src tests
```

## Gereksinimler

- Python >= 3.10
- tmux
- WSL (Windows kullanim senaryosu icin)

## Lisans

MIT
