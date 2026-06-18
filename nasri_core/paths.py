"""
Nasri — Merkezi yol ve sabit yönetimi.
Tüm dosya yolları burada tanımlanır; başka hiçbir modül elle yol kurmaz.
Bu, taşınabilirliği ve bakımı kolaylaştırır.
"""
from pathlib import Path

# Proje kök dizini (bu dosyanın iki üst klasörü: nasri_core/ -> nasri/)
ROOT = Path(__file__).resolve().parent.parent

# Ana klasörler
CONFIG_DIR = ROOT / "config"
LOGS_DIR = ROOT / "logs"

# Dosyalar
CONFIG_FILE = CONFIG_DIR / "config.json"      # genel ayarlar (git'te olabilir)
SECRETS_FILE = CONFIG_DIR / "secrets.json"    # API anahtarları (git'te ASLA)
LOG_FILE = LOGS_DIR / "nasri.log"

# Klasörlerin var olduğundan emin ol (yoksa oluştur)
def ensure_dirs() -> None:
    """Gerekli klasörleri oluşturur. Servis başlangıcında çağrılır."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

DIN_INSAN_FILE = CONFIG_DIR / "din_insan.json"
SOUL_FILE = CONFIG_DIR / "soul.json"
