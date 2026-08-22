# CodexBar Linux — Context

## Amaç

steipete/CodexBar'ın macOS menü çubuğu deneyimini Linux/KDE için bağımsız bir
PyQt6 arayüzüyle sunmak. Veri kaynağı upstream `codexbar` CLI'dır; bu proje
provider API'larını yeniden uygulamaz.

## MVP sınırı

- Sistem tepsisi ikonu ve açılır dashboard penceresi.
- CLI JSON çıktısından sağlayıcı kartları.
- Session/weekly kullanım, reset bilgisi, maliyet ve son güncelleme.
- Yenileme, CLI yolu seçimi ve açık hata durumu.
- Kimlik bilgisi saklama veya provider API çağrısı yok.

## Kabul ölçütleri

- `python3 app.py --fixture tests/fixtures/usage.json` ile masaüstü arayüzü açılır.
- Gerçek CLI çalıştırıldığında JSON başarıyla kartlara dönüştürülür.
- CLI hata verirse pencere bunu görünür biçimde gösterir.
- `python3 -m unittest discover -s tests` başarılıdır.
