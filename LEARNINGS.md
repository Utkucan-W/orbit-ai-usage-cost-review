# Learnings

## Upstream provider listesini filtrele

- Belirti: `codexbar usage --provider all` onlarca provider ismi döndürse de
  çoğunun etkin kullanım penceresi yoktu; arayüz boş kartlarla doluyordu.
- Neden: CLI, desteklenen provider envanterini de JSON'a katabiliyor.
- Doğrulanan çözüm: yalnızca usage penceresi, hesap kimliği veya credit verisi
  bulunan kayıtları arayüzde göster.
- Kanıt: Gerçek yerel CLI çıktısı Codex için tek kullanılabilir kayıt üretti.

## Günlük token geçmişini CLI penceresinden bağımsız sakla

- Belirti: `codexbar cost` günlük token verisini sınırlı bir geçmiş penceresiyle
  döndürür; aylar geçtikçe eski günlük kayıtlar arayüzden kaybolur.
- Neden: CLI yerel loglardan anlık/son dönem özet üretir; uygulamanın kendine
  ait uzun dönem saklama katmanı yoktur.
- Doğrulanan çözüm: `daily[].date` ve `daily[].totalTokens` değerlerini cihazdaki
  JSON geçmişine birleştir; yeni değerler aynı günün kaydını günceller, 365
  günden eski kayıtlar silinir. Aylık toplam ve günlük satırlar bu geçmişten
  üretilir.
- Önleme: Geçmiş kaynağının kapsadığı gün sayısını kullanıcıya açıkça bildir;
  dış CLI verisini olduğu gibi sınırsız geçmiş varsayma.
- Kanıt: Gerçek Codex CLI çıktısından 4 gün içeri aktarıldı; birim testleri
  birleştirme, ay toplamı, ayrıştırma ve JSON round-trip'i kapsıyor.

## Tek-örnek korumasında ortamla uyumlu Qt mekanizması kullan

- Belirti: Uygulama kapatıldıktan sonra tepside yaşamaya devam ederken yeniden
  çalıştırılması ikinci tepsi ikonu ve süreç oluşturabiliyordu.
- Neden: Uygulama kapanışta tamamen sonlanmıyor, ancak ikinci başlatmayı
  engelleyen bir süreç kilidi yoktu.
- Başarısız deneme: `QLocalServer` bu KDE/Qt ortamında `Unknown error` ile
  dinleyici açamadı.
- Doğrulanan çözüm: Süreç ömrüne bağlı `QSharedMemory` koruması kullan. İlk
  süreç küçük bir ortak bellek parçasını oluşturur; ikinci süreç bunu oluşturamaz
  ve yeni pencere/tepsi ikonu üretmeden çıkar.
- Kanıt: Offscreen ortamda ilk uygulama açıkken ikinci `python3 app.py` çağrısı
  “CodexBar zaten arka planda çalışıyor.” mesajıyla sonlandı.
