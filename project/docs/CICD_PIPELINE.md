# CI/CD Pipeline

Nasri monorepo iki ayrı workflow ile çalışır:

- `ci.yml`: her push/PR için kalite kapısı
- `cd.yml`: test sonrası onaylı dağıtım

## CI (Kalite Kapısı)

`ci.yml` aşağıdaki kontrolleri uygular:

- `nasri-core` için `ruff check`, `ruff format --check`, `pytest`
- `nasri-ui` için `npm run typecheck`, `npm run lint`, `npm run build`

## CD (Test -> Onay -> Deploy)

`cd.yml` akışı:

1. `verify` job'u tüm core/ui kontrollerini tekrar çalıştırır.
2. `develop` branch push: `deploy-staging` tetiklenir.
3. `main` branch push: `deploy-production` tetiklenir.
4. Manuel tetikleme (`workflow_dispatch`) ile `staging` veya `production` seçilebilir.

Deploy job'ları GitHub Environment kullanır:

- `staging`
- `production`

Production için GitHub repo ayarlarında `required reviewers` tanımlanırsa dağıtım onay gerektirir.

## Deploy Script

`project/scripts/deploy.sh` şu an iskelet akış içerir:

- config yükleme
- artifact senkronizasyonu
- servis restart
- smoke check

Altyapı hazır olduğunda bu script gerçek komutlarla değiştirilmelidir.

