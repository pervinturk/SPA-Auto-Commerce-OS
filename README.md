# ⚡ SPA Auto-Commerce OS — E-Ticaretin Otonom İşletim Sistemi

> *"Veriyi görüntüleme çağı bitti. Karar alma çağı başlıyor."*

**SPA (Smart Platform Automation) Auto-Commerce OS**, e-ticaret 
satıcılarının finansal, lojistik ve operasyonel süreçlerini 
**Üretken Yapay Zeka (Gemini 1.5 Flash)** ve **Endüstri Mühendisliği** 
algoritmaları ile otonomlaştıran masaüstü tabanlı bir 
**Karar Destek Sistemi (DSS)**'dir.

BTK Akademi × Google Hackathon 2026 — **TEAM EXCEL**  
*Pervin Türk · Arhan Ünallı*

---

## 🎯 Problem: E-Ticaretin Görünmeyen Krizi

Türkiye'deki 500.000+ aktif e-ticaret satıcısının %78'i operasyonel 
kararları hâlâ manuel süreçlerle alıyor:

- ⏱ **Zaman Kaybı** — Stok, kargo ve fiyat kararları saatler alıyor
- 📉 **Marj Erozyonu** — Optimize edilmeyen lojistik, görünmez maliyet yaratıyor  
- 🔀 **Veri Dağınıklığı** — Trendyol, finans ve envanter verileri hiç birleşmiyor

**Sonuç:** Satıcılar büyüme değil, hayatta kalma mücadelesi veriyor.

---

## 💡 Çözüm: Bir İşletim Sistemi Olarak E-Ticaret

SPA Auto-Commerce OS, statik raporlamadan **otonom aksiyona** geçişi 
mümkün kılıyor. Sistem yalnızca analiz etmiyor — **karar alıyor ve uyguluyor.**

<img width="1024" height="1536" alt="ChatGPT Image 19 May 2026 18_02_25" src="https://github.com/user-attachments/assets/e8d1af54-d4c8-4ec2-81a6-8468dd4a988c" />

---

## 🌟 Temel Özellikler

### 🤖 Agentic AI — Akıl Hocası
- **ReAct (Reason + Act)** döngüsüyle çalışan otonom karar motoru
- Gemini 1.5 Flash ile doğal dil komutlarını veritabanı emirlerine dönüştürme
- **Human-in-the-Loop**: Kritik aksiyonlar kullanıcı onayıyla tetiklenir
- Her karar, deterministik doğrulama katmanından geçer

### 🛡 Hallucination Safety Layer
Finansal kararlarda yapay zeka hatasını sıfıra indiren 3 katmanlı güvenlik:
1. **AI Önerisi** — Gemini üretir
2. **Deterministik Doğrulama** — Kural motoru ve veri çapraz kontrolü
3. **Güvenli Aksiyon** — Onaylı karar uygulanır veya reddedilir

### 📊 Endüstri Mühendisliği & Lojistik Optimizasyon
| Algoritma | Kullanım Alanı |
|-----------|---------------|
| **Wagner-Whitin** | Dinamik parti büyüklüğü optimizasyonu |
| **TOPSIS** | Çok kriterli kargo firması seçimi |
| **EOQ Modeli** | Ekonomik sipariş miktarı hesaplama |
| **(s,Q) Stok Politikası** | Dinamik sipariş noktası optimizasyonu |
| **MRP Planlaması** | Zaman bazlı malzeme gereksinim hesabı |
| **Parametrik VaR** | Döviz pozisyonu risk analizi |

> `ROP = Günlük Talep × Tedarik Süresi + Emniyet Stoğu`  
> `EOQ = √(2DS / H)`

### 👁 Vision AI — Otonom Veri Girişi
- Ürün fotoğrafından Gemini multimodal ile SEO açıklaması üretimi
- Trendyol kategori tahmini ve filtre ataması
- Manuel giriş süresinde **%90 azalma**

### 💹 Finansal Mühendislik
- NPV & ROI simülasyonu (Amazon TR/EU, Etsy Global, Çoklu Platform)
- Parametrik VaR ile döviz riski yönetimi
- 18 aylık pozitif nakit akışı projeksiyonu

### 🔗 Trendyol API Entegrasyonu
- Gerçek zamanlı sipariş ve ürün senkronizasyonu
- Hata toleranslı retry mekanizması (556 HTTP)
- Canlı hakediş ve fiyat güncelleme

---

## 🛠 Teknoloji Yığını

| Katman | Teknoloji | Neden Seçildi |
|--------|-----------|---------------|
| **AI/LLM** | Google Gemini 1.5 Flash | Hız, maliyet etkinliği, multimodal destek |
| **Agentic** | ReAct pattern + Function Calling | Deterministik + LLM hibrit kontrol |
| **UI** | CustomTkinter + Matplotlib | Düşük gecikme, masaüstü OS hissi |
| **DB** | SQLite (WAL Mode) + SQLAlchemy Async | Yüksek eşzamanlılık, yerel güvenlik |
| **Validasyon** | Pydantic (Strict Schema) | Halüsinasyon koruması, tip güvenliği |
| **Optimizasyon** | NumPy + SciPy | Matematiksel modeller için endüstri standardı |

---

## ⚙️ Kurulum ve Çalıştırma

```bash
# 1. Repoyu klonlayın
git clone https://github.com/TEAM-EXCEL/spa-autocommerce-os.git
cd spa-autocommerce-os

# 2. Bağımlılıkları yükleyin
pip install -r requirements.txt

# 3. Ortam değişkenlerini tanımlayın
cp .env.example .env
# .env dosyasına Gemini API Key'inizi girin:
# GEMINI_API_KEY=your_key_here

# 4. Uygulamayı başlatın
python main.py
```

**Test Senaryoları** (`tests/` klasöründe):
```bash
python -m pytest tests/ -v
# Wagner-Whitin, TOPSIS, Hybrid Gateway
# ve Finansal modüller için 9 faz test kapsamı
```

---

## 🚀 Yol Haritası (Scalability)

---

## 👥 TEAM EXCEL

| Üye | Rol |
|-----|-----|
| **Pervin Türk** | Lead AI Mühendisi — Agentic mimari, Gemini entegrasyonu, Hallucination Safety Layer |
| **Arhan Ünallı** | UI/UX & Analiz Lideri — Dashboard, finansal modelleme, API veri akışı |

---

*BTK Akademi × Google × Girvak — Hackathon 2026*
