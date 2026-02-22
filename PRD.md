# PRD.md — BranchNexus TypeScript/npm Paketi

## 1. Proje Özeti

**BranchNexus**, birden fazla Git branch'i aynı anda izole worktree'lerde açıp tmux panelleriyle yöneten bir CLI aracıdır. Mevcut Python uygulaması TypeScript ile yeniden yazılacak ve `npm install -g branchnexus` ile kurulabilir hale getirilecektir.

---

## 2. Hedefler

| Hedef | Açıklama |
|-------|----------|
| npm global paketi | `npm install -g branchnexus` ile kurulum |
| Cross-platform | Windows (WSL), macOS, Linux desteği |
| İnteraktif kurulum | Terminalden seçimlerle yapılandırma |
| Tam TypeScript rewrite | Tip güvenliği ve modern tooling |
| Multi-pm desteği | npm, yarn, pnpm lock dosyaları |

---

## 3. Paket Bilgileri

```json
{
  "name": "branchnexus",
  "version": "1.0.0",
  "description": "Multi-branch workspace orchestrator for tmux",
  "bin": { "branchnexus": "./dist/cli.js" },
  "type": "module",
  "engines": { "node": ">=18.0.0" },
  "keywords": ["git", "tmux", "worktree", "cli", "productivity"],
  "license": "MIT"
}
```

---

## 4. Terminal İnteraktif Kurulum Akışı

Kullanıcı `npx branchnexus init` veya `branchnexus` komutunu ilk kez çalıştırdığında:

```
? BranchNexus'e hoş geldiniz! Ne yapmak istersiniz?
  ❯ Yeni kurulum yap
    Mevcut yapılandırmayı düzenle
    Çıkış

? Varsayılan çalışma dizini: (~/workspace)

? Varsayılan layout düzeni:
  ❯ grid (2x2)
    horizontal (yan yana)
    vertical (alt alta)

? Varsayılan pane sayısı: (2-6) 4

? Oturum sonu temizlik politikası:
  ❯ session (oturum bitince worktree'leri sil)
    persistent (worktree'leri koru)

? WSL dağıtımı seç: (Windows için)
  ❯ Ubuntu-22.04
    Debian
    Alpine

? GitHub token gerekli mi? (özel repolar için)
  ❯ Evet, token gireceğim
    Hayır, sadece public repolar

? Yapılandırma kaydedilsin mi?
  ❯ Evet (~/.config/branchnexus/config.json)
    Hayır, bu oturum için geçici
```

---

## 5. CLI Komutları

```bash
branchnexus                  # İnteraktif GUI başlat
branchnexus init             # İlk kurulum sihirbazı
branchnexus config           # Yapılandırmayı düzenle
branchnexus --layout grid    # Layout override
branchnexus --panes 4        # Pane sayısı override
branchnexus --cleanup session|persistent
branchnexus --fresh          # Temiz başlangıç
branchnexus --help           # Yardım
branchnexus --version        # Versiyon
```

---

## 6. Proje Yapısı

```
branchnexus/
├── src/
│   ├── cli.ts                 # Entry point, commander setup
│   ├── index.ts               # Public exports
│   ├── commands/
│   │   ├── init.ts            # İlk kurulum sihirbazı
│   │   ├── run.ts             # Ana çalıştırma komutu
│   │   └── config.ts          # Yapılandırma yönetimi
│   ├── prompts/               # inquirer prompt tanımları
│   │   ├── index.ts
│   │   ├── setup.ts           # Kurulum soruları
│   │   ├── wsl.ts             # WSL seçimi
│   │   ├── repo.ts            # Repo seçimi
│   │   └── branch.ts          # Branch seçimi
│   ├── core/
│   │   ├── orchestrator.ts    # Ana koordinasyon
│   │   ├── config.ts          # Config yükleme/kaydetme
│   │   └── session.ts         # Oturum yönetimi
│   ├── git/
│   │   ├── worktree.ts        # Worktree işlemleri
│   │   ├── branch.ts          # Branch işlemleri
│   │   └── clone.ts           # Clone/fetch işlemleri
│   ├── tmux/
│   │   ├── bootstrap.ts       # tmux kurulum kontrolü
│   │   ├── layouts.ts         # Layout komutları
│   │   └── session.ts         # Oturum başlatma
│   ├── runtime/
│   │   ├── wsl.ts             # WSL entegrasyonu
│   │   └── shell.ts           # Shell komut çalıştırma
│   └── utils/
│       ├── logger.ts          # Logging
│       ├── fs.ts              # Dosya işlemleri
│       └── validators.ts      # Doğrulama fonksiyonları
├── dist/                      # Compiled output
├── package.json
├── tsconfig.json
├── tsconfig.build.json
├── rollup.config.ts           # veya tsup.config.ts
├── .npmignore
├── README.md
└── LICENSE
```

---

## 7. Teknoloji Stack

