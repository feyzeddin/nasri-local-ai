# nasri-ui

SvelteKit tabanlı Nasri dashboard uygulaması.

## Özellikler

- Sohbet paneli (`/chat`)
- Sistem durumu paneli (`/health/ready`, `/maintenance/status`)
- Cihaz listesi (`/network/discover`)
- Log görüntüleyici (`/files/list`)

## Komutlar

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run preview`
- `npm run check`

## Env

`.env.example` dosyasını `.env` olarak kopyalayın.

- `VITE_API_BASE_URL=http://localhost:8000`
- `VITE_SESSION_TOKEN=` (RBAC açıkken gerekli)
