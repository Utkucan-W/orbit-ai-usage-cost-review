# Learnings

## Upstream provider listesini filtrele

- Belirti: `codexbar usage --provider all` onlarca provider ismi döndürse de
  çoğunun etkin kullanım penceresi yoktu; arayüz boş kartlarla doluyordu.
- Neden: CLI, desteklenen provider envanterini de JSON'a katabiliyor.
- Doğrulanan çözüm: yalnızca usage penceresi, hesap kimliği veya credit verisi
  bulunan kayıtları arayüzde göster.
- Kanıt: Gerçek yerel CLI çıktısı Codex için tek kullanılabilir kayıt üretti.