| Katman | Kütüphane | Amaç |
|--------|-----------|------|
| CLI Framework | `commander` | Komut satırı argümanları |
| Prompts | `inquirer` | İnteraktif seçimler |
| Config | `conf` veya `cosmiconfig` | Yapılandırma yönetimi |
| Git İşlemleri | `simple-git` | Git komutları |
| TUI (opsiyonel) | `ink` veya `@clack/core` | Terminal UI |
| Build | `tsup` veya `rollup` | Bundle/compile |
| Test | `vitest` | Unit tests |
| Lint | `eslint` + `prettier` | Code quality |
| Types | `typescript` | Tip güvenliği |

---

## 8. Bağımlılıklar

### Production Dependencies
```json
{
  "commander": "^12.0.0",
  "inquirer": "^9.2.0",
  "conf": "^13.0.0",
  "simple-git": "^3.22.0",
  "chalk": "^5.3.0",
  "ora": "^8.0.0",
  "execa": "^8.0.0",
  "zod": "^3.22.0"
}
```

### Dev Dependencies
```json
{
  "typescript": "^5.3.0",
  "tsup": "^8.0.0",
  "vitest": "^1.2.0",
  "eslint": "^8.56.0",
  "prettier": "^3.2.0",
  "@types/inquirer": "^9.0.0",
  "@types/node": "^20.11.0"
}
```

---

## 9. Config Dosyası Yapısı

**Konum:** `~/.config/branchnexus/config.json`

```json
{
  "defaultRoot": "~/workspace",
  "defaultLayout": "grid",
  "defaultPanes": 4,
  "cleanupPolicy": "session",
  "wslDistribution": "Ubuntu-22.04",
  "terminalDefaultRuntime": "wsl",
  "terminalMaxCount": 16,
  "githubToken": "",
  "githubRepositoriesCache": [],
  "githubBranchesCache": {},
  "sessionRestoreEnabled": true,
  "presets": {
    "quick": { "layout": "horizontal", "panes": 2, "cleanup": "persistent" }
  },
  "commandHooks": {}
}
```

---

## 10. npm Yayın Süreci

```bash
# 1. Build
npm run build

# 2. Local test
npm link
branchnexus --help

# 3. Dry run
npm publish --dry-run

# 4. Publish (ilk kez)
npm publish --access public

# 5. Versiyon güncelleme
npm version patch|minor|major
npm publish
```

---

## 11. Geliştirme Aşamaları

| Aşama | Görevler | Tahmini Süre |
|-------|----------|--------------|
| **Phase 1** | Proje scaffold, tsconfig, build setup | 1 gün |
| **Phase 2** | CLI framework (commander) + inquirer prompts | 2 gün |
| **Phase 3** | Config yönetimi (conf/cosmiconfig) | 1 gün |
| **Phase 4** | Git worktree modülü (simple-git) | 2 gün |
| **Phase 5** | tmux entegrasyonu | 2 gün |
| **Phase 6** | WSL runtime | 1 gün |
| **Phase 7** | Orchestrator + tam akış | 2 gün |
| **Phase 8** | Test + lint + docs | 2 gün |
| **Phase 9** | npm publish + CI/CD | 1 gün |

**Toplam:** ~14 gün

---

## 12. Kabul Kriterleri

- [ ] `npm install -g branchnexus` ile kurulabiliyor
- [ ] `branchnexus init` ile interaktif kurulum çalışıyor
- [ ] Tüm prompt'lar terminalde seçilebiliyor
- [ ] WSL dağıtım seçimi çalışıyor
- [ ] Git worktree oluşturulabiliyor
- [ ] tmux session başlatılabiliyor
- [ ] Config dosyası doğru konuma kaydediliyor
- [ ] `--help` ve `--version` çalışıyor
- [ ] npm, yarn, pnpm ile kurulabiliyor
- [ ] Windows, macOS, Linux'ta test edildi

---

## 13. Riskler ve Azaltıcı Önlemler

| Risk | Etki | Azaltıcı Önlem |
|------|------|----------------|
| WSL API değişiklikleri | Orta | Versiyon kontrolü + fallback |
| tmux versiyon uyumsuzluğu | Düşük | Min versiyon kontrolü |
| npm registry sorunları | Düşük | GitHub Packages backup |

---

## 14. Kaynak Dosyalar (Python → TypeScript Mapping)

| Python Modülü | TypeScript Karşılığı |
|---------------|---------------------|
| `cli.py` | `src/cli.ts` |
| `config.py` | `src/core/config.ts` |
| `orchestrator.py` | `src/core/orchestrator.ts` |
| `tmux/bootstrap.py` | `src/tmux/bootstrap.ts` |
| `tmux/layouts.py` | `src/tmux/layouts.ts` |
| `worktree/manager.py` | `src/git/worktree.ts` |
| `git/branch_provider.py` | `src/git/branch.ts` |
| `git/materialize.py` | `src/git/clone.ts` |
| `runtime/wsl_discovery.py` | `src/runtime/wsl.ts` |
| `runtime/wsl_runtime.py` | `src/runtime/wsl.ts` |
| `errors.py` | `src/utils/errors.ts` |
| `logging.py` | `src/utils/logger.ts` |
| `presets.py` | `src/core/presets.ts` |
| `session.py` | `src/core/session.ts` |
