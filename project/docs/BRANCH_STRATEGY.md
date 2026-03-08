# Branch Strategy

## Ana Branch'ler

- `main`
  - Her zaman deploy edilebilir olmalı.
  - Sadece `release/*` veya `hotfix/*` merge alır.
- `develop`
  - Güncel geliştirmelerin birleştiği branch.
  - `feature/*` ve `fix/*` buraya açılır ve buraya merge edilir.

## Geçici Branch Tipleri

- `feature/<scope>-<name>`
  - Örnek: `feature/core-redis-cache`
  - Kaynak: `develop`
  - Hedef: `develop`
- `fix/<scope>-<name>`
  - Örnek: `fix/ui-navbar-overflow`
  - Kaynak: `develop`
  - Hedef: `develop`
- `release/<version>`
  - Örnek: `release/v0.1.0`
  - Kaynak: `develop`
  - Hedef: `main` ve geri `develop`
- `hotfix/<scope>-<name>`
  - Örnek: `hotfix/core-auth-timeout`
  - Kaynak: `main`
  - Hedef: `main` ve geri `develop`

## Merge Kuralları

- Merge yöntemi: `Squash and merge`
- PR başlığı Conventional Commit formatında olmalı.
- Her PR için CI geçmeli ve en az 1 review alınmalı.

## Versiyonlama

- SemVer (`MAJOR.MINOR.PATCH`) kullan.
- Release branch'leri etiketlenir: `vX.Y.Z`
- Changelog, release PR içinde güncellenir.
