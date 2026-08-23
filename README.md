# CodexBar Linux

steipete/CodexBar'ın Linux/KDE için bağımsız arayüz prototipi. Upstream
`codexbar` CLI'yı veri kaynağı olarak kullanır; provider kimlik bilgilerine
dokunmaz.

## Çalıştırma

```bash
cd /home/utkucan/Projects/codexbar-linux
python3 app.py
```

Varsayılan CLI yolu önce kullanıcı alanındaki CodexBar 0.54.0 wrapper'ıdır:
`/home/utkucan/.local/bin/codexbar-0540`. Gerekirse:

```bash
python3 app.py --cli /path/to/codexbar
```

Arayüzü test verisiyle açmak için:

```bash
python3 app.py --fixture tests/fixtures/usage.json
```

## Arayüz ve işlevler

- Siteye benzer kompakt `Usage` görünümü: provider seçimi, hesap/plan, kalan
  kullanım, reset sayaçları ve pace metni.
- Başlıktaki ay/güneş düğmesiyle açık ve koyu tema; son tercih uygulama
  yeniden açıldığında korunur.
- `Spend` görünümü: güncel/30 günlük maliyet, token toplamları, günlük maliyet
  grafiği ve model kırılımı.
- 12 aylık token geçmişi: günlük `totalTokens` kayıtları bu cihazda en fazla
  365 gün tutulur; aylık grafik ve her kayıt günü için token satırı gösterilir.
- Uygulama aynı anda yalnızca bir kez açılır; ikinci başlatma, yeni pencere veya
  tepsi ikonu oluşturmadan sonlanır.
- `assets/codexbar-linux-logo.png` özgün uygulama logosudur; pencere ve sistem
  tepsisinde kullanılır.
- Sistem tepsisi menüsü ve 60 saniyelik otomatik yenileme.
- Upstream CLI'dan gelen gerçek kullanım ve yerel maliyet verisi.

## Durum

MVP tamamlandı. Sadece gerçek kullanım penceresi veya bağlı hesap bilgisi
döndüren provider'lar listelenir; boş provider şablonları arayüzü doldurmaz.
