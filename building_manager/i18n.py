from .helpers import *

def _norm_key(text):
    return text.replace(_ZW, "").replace("ي", "ی").replace("ك", "ک").strip()


# کدهای خطا در ERROR_MESSAGES نگهداری می‌شوند؛ _RAW فقط برای ترجمه‌ی متن‌های رابط کاربری است.
# آزمون دستی: T("json-import-failed") باید خود کلید را برگرداند.
_RAW = r"""
شارژ | Charge | رسوم | Aidat | Gebühr | Charge | 物业费 | 管理費 | 관리비
پرداختی | Contribution | مساهمة | Katkı | Beitrag | Contribution | 缴款 | 拠出金 | 분담금
فروردین | Farvardin | فروردين | Farvardin | Farvardin | Farvardin | Farvardin | Farvardin | Farvardin
اردیبهشت | Ordibehesht | أرديبهشت | Ordibehesht | Ordibehescht | Ordibehesht | Ordibehesht | Ordibehesht | Ordibehesht
خرداد | Khordad | خرداد | Khordad | Chordad | Khordad | Khordad | Khordad | Khordad
تیر | Tir | تير | Tir | Tir | Tir | Tir | Tir | Tir
مرداد | Mordad | مرداد | Mordad | Mordad | Mordad | Mordad | Mordad | Mordad
شهریور | Shahrivar | شهريور | Şehrivar | Schahriwar | Shahrivar | Shahrivar | Shahrivar | Shahrivar
مهر | Mehr | مهر | Mehr | Mehr | Mehr | Mehr | Mehr | Mehr
آبان | Aban | آبان | Aban | Aban | Aban | Aban | Aban | Aban
آذر | Azar | آذر | Azar | Azar | Azar | Azar | Azar | Azar
دی | Dey | دي | Dey | Dei | Dey | Dey | Dey | Dey
بهمن | Bahman | بهمن | Bahman | Bahman | Bahman | Bahman | Bahman | Bahman
اسفند | Esfand | إسفند | Esfand | Esfand | Esfand | Esfand | Esfand | Esfand
خالی | Vacant | شاغر | Boş | Leer | Libre | 空置 | 空室 | 공실
مالک | Owner | المالك | Malik | Eigentümer | Propriétaire | 业主 | 所有者 | 소유자
مستأجر | Tenant | المستأجر | Kiracı | Mieter | Locataire | 租户 | 賃借人 | 임차인
بهار | Spring | الربيع | İlkbahar | Frühling | Printemps | 春季 | 春 | 봄
تابستان | Summer | الصيف | Yaz | Sommer | Été | 夏季 | 夏 | 여름
پاییز | Autumn | الخريف | Sonbahar | Herbst | Automne | 秋季 | 秋 | 가을
زمستان | Winter | الشتاء | Kış | Winter | Hiver | 冬季 | 冬 | 겨울
ذخیره | Save | حفظ | Kaydet | Speichern | Enregistrer | 保存 | 保存 | 저장
گزارش ایجاد شد. | Report created. | تم إنشاء التقرير. | Rapor oluşturuldu. | Bericht erstellt. | Rapport créé. | 报告已生成。 | レポートを作成しました。 | 보고서가 생성되었습니다.
واحد | Unit | وحدة | Daire | Einheit | Logement | 单元 | 部屋 | 세대
نام | Name | الاسم | Ad | Name | Nom | 姓名 | 名前 | 이름
نوع | Type | النوع | Tür | Typ | Type | 类型 | 種類 | 유형
واریزی | Amount | المبلغ | Tutar | Betrag | Montant | 金额 | 金額 | 금액
حق‌السهم | Share | الحصة | Pay | Anteil | Quote-part | 应摊份额 | 分担額 | 분담액
بدهکاری ماه‌های قبل | Debt from Previous Months | دين الأشهر السابقة | Önceki Aylardan Borç | Schulden aus Vormonaten | Dette des mois précédents | 往月欠款 | 前月までの未払い | 이전 달 미납액
بستانکاری ماه‌های قبل | Credit from Previous Months | رصيد دائن من الأشهر السابقة | Önceki Aylardan Alacak | Guthaben aus Vormonaten | Crédit des mois précédents | 往月余额 | 前月までの過払い | 이전 달 선납액
قابل واریز | Amount Due | المبلغ المستحق | Ödenecek Tutar | Fälliger Betrag | Montant à payer | 应缴金额 | 支払うべき額 | 납부할 금액
مانده حساب | Balance | الرصيد | Bakiye | Saldo | Solde | 余额 | 残高 | 잔액
تاریخ | Date | التاريخ | Tarih | Datum | Date | 日期 | 日付 | 날짜
توضیحات | Notes | ملاحظات | Notlar | Notizen | Notes | 备注 | メモ | 메모
نوع هزینه | Expense Type | نوع المصروف | Gider Türü | Ausgabenart | Type de dépense | 费用类型 | 経費の種類 | 지출 유형
دسته‌بندی | Category | الفئة | Kategori | Kategorie | Catégorie | 类别 | カテゴリ | 분류
مبلغ | Amount | المبلغ | Tutar | Betrag | Montant | 金额 | 金額 | 금액
عنوان | Title | العنوان | Başlık | Titel | Titre | 标题 | タイトル | 제목
صفحه اصلی | Home | الرئيسية | Ana Sayfa | Startseite | Accueil | 主页 | ホーム | 홈
ثبت ماهانه | Monthly Entry | القيد الشهري | Aylık Kayıt | Monatserfassung | Saisie mensuelle | 月度登记 | 月次入力 | 월별 입력
مدیریت واحدها | Manage Units | إدارة الوحدات | Daireleri Yönet | Einheiten verwalten | Gérer les logements | 管理单元 | 部屋の管理 | 세대 관리
بدهکاران | Debtors | المدينون | Borçlular | Schuldner | Débiteurs | 欠款住户 | 未払い者 | 미납자
تنظیمات | Settings | الإعدادات | Ayarlar | Einstellungen | Paramètres | 设置 | 設定 | 설정
رسید پرداخت | Payment Receipt | إيصال الدفع | Ödeme Makbuzu | Zahlungsbeleg | Reçu de paiement | 付款收据 | 支払い領収書 | 납부 영수증
هزینه‌ها | Expenses | المصروفات | Giderler | Ausgaben | Dépenses | 费用 | 経費 | 지출
فایل Excel ایجاد شد. | The Excel file was created. | تم إنشاء ملف Excel. | Excel dosyası oluşturuldu. | Die Excel-Datei wurde erstellt. | Le fichier Excel a été créé. | Excel 文件已生成。 | Excelファイルを作成しました。 | Excel 파일이 생성되었습니다.
واحد {} | Unit {} | الوحدة {} | Daire {} | Einheit {} | Logement {} | {}号单元 | 部屋 {} | {}호
گزارش مالی سالانه PDF | Annual Financial Report (PDF) | التقرير المالي السنوي PDF | Yıllık Mali Rapor (PDF) | Jahresfinanzbericht (PDF) | Rapport financier annuel (PDF) | 年度财务报告（PDF） | 年次会計レポート（PDF） | 연간 재무 보고서(PDF)
خروجی Excel سالانه | Annual Excel Export | تصدير Excel السنوي | Yıllık Excel Çıktısı | Jahres-Excel-Export | Export Excel annuel | 导出年度Excel | 年次Excelエクスポート | 연간 Excel 내보내기
خروجی Excel ماهانه | Monthly Excel Export | تصدير Excel الشهري | Aylık Excel Çıktısı | Monatlicher Excel-Export | Export Excel mensuel | 导出月度Excel | 月次Excelエクスポート | 월간 Excel 내보내기
Excel ماهانه | Monthly Excel | Excel الشهري | Aylık Excel | Monats-Excel | Excel mensuel | 月度 Excel | 月次 Excel | 월간 Excel
Excel ماهانه — دریافتی‌ها | Monthly Excel — Receipts | Excel الشهري — المقبوضات | Aylık Excel — Tahsilatlar | Monats-Excel — Einnahmen | Excel mensuel — Encaissements | 月度 Excel — 收款 | 月次 Excel — 受取 | 월간 Excel — 수입액
Excel ماهانه — هزینه‌ها | Monthly Excel — Expenses | Excel الشهري — المصروفات | Aylık Excel — Giderler | Monats-Excel — Ausgaben | Excel mensuel — Dépenses | 月度 Excel — 费用 | 月次 Excel — 支出 | 월간 Excel — 지출
Excel ماهانه — درآمدهای متفرقه | Monthly Excel — Miscellaneous Income | Excel الشهري — الإيرادات المتنوعة | Aylık Excel — Diğer Gelirler | Monats-Excel — Sonstige Einnahmen | Excel mensuel — Revenus divers | 月度 Excel — 其他收入 | 月次 Excel — その他の収入 | 월간 Excel — 기타 수입
دسته‌بندی هزینه‌ها | Expense Categories | فئات المصروفات | Gider Kategorileri | Ausgabenkategorien | Catégories de dépenses | 费用类别 | 経費カテゴリ | 지출 분류
تومان | Toman | تومان | Toman | Toman | tomans | 土曼 | トマン | 토만
گزارش PDF | PDF Report | تقرير PDF | PDF Raporu | PDF-Bericht | Rapport PDF | PDF报告 | PDFレポート | PDF 보고서
ثبت پرداخت جدید | Add Payment | تسجيل دفعة جديدة | Yeni Ödeme Ekle | Neue Zahlung erfassen | Nouveau paiement | 新增付款 | 支払いを追加 | 새 납부 등록
ویرایش انتخاب | Edit Selected | تعديل المحدد | Seçileni Düzenle | Auswahl bearbeiten | Modifier la sélection | 编辑所选 | 選択を編集 | 선택 항목 수정
حذف انتخاب | Delete Selected | حذف المحدد | Seçileni Sil | Auswahl löschen | Supprimer la sélection | 删除所选 | 選択を削除 | 선택 항목 삭제
ثبت هزینه جدید | Add Expense | تسجيل مصروف جديد | Yeni Gider Ekle | Neue Ausgabe erfassen | Nouvelle dépense | 新增费用 | 経費を追加 | 새 지출 등록
دسته‌بندی‌ها | Categories | الفئات | Kategoriler | Kategorien | Catégories | 类别 | カテゴリ | 분류
افزودن واحد | Add Unit | إضافة وحدة | Daire Ekle | Einheit hinzufügen | Ajouter un logement | 添加单元 | 部屋を追加 | 세대 추가
ویرایش واحد | Edit Unit | تعديل الوحدة | Daireyi Düzenle | Einheit bearbeiten | Modifier le logement | 编辑单元 | 部屋を編集 | 세대 수정
حذف واحد | Delete Unit | حذف الوحدة | Daireyi Sil | Einheit löschen | Supprimer le logement | 删除单元 | 部屋を削除 | 세대 삭제
خروجی PDF | Export PDF | تصدير PDF | PDF Çıktısı | PDF exportieren | Exporter en PDF | 导出PDF | PDFを出力 | PDF 내보내기
تنظیمات منطقی (چندحسابی) | Account Settings (Multi-account) | إعدادات الحسابات (متعددة) | Hesap Ayarları (Çoklu hesap) | Kontoeinstellungen (Mehrere Konten) | Paramètres des comptes (multi-comptes) | 账户设置（多账户） | アカウント設定（複数口座） | 계정 설정(다중 계좌)
مشخصات کلی ساختمان | General Building Details | تفاصيل المبنى العامة | Genel Bina Bilgileri | Allgemeine Gebäudedaten | Détails généraux du bâtiment | 楼宇基本信息 | 建物の基本情報 | 건물 기본 정보
موجودی اولیه کارت اول | Initial Balance of First Account | الرصيد الابتدائي للحساب الأول | Birinci Hesabın Başlangıç Bakiyesi | Anfangssaldo des ersten Kontos | Solde initial du premier compte | 第一账户初始余额 | 1つ目の口座の初期残高 | 첫 번째 계좌 초기 잔액
موجودی اولیه کارت دوم | Initial Balance of Second Account | الرصيد الابتدائي للحساب الثاني | İkinci Hesabın Başlangıç Bakiyesi | Anfangssaldo des zweiten Kontos | Solde initial du second compte | 第二账户初始余额 | 2つ目の口座の初期残高 | 두 번째 계좌 초기 잔액
تنظیمات ظاهری نرم‌افزار | Software Appearance Settings | إعدادات مظهر البرنامج | Yazılım Görünüm Ayarları | Darstellungseinstellungen der Software | Paramètres d'apparence du logiciel | 软件外观设置 | ソフトウェアの外観設定 | 소프트웨어 화면 설정
مدیریت حساب‌ها و کارت‌های مالی | Manage Accounts & Cards | إدارة الحسابات والبطاقات المالية | Hesap ve Kartları Yönet | Konten und Karten verwalten | Gérer les comptes et cartes | 管理账户与银行卡 | 口座とカードの管理 | 계좌 및 카드 관리
وضعیت چندحسابی | Multi-account Status | حالة الحسابات المتعددة | Çoklu Hesap Durumu | Status Mehrfachkonten | État multi-comptes | 多账户状态 | 複数口座の状態 | 다중 계좌 상태
نسخه پشتیبان ایجاد شد. | Backup created. | تم إنشاء النسخة الاحتياطية. | Yedek oluşturuldu. | Sicherung erstellt. | Sauvegarde créée. | 备份已创建。 | バックアップを作成しました。 | 백업이 생성되었습니다.
پشتیبان با موفقیت بازیابی شد. | Backup restored successfully. | تمت استعادة النسخة الاحتياطية بنجاح. | Yedek başarıyla geri yüklendi. | Sicherung erfolgreich wiederhergestellt. | Sauvegarde restaurée avec succès. | 备份已成功恢复。 | バックアップを復元しました。 | 백업이 복원되었습니다.
خطا | Error | خطأ | Hata | Fehler | Erreur | 错误 | エラー | 오류
برای گزارش PDF نصب کنید:\npip install reportlab | To create PDF reports, install:\npip install reportlab | لإنشاء تقارير PDF ثبّت:\npip install reportlab | PDF raporu için şunu kurun:\npip install reportlab | Für PDF-Berichte installieren Sie:\npip install reportlab | Pour créer des rapports PDF, installez :\npip install reportlab | 生成PDF报告请安装：\npip install reportlab | PDFレポートには次をインストール：\npip install reportlab | PDF 보고서를 만들려면 설치하세요:\npip install reportlab
فونت فارسی برای PDF پیدا نشد. فایل Vazirmatn.ttf را در پوشه‌ی fonts کنار برنامه قرار دهید. | No Persian font was found for PDF. Put Vazirmatn.ttf in the "fonts" folder next to the program. | لم يتم العثور على خط فارسي لـ PDF. ضع ملف Vazirmatn.ttf في مجلد fonts بجانب البرنامج. | PDF için Farsça yazı tipi bulunamadı. Vazirmatn.ttf dosyasını programın yanındaki "fonts" klasörüne koyun. | Für das PDF wurde keine persische Schriftart gefunden. Legen Sie Vazirmatn.ttf in den Ordner „fonts“ neben dem Programm. | Aucune police persane trouvée pour le PDF. Placez Vazirmatn.ttf dans le dossier « fonts » à côté du programme. | 未找到可用于PDF的波斯语字体。请将 Vazirmatn.ttf 放在程序旁的 fonts 文件夹中。 | PDF用のペルシア語フォントが見つかりません。Vazirmatn.ttf をプログラムと同じ場所の fonts フォルダに置いてください。 | PDF용 페르시아어 글꼴을 찾을 수 없습니다. Vazirmatn.ttf를 프로그램 옆 fonts 폴더에 넣으세요.
خلاصه مالی | Financial Summary | الملخص المالي | Mali Özet | Finanzübersicht | Résumé financier | 财务摘要 | 会計サマリー | 재무 요약
گزارش مالی سال {} با موفقیت ایجاد شد. | The financial report for {} was created successfully. | تم إنشاء التقرير المالي لسنة {} بنجاح. | {} yılı mali raporu başarıyla oluşturuldu. | Der Finanzbericht für {} wurde erstellt. | Le rapport financier de {} a été créé avec succès. | {}年度财务报告已成功生成。 | {}年の会計レポートを作成しました。 | {}년 재무 보고서가 생성되었습니다.
پرداخت پیدا نشد. | Payment not found. | لم يتم العثور على الدفعة. | Ödeme bulunamadı. | Zahlung nicht gefunden. | Paiement introuvable. | 未找到该付款。 | 支払いが見つかりません。 | 납부 내역을 찾을 수 없습니다.
رسید ایجاد شد. | Receipt created. | تم إنشاء الإيصال. | Makbuz oluşturuldu. | Beleg erstellt. | Reçu créé. | 收据已生成。 | 領収書を作成しました。 | 영수증이 생성되었습니다.
برای خروجی Excel نصب کنید:\npip install openpyxl | To export Excel files, install:\npip install openpyxl | لتصدير ملفات Excel ثبّت:\npip install openpyxl | Excel çıktısı için şunu kurun:\npip install openpyxl | Für den Excel-Export installieren Sie:\npip install openpyxl | Pour exporter en Excel, installez :\npip install openpyxl | 导出Excel请安装：\npip install openpyxl | Excelに出力するには次をインストール：\npip install openpyxl | Excel로 내보내려면 설치하세요:\npip install openpyxl
مدیریت ساختمان | Building Manager | إدارة المبنى | Bina Yönetimi | Gebäudeverwaltung | Gestion de l'immeuble | 楼宇管理 | 建物管理 | 건물 관리
توجه | Notice | تنبيه | Bilgi | Hinweis | Information | 提示 | お知らせ | 알림
هشدار | Warning | تحذير | Uyarı | Warnung | Avertissement | 警告 | 警告 | 경고
تأیید | Confirm | تأكيد | Onayla | Bestätigen | Confirmer | 确认 | 確認 | 확인
شارژ و پرداختی‌ها | Charges & Contributions | الرسوم والمساهمات | Aidat ve Katkılar | Gebühren & Beiträge | Charges et contributions | 物业费与缴款 | 管理費と拠出金 | 관리비 및 분담금
مجموع واریزی‌ها: {} تومان | Total deposits: {} Toman | إجمالي الإيداعات: {} تومان | Toplam yatırım: {} Toman | Summe der Einzahlungen: {} Toman | Total des versements : {} tomans | 存款合计：{} 土曼 | 入金合計：{} トマン | 입금 합계: {} 토만
ابتدا حداقل یک واحد ثبت کنید. | Please add at least one unit first. | يرجى إضافة وحدة واحدة على الأقل أولاً. | Lütfen önce en az bir daire ekleyin. | Bitte legen Sie zuerst mindestens eine Einheit an. | Veuillez d'abord ajouter au moins un logement. | 请先至少添加一个单元。 | 先に部屋を1つ以上登録してください。 | 먼저 세대를 하나 이상 등록하세요.
ابتدا یک مورد را انتخاب کنید. | Please select an item first. | يرجى اختيار عنصر أولاً. | Lütfen önce bir öğe seçin. | Bitte wählen Sie zuerst einen Eintrag aus. | Veuillez d'abord sélectionner un élément. | 请先选择一项。 | 先に項目を選択してください。 | 먼저 항목을 선택하세요.
یک پرداخت را انتخاب کنید. | Please select a payment. | يرجى اختيار دفعة. | Lütfen bir ödeme seçin. | Bitte wählen Sie eine Zahlung aus. | Veuillez sélectionner un paiement. | 请选择一笔付款。 | 支払いを選択してください。 | 납부 내역을 선택하세요.
مجموع هزینه: {} تومان | Total expenses: {} Toman | إجمالي المصروفات: {} تومان | Toplam gider: {} Toman | Gesamtausgaben: {} Toman | Total des dépenses : {} tomans | 费用合计：{} 土曼 | 経費合計：{} トマン | 지출 합계: {} 토만
هزینه پیدا نشد. | Expense not found. | لم يتم العثور على المصروف. | Gider bulunamadı. | Ausgabe nicht gefunden. | Dépense introuvable. | 未找到该费用。 | 経費が見つかりません。 | 지출 내역을 찾을 수 없습니다.
واحد پیدا نشد. | Unit not found. | لم يتم العثور على الوحدة. | Daire bulunamadı. | Einheit nicht gefunden. | Logement introuvable. | 未找到该单元。 | 部屋が見つかりません。 | 세대를 찾을 수 없습니다.
شماره واحد | Unit Number | رقم الوحدة | Daire No | Einheitsnummer | Numéro du logement | 单元编号 | 部屋番号 | 세대 번호
طبقه | Floor | الطابق | Kat | Etage | Étage | 楼层 | 階 | 층
وضعیت | Status | الحالة | Durum | Status | Statut | 状态 | 状態 | 상태
نام مالک | Owner Name | اسم المالك | Malik Adı | Name des Eigentümers | Nom du propriétaire | 业主姓名 | 所有者名 | 소유자 이름
تلفن مالک | Owner Phone | هاتف المالك | Malik Telefonu | Telefon des Eigentümers | Téléphone du propriétaire | 业主电话 | 所有者の電話 | 소유자 전화
نام مستأجر | Tenant Name | اسم المستأجر | Kiracı Adı | Name des Mieters | Nom du locataire | 租户姓名 | 賃借人名 | 임차인 이름
تلفن مستأجر | Tenant Phone | هاتف المستأجر | Kiracı Telefonu | Telefon des Mieters | Téléphone du locataire | 租户电话 | 賃借人の電話 | 임차인 전화
ابتدا یک واحد را انتخاب کنید. | Please select a unit first. | يرجى اختيار وحدة أولاً. | Lütfen önce bir daire seçin. | Bitte wählen Sie zuerst eine Einheit aus. | Veuillez d'abord sélectionner un logement. | 请先选择一个单元。 | 先に部屋を選択してください。 | 먼저 세대를 선택하세요.
واحد غیرفعال شد. | The unit was deactivated. | تم تعطيل الوحدة. | Daire devre dışı bırakıldı. | Die Einheit wurde deaktiviert. | Le logement a été désactivé. | 单元已停用。 | 部屋を無効にしました。 | 세대가 비활성화되었습니다.
جمع مانده: {} تومان | Total outstanding: {} Toman | إجمالي المتبقي: {} تومان | Toplam kalan: {} Toman | Gesamtrest: {} Toman | Total restant : {} tomans | 余额合计：{} 土曼 | 残高合計：{} トマン | 잔액 합계: {} 토만
مدیریت دسته‌بندی هزینه‌ها | Manage Expense Categories | إدارة فئات المصروفات | Gider Kategorilerini Yönet | Ausgabenkategorien verwalten | Gérer les catégories de dépenses | 管理费用类别 | 経費カテゴリの管理 | 지출 분류 관리
افزودن دسته‌بندی | Add Category | إضافة فئة | Kategori Ekle | Kategorie hinzufügen | Ajouter une catégorie | 添加类别 | カテゴリを追加 | 분류 추가
ویرایش دسته‌بندی | Edit Category | تعديل الفئة | Kategoriyi Düzenle | Kategorie bearbeiten | Modifier la catégorie | 编辑类别 | カテゴリを編集 | 분류 수정
فایل انتخاب‌شده همین پایگاه داده فعلی است. | The selected file is the current database itself. | الملف المحدد هو قاعدة البيانات الحالية نفسها. | Seçilen dosya mevcut veritabanının kendisi. | Die gewählte Datei ist die aktuelle Datenbank. | Le fichier sélectionné est la base de données actuelle. | 所选文件就是当前数据库。 | 選択したファイルは現在のデータベースです。 | 선택한 파일은 현재 데이터베이스입니다.
تمام اطلاعات فعلی با پشتیبان جایگزین شود؟ | Replace all current data with the backup? | هل تريد استبدال جميع البيانات الحالية بالنسخة الاحتياطية؟ | Tüm mevcut veriler yedekle değiştirilsin mi? | Alle aktuellen Daten durch die Sicherung ersetzen? | Remplacer toutes les données actuelles par la sauvegarde ? | 要用备份替换当前所有数据吗？ | 現在のデータをすべてバックアップで置き換えますか？ | 현재 모든 데이터를 백업으로 교체할까요?
برای نمایش درست فارسی در PDF نصب کنید:\npip install arabic-reshaper python-bidi | To display Persian text correctly in PDFs, install:\npip install arabic-reshaper python-bidi | لعرض الفارسية بشكل صحيح في PDF ثبّت:\npip install arabic-reshaper python-bidi | PDF'te Farsçanın doğru görünmesi için kurun:\npip install arabic-reshaper python-bidi | Damit Persisch im PDF korrekt angezeigt wird, installieren Sie:\npip install arabic-reshaper python-bidi | Pour afficher correctement le persan dans les PDF, installez :\npip install arabic-reshaper python-bidi | 要在PDF中正确显示波斯语，请安装：\npip install arabic-reshaper python-bidi | PDFでペルシア語を正しく表示するには次をインストール：\npip install arabic-reshaper python-bidi | PDF에서 페르시아어를 올바르게 표시하려면 설치하세요:\npip install arabic-reshaper python-bidi
ساخت یا ذخیره PDF ناموفق بود:\n{} | Creating or saving the PDF failed:\n{} | فشل إنشاء أو حفظ ملف PDF:\n{} | PDF oluşturulamadı veya kaydedilemedi:\n{} | PDF konnte nicht erstellt oder gespeichert werden:\n{} | Échec de la création ou de l'enregistrement du PDF :\n{} | 生成或保存PDF失败：\n{} | PDFの作成または保存に失敗しました：\n{} | PDF를 만들거나 저장하지 못했습니다:\n{}
تلفن | Phone | الهاتف | Telefon | Telefon | Téléphone | 电话 | 電話 | 전화
بدهی ماه‌های قبل | Debt from Previous Months | دين الأشهر السابقة | Önceki Aylardan Borç | Schulden aus Vormonaten | Dette des mois précédents | 往月欠款 | 前月までの未払い | 이전 달 미납액
پرداخت‌شده | Paid | مدفوع | Ödenen | Bezahlt | Payé | 已付 | 支払済み | 납부액
مانده | Remaining | المتبقي | Kalan | Rest | Reste | 余额 | 残り | 잔액
ذخیره‌ی فایل انجام نشد:\n{} | Could not save the file:\n{} | تعذر حفظ الملف:\n{} | Dosya kaydedilemedi:\n{} | Die Datei konnte nicht gespeichert werden:\n{} | Impossible d'enregistrer le fichier :\n{} | 无法保存文件：\n{} | ファイルを保存できませんでした：\n{} | 파일을 저장하지 못했습니다:\n{}
پشتیبان‌گیری | Back up | نسخ احتياطي | Yedekle | Sichern | Sauvegarder | 备份 | バックアップ | 백업
بازیابی پشتیبان | Restore backup | استعادة النسخة الاحتياطية | Yedeği geri yükle | Sicherung wiederherstellen | Restaurer la sauvegarde | 恢复备份 | バックアップを復元 | 백업 복원
خروج | Exit | خروج | Çıkış | Beenden | Quitter | 退出 | 終了 | 종료
پرونده | File | ملف | Dosya | Datei | Fichier | 文件 | ファイル | 파일
واحدها | Units | الوحدات | Daireler | Einheiten | Logements | 单元 | 部屋 | 세대
مالکان | Owners | المالكون | Malikler | Eigentümer | Propriétaires | 业主 | 所有者 | 소유자
مستأجران | Tenants | المستأجرون | Kiracılar | Mieter | Locataires | 租户 | 賃借人 | 임차인
موجودی فعلی {} | Current balance: {} | الرصيد الحالي: {} | Güncel bakiye: {} | Aktueller Kontostand: {} | Solde actuel : {} | 当前余额：{} | 現在の残高：{} | 현재 잔액: {}
شروع ماه {} | Start of month: {} | بداية الشهر: {} | Ay başı: {} | Monatsanfang: {} | Début du mois : {} | 月初：{} | 月初：{} | 월초: {}
پایان ماه {} | End of month: {} | نهاية الشهر: {} | Ay sonu: {} | Monatsende: {} | Fin du mois : {} | 月末：{} | 月末：{} | 월말: {}
کل شارژ تعیین‌شده | Total assessed charge | إجمالي الرسوم المحددة | Belirlenen toplam aidat | Festgelegte Gesamtgebühr | Total des charges fixées | 已设定物业费合计 | 設定済み管理費合計 | 책정된 관리비 합계
واریزی شارژ به {} | Charge deposits to {} | إيداعات الرسوم إلى {} | {} hesabına aidat yatırımı | Gebühreneingänge auf {} | Versements de charges vers {} | 物业费存入 {} | 管理費の入金先 {} | 관리비 입금: {}
بدهی شارژ واحدها | Units' charge debt | ديون رسوم الوحدات | Dairelerin aidat borcu | Gebührenschulden der Einheiten | Dettes de charges des logements | 各单元物业费欠款 | 部屋の管理費未払い | 세대 관리비 미납액
هزینه از {} | Expenses from {} | المصروفات من {} | {} kaynaklı gider | Ausgaben von {} | Dépenses depuis {} | 来自 {} 的支出 | {} からの経費 | {} 지출
پرداخت انتخاب‌شده حذف شود؟ | Delete the selected payment? | هل تريد حذف الدفعة المحددة؟ | Seçilen ödeme silinsin mi? | Die gewählte Zahlung löschen? | Supprimer le paiement sélectionné ? | 要删除所选付款吗？ | 選択した支払いを削除しますか？ | 선택한 납부를 삭제할까요?
مبلغ باید عددی باشد. | The amount must be a number. | يجب أن يكون المبلغ رقماً. | Tutar sayı olmalıdır. | Der Betrag muss eine Zahl sein. | Le montant doit être un nombre. | 金额必须是数字。 | 金額は数値で入力してください。 | 금액은 숫자여야 합니다.
این مبلغ برای {} تا پایان سال {} اعمال شود؟ | Apply this amount from {} to the end of year {}? | هل تريد تطبيق هذا المبلغ من {} حتى نهاية السنة {}؟ | Bu tutar {} ayından {} yılı sonuna kadar uygulansın mı? | Diesen Betrag ab {} bis zum Ende des Jahres {} anwenden? | Appliquer ce montant de {} jusqu'à la fin de l'année {} ? | 是否将此金额从 {} 应用到 {} 年底？ | この金額を {} から {} 年末まで適用しますか？ | 이 금액을 {}부터 {}년 말까지 적용할까요?
حذف انجام نشد:\n{} | Deletion failed:\n{} | فشل الحذف:\n{} | Silme başarısız:\n{} | Löschen fehlgeschlagen:\n{} | Échec de la suppression :\n{} | 删除失败：\n{} | 削除に失敗しました：\n{} | 삭제에 실패했습니다:\n{}
ویرایش پرداخت | Edit Payment | تعديل الدفعة | Ödemeyi Düzenle | Zahlung bearbeiten | Modifier le paiement | 编辑付款 | 支払いを編集 | 납부 수정
ثبت پرداخت | Record Payment | تسجيل دفعة | Ödeme Kaydet | Zahlung erfassen | Enregistrer un paiement | 登记付款 | 支払いを記録 | 납부 기록
هزینه انتخاب‌شده حذف شود؟ | Delete the selected expense? | هل تريد حذف المصروف المحدد؟ | Seçilen gider silinsin mi? | Die gewählte Ausgabe löschen? | Supprimer la dépense sélectionnée ? | 要删除所选费用吗？ | 選択した経費を削除しますか？ | 선택한 지출을 삭제할까요?
ویرایش هزینه | Edit Expense | تعديل المصروف | Gideri Düzenle | Ausgabe bearbeiten | Modifier la dépense | 编辑费用 | 経費を編集 | 지출 수정
ثبت هزینه | Record Expense | تسجيل مصروف | Gider Kaydet | Ausgabe erfassen | Enregistrer une dépense | 登记费用 | 経費を記録 | 지출 기록
فعال | Enabled | مفعّل | Etkin | Aktiv | Activé | 启用 | 有効 | 활성
وضعیت واحد | Unit Status | حالة الوحدة | Daire Durumu | Einheitenstatus | Statut du logement | 单元状态 | 部屋の状態 | 세대 상태
واحد فعال است | Unit is active | الوحدة نشطة | Daire aktif | Einheit ist aktiv | Logement actif | 单元启用中 | 有効な部屋 | 활성 세대
این شماره‌ی واحد قبلاً ثبت شده است. | This unit number already exists. | رقم الوحدة هذا مسجل مسبقاً. | Bu daire numarası zaten kayıtlı. | Diese Einheitennummer existiert bereits. | Ce numéro de logement existe déjà. | 该单元编号已存在。 | この部屋番号は既に登録されています。 | 이미 등록된 세대 번호입니다.
این واحد سابقه‌ی مالی دارد؛ برای حفظ تاریخچه‌ی پرداخت‌ها حذف نمی‌شود و غیرفعال می‌شود. ادامه می‌دهید؟ | This unit has financial history. To keep the payment history it will be deactivated instead of deleted. Continue? | لهذه الوحدة سجل مالي. للحفاظ على تاريخ المدفوعات سيتم تعطيلها بدلاً من حذفها. هل تريد المتابعة؟ | Bu dairenin mali geçmişi var. Ödeme geçmişini korumak için silinmek yerine devre dışı bırakılacak. Devam edilsin mi? | Diese Einheit hat Buchungen. Um die Zahlungshistorie zu erhalten, wird sie deaktiviert statt gelöscht. Fortfahren? | Ce logement a un historique financier. Pour le conserver, il sera désactivé au lieu d'être supprimé. Continuer ? | 该单元有财务记录。为保留付款历史，将停用而不是删除。是否继续？ | この部屋には会計履歴があります。履歴を残すため、削除ではなく無効にします。続行しますか？ | 이 세대에는 재무 기록이 있습니다. 납부 기록을 보존하기 위해 삭제하지 않고 비활성화합니다. 계속할까요?
واحد حذف شود؟ | Delete this unit? | هل تريد حذف هذه الوحدة؟ | Bu daire silinsin mi? | Diese Einheit löschen? | Supprimer ce logement ? | 要删除此单元吗？ | この部屋を削除しますか？ | 이 세대를 삭제할까요?
غیرفعال | Disabled | معطّل | Devre Dışı | Inaktiv | Désactivé | 停用 | 無効 | 비활성
پشتیبان‌گیری انجام نشد:\n{} | Backup failed:\n{} | فشل النسخ الاحتياطي:\n{} | Yedekleme başarısız:\n{} | Sicherung fehlgeschlagen:\n{} | Échec de la sauvegarde :\n{} | 备份失败：\n{} | バックアップに失敗しました：\n{} | 백업에 실패했습니다:\n{}
فایل پشتیبان سالم نیست. | The backup file is corrupted. | ملف النسخة الاحتياطية تالف. | Yedek dosyası bozuk. | Die Sicherungsdatei ist beschädigt. | Le fichier de sauvegarde est corrompu. | 备份文件已损坏。 | バックアップファイルが破損しています。 | 백업 파일이 손상되었습니다.
بازیابی انجام نشد:\n{} | Restore failed:\n{} | فشلت الاستعادة:\n{} | Geri yükleme başarısız:\n{} | Wiederherstellung fehlgeschlagen:\n{} | Échec de la restauration :\n{} | 恢复失败：\n{} | 復元に失敗しました：\n{} | 복원에 실패했습니다:\n{}
کل پرداختی تعیین‌شده | Total assessed contributions | إجمالي المساهمات المحددة | Belirlenen toplam katkı | Festgelegte Gesamtbeiträge | Total des contributions fixées | 已设定缴款额合计 | 設定済み拠出額合計 | 책정된 분담금 합계
واریزی به {} | Deposits to {} | إيداعات إلى {} | {} hesabına yatırılan | Einzahlungen auf {} | Versements vers {} | 存入 {} | 入金先 {} | 입금: {}
بدهی پرداختی واحدها | Units' contribution debt | ديون مساهمات الوحدات | Dairelerin katkı borcu | Beitragsschulden der Einheiten | Dettes de contributions des logements | 各单元缴款欠款 | 部屋の拠出金未払い | 세대 분담금 미납액
شارژ هر واحد ({}) | Charge per Unit ({}) | الرسوم لكل وحدة ({}) | Daire Başına Aidat ({}) | Gebühr pro Einheit ({}) | Charge par logement ({}) | 每单元物业费（{}） | 部屋ごとの管理費（{}） | 세대당 관리비({})
پرداختی هر واحد ({}) | Contribution per Unit ({}) | المساهمة لكل وحدة ({}) | Daire Başına Katkı ({}) | Beitrag pro Einheit ({}) | Contribution par logement ({}) | 每单元缴款额（{}） | 部屋ごとの拠出額（{}） | 세대당 분담금({})
تعیین مبلغ جداگانه برای واحدها | Set Individual Amounts for Units | تحديد مبالغ منفصلة للوحدات | Daireler İçin Ayrı Tutar Belirle | Einzelbeträge je Einheit festlegen | Définir des montants par logement | 为各单元单独设置金额 | 部屋ごとの金額を設定 | 세대별 금액 개별 설정
{} واحد فعال | {} active units | {} وحدة نشطة | {} aktif daire | {} aktive Einheiten | {} logements actifs | {} 个启用单元 | 有効な部屋 {} 件 | 활성 세대 {}개
یک دسته‌بندی را انتخاب کنید. | Please select a category. | يرجى اختيار فئة. | Lütfen bir kategori seçin. | Bitte wählen Sie eine Kategorie aus. | Veuillez sélectionner une catégorie. | 请选择一个类别。 | カテゴリを選択してください。 | 분류를 선택하세요.
دسته‌بندی «سایر» قابل حذف نیست. | The "Other" category cannot be deleted. | لا يمكن حذف فئة «أخرى». | "Diğer" kategorisi silinemez. | Die Kategorie „Sonstiges“ kann nicht gelöscht werden. | La catégorie « Autres » ne peut pas être supprimée. | “其他”类别不能删除。 | 「その他」カテゴリは削除できません。 | '기타' 분류는 삭제할 수 없습니다.
انصراف | Cancel | إلغاء | İptal | Abbrechen | Annuler | 取消 | キャンセル | 취소
فیلدهای الزامی را کامل کنید. | Please fill in the required fields. | يرجى ملء الحقول المطلوبة. | Lütfen zorunlu alanları doldurun. | Bitte füllen Sie die Pflichtfelder aus. | Veuillez remplir les champs obligatoires. | 请填写必填项。 | 必須項目を入力してください。 | 필수 항목을 입력하세요.
ماه قبل | Previous Month | الشهر السابق | Önceki Ay | Vorheriger Monat | Mois précédent | 上个月 | 前の月 | 이전 달
ماه بعد | Next Month | الشهر التالي | Sonraki Ay | Nächster Monat | Mois suivant | 下个月 | 次の月 | 다음 달
ماه‌های سال | Months of the Year | أشهر السنة | Yılın Ayları | Monate des Jahres | Mois de l'année | 全年月份 | 年間の月 | 연간 월별
کل شارژ | Total charge | إجمالي الرسوم | Toplam aidat | Gesamtgebühr | Total des charges | 物业费合计 | 管理費合計 | 관리비 합계
دریافتی | Received | المقبوض | Alınan | Eingenommen | Encaissé | 已收 | 受取額 | 수납액
هزینه | Expense | المصروف | Gider | Ausgabe | Dépense | 费用 | 経費 | 지출
پرداخت کامل: {0} — ناقص: {1} — پرداخت‌نشده: {2} | Fully paid: {0} — Partial: {1} — Unpaid: {2} | مدفوع بالكامل: {0} — جزئي: {1} — غير مدفوع: {2} | Tamamen ödenen: {0} — Kısmi: {1} — Ödenmemiş: {2} | Vollständig bezahlt: {0} — Teilweise: {1} — Unbezahlt: {2} | Payé intégralement : {0} — Partiel : {1} — Impayé : {2} | 全额付款：{0} — 部分付款：{1} — 未付款：{2} | 全額支払い：{0} — 一部支払い：{1} — 未払い：{2} | 완납: {0} — 부분 납부: {1} — 미납: {2}
اعمال تا پایان سال | Apply to Year End | تطبيق حتى نهاية السنة | Yıl Sonuna Kadar Uygula | Bis Jahresende anwenden | Appliquer jusqu'à fin d'année | 应用到年底 | 年末まで適用 | 연말까지 적용
کل: {0} — دریافتی: {1} — مانده وصول: {2} تومان | Total: {0} — Received: {1} — Outstanding: {2} Toman | الإجمالي: {0} — المقبوض: {1} — المتبقي للتحصيل: {2} تومان | Toplam: {0} — Alınan: {1} — Tahsil edilecek: {2} Toman | Gesamt: {0} — Eingenommen: {1} — Offen: {2} Toman | Total : {0} — Encaissé : {1} — Reste à encaisser : {2} tomans | 合计：{0} — 已收：{1} — 待收：{2} 土曼 | 合計：{0} — 受取：{1} — 未回収：{2} トマン | 합계: {0} — 수납: {1} — 미수: {2} 토만
برای هر واحد مبلغ دلخواه را وارد کنید. اگر خالی بماند، مبلغ پیش‌فرض ({}) اعمال می‌شود. | Enter a custom amount for each unit. If left empty, the default amount ({}) is applied. | أدخل مبلغاً مخصصاً لكل وحدة. إذا ترك فارغاً يُطبَّق المبلغ الافتراضي ({}). | Her daire için özel bir tutar girin. Boş bırakılırsa varsayılan tutar ({}) uygulanır. | Geben Sie für jede Einheit einen eigenen Betrag ein. Bleibt das Feld leer, gilt der Standardbetrag ({}). | Saisissez un montant personnalisé pour chaque logement. Si le champ est vide, le montant par défaut ({}) s'applique. | 请为每个单元输入自定义金额。留空则使用默认金额（{}）。 | 各部屋の金額を入力してください。空欄の場合は標準の金額（{}）が適用されます。 | 세대별 금액을 입력하세요. 비워 두면 기본 금액({})이 적용됩니다.
نمایش واحدهای غیرفعال | Show inactive units | إظهار الوحدات المعطلة | Devre dışı daireleri göster | Inaktive Einheiten anzeigen | Afficher les logements désactivés | 显示已停用单元 | 無効な部屋を表示 | 비활성 세대 표시
دسته‌بندی‌های هزینه‌ها | Expense Categories | فئات المصروفات | Gider Kategorileri | Ausgabenkategorien | Catégories de dépenses | 费用类别 | 経費カテゴリ | 지출 분류
نام دسته‌بندی | Category name | اسم الفئة | Kategori adı | Name der Kategorie | Nom de la catégorie | 类别名称 | カテゴリ名 | 분류 이름
این دسته‌بندی در {} هزینه استفاده شده است.\nابتدا این هزینه‌ها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟ | This category is used in {} expenses.\nThese expenses will first be moved to “Other”.\nContinue? | تُستخدم هذه الفئة في {} من المصروفات.\nسيتم نقل هذه المصروفات أولاً إلى «أخرى».\nهل تريد المتابعة؟ | Bu kategori {} giderde kullanılıyor.\nBu giderler önce “Diğer” kategorisine taşınacak.\nDevam edilsin mi? | Diese Kategorie wird in {} Ausgaben verwendet.\nDiese Ausgaben werden zuerst zu „Sonstige“ verschoben.\nFortfahren? | Cette catégorie est utilisée dans {} dépenses.\nCes dépenses seront d’abord transférées vers « Autre ».\nContinuer ? | 此类别用于 {} 条费用记录。\n这些费用将先转移到“其他”。\n是否继续？ | このカテゴリは {} 件の経費で使用されています。\nこれらの経費は先に「その他」へ移動されます。\n続行しますか？ | 이 분류는 {}개의 지출 항목에서 사용 중입니다.\n해당 지출은 먼저 “기타”로 이동됩니다.\n계속하시겠습니까?
افزودن | Add | إضافة | Ekle | Hinzufügen | Ajouter | 添加 | 追加 | 추가
ویرایش | Edit | تعديل | Düzenle | Bearbeiten | Modifier | 编辑 | 編集 | 수정
حذف | Delete | حذف | Sil | Löschen | Supprimer | 删除 | 削除 | 삭제
بستن | Close | إغلاق | Kapat | Schließen | Fermer | 关闭 | 閉じる | 닫기
پایگاه داده SQLite | SQLite database | قاعدة بيانات SQLite | SQLite veritabanı | SQLite-Datenbank | Base de données SQLite | SQLite 数据库 | SQLiteデータベース | SQLite 데이터베이스
همه فایل‌ها | All files | كل الملفات | Tüm dosyalar | Alle Dateien | Tous les fichiers | 所有文件 | すべてのファイル | 모든 파일
پاکسازی | Clear | مسح | Temizle | Leeren | Effacer | 清除 | クリア | 지우기
سال مالی | Financial Year | السنة المالية | Mali Yıl | Geschäftsjahr | Exercice | 财务年度 | 会計年度 | 회계 연도
مبلغ هر واحد | Amount per Unit | المبلغ لكل وحدة | Daire Başına Tutar | Betrag pro Einheit | Montant par logement | 每单元金额 | 部屋ごとの金額 | 세대당 금액
این دسته‌بندی قبلاً وجود دارد. | This category already exists. | هذه الفئة موجودة مسبقاً. | Bu kategori zaten var. | Diese Kategorie existiert bereits. | Cette catégorie existe déjà. | 该类别已存在。 | このカテゴリは既に存在します。 | 이미 있는 분류입니다.
این نام قبلاً وجود دارد. | This name already exists. | هذا الاسم موجود مسبقاً. | Bu ad zaten var. | Dieser Name existiert bereits. | Ce nom existe déjà. | 该名称已存在。 | この名前は既に存在します。 | 이미 있는 이름입니다.
جستجو و فیلتر | Search & Filter | بحث وتصفية | Ara ve Filtrele | Suchen & Filtern | Rechercher et filtrer | 搜索与筛选 | 検索とフィルター | 검색 및 필터
مبلغ باید بیشتر از صفر باشد. | The amount must be greater than zero. | يجب أن يكون المبلغ أكبر من صفر. | Tutar sıfırdan büyük olmalıdır. | Der Betrag muss größer als null sein. | Le montant doit être supérieur à zéro. | 金额必须大于零。 | 金額は0より大きくしてください。 | 금액은 0보다 커야 합니다.
تاریخ نامعتبر است. نمونه: {} | Invalid date. Example: {} | تاريخ غير صالح. مثال: {} | Geçersiz tarih. Örnek: {} | Ungültiges Datum. Beispiel: {} | Date invalide. Exemple : {} | 日期无效。示例：{} | 無効な日付です。例：{} | 날짜가 올바르지 않습니다. 예: {}
مرتب‌سازی: | Sort: | الترتيب: | Sıralama: | Sortierung: | Trier : | 排序： | 並べ替え： | 정렬:
ترتیب دستی | Manual order | ترتيب يدوي | Manuel sıralama | Manuelle Reihenfolge | Ordre manuel | 手动排序 | 手動順序 | 수동 정렬
اعمال | Apply | تطبيق | Uygula | Anwenden | Appliquer | 应用 | 適用 | 적용
گزارش ماهانه — خلاصه مالی | Monthly report — Financial summary | التقرير الشهري — الملخص المالي | Aylık rapor — Mali özet | Monatsbericht — Finanzübersicht | Rapport mensuel — Résumé financier | 月度报告 — 财务摘要 | 月次レポート — 財務概要 | 월간 보고서 — 재무 요약
گزارش ماهانه — هزینه‌ها | Monthly report — Expenses | التقرير الشهري — المصروفات | Aylık rapor — Giderler | Monatsbericht — Ausgaben | Rapport mensuel — Dépenses | 月度报告 — 费用 | 月次レポート — 支出 | 월간 보고서 — 지출
گزارش ماهانه — درآمدهای متفرقه | Monthly report — Miscellaneous income | التقرير الشهري — الإيرادات المتنوعة | Aylık rapor — Diğer gelirler | Monatsbericht — Sonstige Einnahmen | Rapport mensuel — Revenus divers | 月度报告 — 其他收入 | 月次レポート — その他の収入 | 월간 보고서 — 기타 수입
گزارش سالانه — درآمدهای متفرقه | Annual report — Miscellaneous income | التقرير السنوي — الإيرادات المتنوعة | Yıllık rapor — Diğer gelirler | Jahresbericht — Sonstige Einnahmen | Rapport annuel — Revenus divers | 年度报告 — 其他收入 | 年次レポート — その他の収入 | 연간 보고서 — 기타 수입
Excel سالانه — درآمدهای متفرقه | Annual Excel — Miscellaneous income | Excel السنوي — الإيرادات المتنوعة | Yıllık Excel — Diğer gelirler | Jahres-Excel — Sonstige Einnahmen | Excel annuel — Revenus divers | 年度 Excel — 其他收入 | 年次 Excel — その他の収入 | 연간 Excel — 기타 수입
گزارش ماهانه — دریافتی‌ها | Monthly report — Receipts | التقرير الشهري — المقبوضات | Aylık rapor — Tahsilatlar | Monatsbericht — Einnahmen | Rapport mensuel — Encaissements | 月度报告 — 收款 | 月次レポート — 受取 | 월간 보고서 — 수입액
گزارش سالانه — خلاصه مالی | Annual report — Financial summary | التقرير السنوي — الملخص المالي | Yıllık rapor — Mali özet | Jahresbericht — Finanzübersicht | Rapport annuel — Résumé financier | 年度报告 — 财务摘要 | 年次レポート — 財務概要 | 연간 보고서 — 재무 요약
گزارش سالانه — روند ماهانه | Annual report — Monthly trend | التقرير السنوي — الاتجاه الشهري | Yıllık rapor — Aylık eğilim | Jahresbericht — Monatsverlauf | Rapport annuel — Tendance mensuelle | 年度报告 — 月度趋势 | 年次レポート — 月別推移 | 연간 보고서 — 월별 추이
گزارش سالانه — هزینه‌ها بر اساس دسته‌بندی | Annual report — Expenses by category | التقرير السنوي — المصروفات حسب الفئة | Yıllık rapor — Kategoriye göre giderler | Jahresbericht — Ausgaben nach Kategorie | Rapport annuel — Dépenses par catégorie | 年度报告 — 按类别统计费用 | 年次レポート — カテゴリ別支出 | 연간 보고서 — 분류별 지출
گزارش سالانه — دریافتی‌ها | Annual report — Receipts | التقرير السنوي — المقبوضات | Yıllık rapor — Tahsilatlar | Jahresbericht — Einnahmen | Rapport annuel — Encaissements | 年度报告 — 收款 | 年次レポート — 受取 | 연간 보고서 — 수입액
گزارش سالانه — هزینه‌ها | Annual report — Expenses | التقرير السنوي — المصروفات | Yıllık rapor — Giderler | Jahresbericht — Ausgaben | Rapport annuel — Dépenses | 年度报告 — 费用 | 年次レポート — 支出 | 연간 보고서 — 지출
گزارش بدهکاران — جدول بدهکاران | Debtors report — Debtors table | تقرير المدينين — جدول المدينين | Borçlular raporu — Borçlular tablosu | Schuldnerbericht — Schuldnertabelle | Rapport des débiteurs — Tableau des débiteurs | 欠款人报告 — 欠款人表格 | 未払い者レポート — 未払い者一覧 | 미납자 보고서 — 미납자 표
Excel سالانه — خلاصه ماهانه | Annual Excel — Monthly summary | Excel السنوي — الملخص الشهري | Yıllık Excel — Aylık özet | Jahres-Excel — Monatsübersicht | Excel annuel — Résumé mensuel | 年度 Excel — 月度摘要 | 年次 Excel — 月次概要 | 연간 Excel — 월별 요약
Excel سالانه — دریافتی‌ها | Annual Excel — Receipts | Excel السنوي — المقبوضات | Yıllık Excel — Tahsilatlar | Jahres-Excel — Einnahmen | Excel annuel — Encaissements | 年度 Excel — 收款 | 年次 Excel — 受取 | 연간 Excel — 수입액
Excel سالانه — هزینه‌ها | Annual Excel — Expenses | Excel السنوي — المصروفات | Yıllık Excel — Giderler | Jahres-Excel — Ausgaben | Excel annuel — Dépenses | 年度 Excel — 费用 | 年次 Excel — 支出 | 연간 Excel — 지출
مبلغ از کم به زیاد | Amount: Low to High | المبلغ: من الأقل إلى الأعلى | Tutar: Artan | Betrag: Aufsteigend | Montant : croissant | 金额：从低到高 | 金額：昇順 | 금액: 낮은순
مبلغ از زیاد به کم | Amount: High to Low | المبلغ: من الأعلى إلى الأقل | Tutar: Azalan | Betrag: Absteigend | Montant : décroissant | 金额：从高到低 | 金額：降順 | 금액: 높은순
تاریخ از قدیم به جدید | Date: Oldest to Newest | التاريخ: من الأقدم إلى الأحدث | Tarih: Eskiden yeniye | Datum: Älteste zuerst | Date : du plus ancien au plus récent | 日期：从早到晚 | 日付：古い順 | 날짜: 오래된순
تاریخ از جدید به قدیم | Date: Newest to Oldest | التاريخ: من الأحدث إلى الأقدم | Tarih: Yeniden eskiye | Datum: Neueste zuerst | Date : du plus récent au plus ancien | 日期：从晚到早 | 日付：新しい順 | 날짜: 최신순
بر اساس واحدها | By unit | حسب الوحدة | Daireye göre | Nach Einheit | Par logement | 按单元 | 部屋別 | 세대별
مانده از کم به زیاد | Remaining: Low to High | المتبقي: من الأقل إلى الأعلى | Kalan: Artan | Restbetrag: Aufsteigend | Solde : croissant | 余额：从低到高 | 残額：昇順 | 잔액: 낮은순
مانده از زیاد به کم | Remaining: High to Low | المتبقي: من الأعلى إلى الأقل | Kalan: Azalan | Restbetrag: Absteigend | Solde : décroissant | 余额：从高到低 | 残額：降順 | 잔액: 높은순
بر اساس دسته‌بندی | By category | حسب الفئة | Kategoriye göre | Nach Kategorie | Par catégorie | 按类别 | カテゴリ別 | 분류별
بر اساس عنوان | By title | حسب العنوان | Başlığa göre | Nach Titel | Par Titel | 按标题 | タイトル別 | 제목별
بر اساس نوع هزینه | By expense type | حسب نوع المصروف | Gider türüne göre | Nach Ausgabenart | Par type de dépense | 按费用类型 | 費用種別 | 지출 유형별
بر اساس نوع پرداخت | By payment type | حسب نوع الدفع | Ödeme türüne göre | Nach Zahlungsart | Par type de paiement | 按付款类型 | 支払種別 | 납부 유형별
موجودی از کم به زیاد | Balance: Low to High | الرصيد: من الأقل إلى الأعلى | Bakiye: Artan | Kontostand: Aufsteigend | Solde : croissant | 余额：从低到高 | 残高：昇順 | 잔액: 낮은순
موجودی از زیاد به کم | Balance: High to Low | الرصيد: من الأعلى إلى الأقل | Bakiye: Azalan | Kontostand: Absteigend | Solde : décroissant | 余额：从高到低 | 残高：降順 | 잔액: 높은순
مجموع از کم به زیاد | Total: Low to High | الإجمالي: من الأقل إلى الأعلى | Toplam: Artan | Summe: Aufsteigend | Total : croissant | 总计：从低到高 | 合計：昇順 | 합계: 낮은순
مجموع از زیاد به کم | Total: High to Low | الإجمالي: من الأعلى إلى الأقل | Toplam: Azalan | Summe: Absteigend | Total : décroissant | 总计：从高到低 | 合計：降順 | 합계: 높은순
بر اساس نام | By name | حسب الاسم | Ada göre | Nach Name | Par nom | 按名称 | 名前順 | 이름순
بر اساس حساب | By account | حسب الحساب | Hesaba göre | Nach Konto | Par compte | 按账户 | 口座別 | 계좌별
درآمدهای متفرقه | Miscellaneous Income | الإيرادات المتنوعة | Diğer Gelirler | Sonstige Einnahmen | Revenus divers | 其他收入 | その他の収入 | 기타 수입
درآمد متفرقه | Miscellaneous income | دخل متنوع | Diğer gelir | Sonstige Einnahme | Revenu divers | 其他收入 | その他の収入 | 기타 수입
ثبت درآمد جدید | Add Income | إضافة دخل جديد | Yeni Gelir Ekle | Neue Einnahme erfassen | Ajouter un revenu | 添加收入 | 収入を追加 | 수입 추가
ویرایش درآمد متفرقه | Edit Miscellaneous Income | تعديل الإيرادات المتنوعة | Diğer Geliri Düzenle | Sonstige Einnahme bearbeiten | Modifier le revenu divers | 编辑其他收入 | その他の収入を編集 | 기타 수입 수정
ثبت درآمد متفرقه | Record Miscellaneous Income | تسجيل دخل متنوع | Diğer Gelir Kaydet | Sonstige Einnahme erfassen | Enregistrer un revenu divers | 记录其他收入 | その他の収入を記録 | 기타 수입 기록
مجموع درآمد متفرقه: {} تومان | Total miscellaneous income: {} Toman | إجمالي الإيرادات المتنوعة: {} تومان | Toplam diğer gelir: {} Toman | Sonstige Einnahmen gesamt: {} Toman | Total des revenus divers : {} tomans | 其他收入总额：{} 土曼 | その他の収入合計：{} トマン | 기타 수입 합계: {} 토만
درآمد انتخاب‌شده حذف شود؟ | Delete the selected income? | هل تريد حذف الدخل المحدد؟ | Seçilen gelir silinsin mi? | Ausgewählte Einnahme löschen? | Supprimer le revenu sélectionné ? | 删除所选收入？ | 選択した収入を削除しますか？ | 선택한 수입을 삭제할까요?
منبع درآمد | Income Source | مصدر الدخل | Gelir Kaynağı | Einnahmequelle | Source du revenu | 收入来源 | 収入源 | 수입 출처
تاریخ دریافت | Date Received | تاريخ الاستلام | Alınma Tarihi | Eingangsdatum | Date de réception | 收款日期 | 受取日 | 수령일
حساب مقصد | Destination Account | الحساب المستلم | Hedef Hesap | Zielkonto | Compte destinataire | 收款账户 | 入金先口座 | 입금 계좌
واریز به حساب | Deposit to Account | إيداع في الحساب | Hesaba Yatır | Auf Konto einzahlen | Verser sur le compte | 存入账户 | 口座に入金 | 계좌에 입금

مدیریت دسته‌بندی‌ها | Manage Categories | إدارة الفئات | Kategorileri Yönet | Kategorien verwalten | Gérer les catégories | 管理类别 | カテゴリを管理 | 분류 관리
دسته‌بندی منبع درآمد | Income Source Categories | فئات مصادر الدخل | Gelir Kaynağı Kategorileri | Einnahmequellen-Kategorien | Catégories de sources de revenus | 收入来源类别 | 収入源カテゴリ | 수입원 분류
منابع درآمد | Income Sources | مصادر الدخل | Gelir Kaynakları | Einnahmequellen | Sources de revenus | 收入来源 | 収入源 | 수입원
افزودن منبع درآمد | Add Income Source | إضافة مصدر دخل | Gelir Kaynağı Ekle | Einnahmequelle hinzufügen | Ajouter une source de revenu | 添加收入来源 | 収入源を追加 | 수입원 추가
ویرایش منبع درآمد | Edit Income Source | تعديل مصدر الدخل | Gelir Kaynağını Düzenle | Einnahmequelle bearbeiten | Modifier la source de revenu | 编辑收入来源 | 収入源を編集 | 수입원 수정
نام منبع درآمد | Income Source Name | اسم مصدر الدخل | Gelir Kaynağı Adı | Name der Einnahmequelle | Nom de la source de revenu | 收入来源名称 | 収入源名 | 수입원 이름
درآمد پیدا نشد. | Income not found. | لم يتم العثور على الدخل. | Gelir bulunamadı. | Einnahme nicht gefunden. | Revenu introuvable. | 未找到收入记录。 | 収入が見つかりません。 | 수입 내역을 찾을 수 없습니다.
وارد کردن اطلاعات قدیمی از فایل‌های JSON انجام نشد؛ هیچ بخشی از واردسازی ناقص ذخیره نشده است.\nجزئیات خطا: {} | Importing legacy data from JSON files failed; no incomplete import was saved.\nError details: {} | فشل استيراد البيانات القديمة من ملفات JSON؛ لم يتم حفظ أي استيراد غير مكتمل.\nتفاصيل الخطأ: {} | Eski JSON verilerinin içe aktarılması başarısız oldu; eksik içe aktarma kaydedilmedi.\nHata ayrıntıları: {} | Der Import alter JSON-Daten ist fehlgeschlagen; es wurden keine unvollständigen Daten gespeichert.\nFehlerdetails: {} | L’importation des anciennes données JSON a échoué ; aucune importation incomplète n’a été enregistrée.\nDétails de l’erreur : {} | 从旧 JSON 文件导入数据失败；未保存任何不完整的导入内容。\n错误详情：{} | 古い JSON ファイルからのデータのインポートに失敗しました。不完全なデータは保存されていません。\nエラーの詳細：{} | 이전 JSON 데이터 가져오기에 실패했습니다. 불완전한 가져오기는 저장되지 않았습니다.\n오류 세부정보: {}
این منبع درآمد در {} درآمد استفاده شده است.\nابتدا این درآمدها به «سایر» منتقل می‌شوند.\nادامه می‌دهید؟ | This income source is used in {} income entries.\nThese entries will first be moved to “Other”.\nContinue? | يُستخدم مصدر الدخل هذا في {} من قيود الدخل.\nسيتم نقل هذه القيود أولاً إلى «أخرى».\nهل تريد المتابعة؟ | Bu gelir kaynağı {} gelir kaydında kullanılıyor.\nBu kayıtlar önce “Diğer” kategorisine taşınacak.\nDevam edilsin mi? | Diese Einnahmequelle wird in {} Einnahmen verwendet.\nDiese Einträge werden zuerst zu „Sonstige“ verschoben.\nFortfahren? | Cette source de revenus est utilisée dans {} écritures.\nCes écritures seront d’abord transférées vers « Autre ».\nContinuer ? | 此收入来源用于 {} 条收入记录。\n这些记录将先转移到“其他”。\n是否继续？ | この収入源は {} 件の収入記録で使用されています。\nこれらの記録は先に「その他」へ移動されます。\n続行しますか？ | 이 수입 출처는 {}개의 수입 항목에서 사용 중입니다.\n해당 항목은 먼저 “기타”로 이동됩니다.\n계속하시겠습니까?
راهنما | Help | مساعدة | Yardım | Hilfe | Aide | 帮助 | ヘルプ | 도움말
گزارش خطاها | Error Logs | سجلات الأخطاء | Hata kayıtları | Fehlerprotokolle | Journaux d’erreurs | 错误日志 | エラーログ | 오류 로그
برای این حساب بدهیِ تسویه‌نشده‌ای وجود ندارد. | There is no outstanding debt for this account. | لا توجد ديون مستحقة غير مسددة لهذا الحساب. | Bu hesap için ödenmemiş borç bulunmuyor. | Für dieses Konto bestehen keine offenen Schulden. | Aucun impayé n’est dû pour ce compte. | 此账户没有未结清的欠款。 | この口座に未精算の未払い金はありません。 | 이 계정에는 미결제 부채가 없습니다.
سال یا ماه معتبر نیست. | Invalid year or month. | السنة أو الشهر غير صالح. | Yıl veya ay geçersiz. | Jahr oder Monat ist ungültig. | Année ou mois invalide. | 年份或月份无效。 | 年または月が無効です。 | 연도 또는 월이 올바르지 않습니다.
تنظیمات پیشرفته ساختمان | Advanced Building Settings | إعدادات المبنى المتقدمة | Gelişmiş Bina Ayarları | Erweiterte Gebäudeeinstellungen | Paramètres avancés du bâtiment | 高级楼宇设置 | 建物の詳細設定 | 고급 건물 설정
درآمد متفرقه از {} | Miscellaneous income from {} | إيرادات متنوعة من {} | {} kaynaklı diğer gelir | Sonstige Einnahmen von {} | Revenus divers de {} | 来自 {} 的其他收入 | {} からのその他の収入 | {}에서 발생한 기타 수입
عادی (Normal) | Normal | عادي | Normal | Normal | Normal | 普通 | 標準 | 보통
بزرگ (Large) | Large | كبير | Büyük | Groß | Grand | 大 | 大 | 크게
روشن | Light | فاتح | Açık | Hell | Clair | 浅色 | ライト | 밝게
تیره | Dark | داكن | Koyu | Dunkel | Sombre | 深色 | ダーク | 어둡게
از ابتدای همان ماه؛ دیگر شارژ نگیرد | From the beginning of that month; no further charge | من بداية الشهر نفسه؛ لا تُفرض رسوم بعد ذلك | Aynı ayın başından itibaren; artık aidat alınmasın | Ab Monatsbeginn; keine weiteren Gebühren | Dès le début du mois ; ne plus facturer | 从该月初开始，不再收取费用 | その月の初めから請求しない | 해당 월 초부터 더 이상 부과하지 않음
تا پایان همین ماه شارژ شود؛ از ماه بعد متوقف شود | Charge through this month; stop from next month | تُفرض الرسوم حتى نهاية هذا الشهر؛ وتتوقف من الشهر التالي | Bu ayın sonuna kadar aidat alınsın; gelecek aydan itibaren durdurulsun | Bis Monatsende berechnen; ab dem Folgemonat stoppen | Facturer jusqu’à la fin du mois, puis arrêter le mois suivant | 收取至本月底；从下个月起停止 | 今月末まで請求し、翌月から停止 | 이번 달 말까지 부과하고 다음 달부터 중단
مبلغ نمی‌تواند منفی باشد. | Amount cannot be negative. | لا يمكن أن يكون المبلغ سالبًا. | Tutar negatif olamaz. | Der Betrag darf nicht negativ sein. | Le montant ne peut pas être négatif. | 金额不能为负数。 | 金額を負にすることはできません。 | 금액은 음수일 수 없습니다.
ترتیب پیش‌فرض جدول‌ها در هر نوع خروجی را جداگانه انتخاب کنید. | Choose the default table order separately for each export type. | اختر ترتيب الجدول الافتراضي بشكل منفصل لكل نوع تصدير. | Her dışa aktarma türü için varsayılan tablo sırasını ayrı seçin. | Wählen Sie die Standardtabellenreihenfolge für jeden Exporttyp separat. | Choisissez séparément l’ordre par défaut des tableaux pour chaque type d’exportation. | 为每种导出类型分别选择默认表格顺序。 | 出力形式ごとに既定の表順を選択してください。 | 내보내기 유형별 기본 표 순서를 각각 선택하세요.
ذخیره کلیه تغییرات تنظیمات | Save All Settings | حفظ جميع الإعدادات | Tüm ayarları kaydet | Alle Einstellungen speichern | Enregistrer tous les paramètres | 保存所有设置 | すべての設定を保存 | 모든 설정 저장
ترتیب پیش‌فرض برنامه | Application Default Order | الترتيب الافتراضي للتطبيق | Uygulama Varsayılan Sırası | Standardreihenfolge der Anwendung | Ordre par défaut de l’application | 程序默认顺序 | アプリの既定順序 | 앱 기본 순서
گزارش چندماهه — خلاصه مالی | Multi-month report — Financial summary | تقرير عدة أشهر — الملخص المالي | Çok aylı rapor — Mali özet | Mehrmonatsbericht — Finanzübersicht | Rapport multi-mois — Résumé financier | 多月报告 — 财务摘要 | 複数月レポート — 財務概要 | 여러 달 보고서 — 재무 요약
گزارش چندماهه — روند ماهانه | Multi-month report — Monthly trend | تقرير عدة أشهر — الاتجاه الشهري | Çok aylı rapor — Aylık eğilim | Mehrmonatsbericht — Monatsverlauf | Rapport multi-mois — Tendance mensuelle | 多月报告 — 月度趋势 | 複数月レポート — 月別推移 | 여러 달 보고서 — 월별 추이
گزارش چندماهه — هزینه‌ها بر اساس دسته‌بندی | Multi-month report — Expenses by category | تقرير عدة أشهر — المصروفات حسب الفئة | Çok aylı rapor — Kategoriye göre giderler | Mehrmonatsbericht — Ausgaben nach Kategorie | Rapport multi-mois — Dépenses par catégorie | 多月报告 — 按类别统计费用 | 複数月レポート — カテゴリ別支出 | 여러 달 보고서 — 분류별 지출
گزارش چندماهه — دریافتی‌ها | Multi-month report — Receipts | تقرير عدة أشهر — المقبوضات | Çok aylı rapor — Tahsilatlar | Mehrmonatsbericht — Einnahmen | Rapport multi-mois — Encaissements | 多月报告 — 收款 | 複数月レポート — 受取 | 여러 달 보고서 — 수입액
گزارش چندماهه — هزینه‌ها | Multi-month report — Expenses | تقرير عدة أشهر — المصروفات | Çok aylı rapor — Giderler | Mehrmonatsbericht — Ausgaben | Rapport multi-mois — Dépenses | 多月报告 — 费用 | 複数月レポート — 支出 | 여러 달 보고서 — 지출
گزارش چندماهه — درآمدهای متفرقه | Multi-month report — Miscellaneous income | تقرير عدة أشهر — الإيرادات المتنوعة | Çok aylı rapor — Diğer gelirler | Mehrmonatsbericht — Sonstige Einnahmen | Rapport multi-mois — Revenus divers | 多月报告 — 其他收入 | 複数月レポート — その他の収入 | 여러 달 보고서 — 기타 수입
PDF ماهانه | Monthly PDF | PDF شهري | Aylık PDF | Monats-PDF | PDF mensuel | 月度 PDF | 月次 PDF | 월간 PDF
PDF سالانه | Annual PDF | PDF سنوي | Yıllık PDF | Jahres-PDF | PDF annuel | 年度 PDF | 年次 PDF | 연간 PDF
PDF بدهکاران | Debtors PDF | PDF المدينين | Borçlular PDF | Schuldner-PDF | PDF des débiteurs | 欠款人 PDF | 未払い者 PDF | 미납자 PDF
Excel سالانه | Annual Excel | Excel سنوي | Yıllık Excel | Jahres-Excel | Excel annuel | 年度 Excel | 年次 Excel | 연간 Excel
گزارش مالی چندماهه PDF | Multi-month Financial Report (PDF) | تقرير مالي لعدة أشهر PDF | Çok Aylı Mali Rapor (PDF) | Mehrmonatiger Finanzbericht (PDF) | Rapport financier sur plusieurs mois (PDF) | 多月财务报告（PDF） | 複数月財務レポート（PDF） | 여러 달 재무 보고서(PDF)
انتخاب ماه‌های گزارش | Select report months | اختر أشهر التقرير | Rapor aylarını seçin | Berichtsmonate auswählen | Sélectionner les mois du rapport | 选择报告月份 | レポート対象月を選択 | 보고서 월 선택
حداقل یک ماه را انتخاب کنید. | Select at least one month. | اختر شهراً واحداً على الأقل. | En az bir ay seçin. | Wählen Sie mindestens einen Monat aus. | Sélectionnez au moins un mois. | 请至少选择一个月份。 | 少なくとも1か月を選択してください。 | 최소 한 달을 선택하세요.
انتخاب همه | Select all | تحديد الكل | Tümünü seç | Alle auswählen | Tout sélectionner | 全选 | すべて選択 | 모두 선택
لغو انتخاب همه | Clear all | إلغاء تحديد الكل | Seçimi temizle | Auswahl aufheben | Tout désélectionner | 全部取消 | すべて解除 | 모두 선택 해제
سال گزارش | Report year | سنة التقرير | Rapor yılı | Berichtsjahr | Année du rapport | 报告年份 | レポート年 | 보고 연도
گزارش مالی ماه‌های انتخاب‌شده سال {} | Financial report for selected months of {} | التقرير المالي للأشهر المحددة من {} | {} yılının seçilen ayları için mali rapor | Finanzbericht für die ausgewählten Monate {} | Rapport financier pour les mois sélectionnés de {} | {}年所选月份的财务报告 | {}年の選択月の財務レポート | {}년 선택한 달의 재무 보고서
سایر | Other | أخرى | Diğer | Sonstige | Autre | 其他 | その他 | 기타
وارد کردن اطلاعات قدیمی از فایل‌های JSON انجام نشد؛ جزئیات خطا: {} | Failed to import legacy JSON data; details: {} | فشل استيراد بيانات JSON القديمة؛ التفاصيل: {} | Eski JSON verileri içe aktarılamadı; ayrıntılar: {} | Alte JSON-Daten konnten nicht importiert werden; Details: {} | Échec de l’importation des anciennes données JSON ; détails : {} | 导入旧 JSON 数据失败；详情：{} | 旧 JSON データのインポートに失敗しました。詳細：{} | 이전 JSON 데이터를 가져오지 못했습니다. 세부 정보: {}
مبلغ باید عدد صحیح باشد؛ اعشار مجاز نیست. | Amount must be a whole number; decimals are not allowed. | يجب أن يكون المبلغ عددًا صحيحًا؛ الكسور العشرية غير مسموح بها. | Tutar tam sayı olmalıdır; ondalık değerlere izin verilmez. | Der Betrag muss eine ganze Zahl sein; Dezimalstellen sind nicht zulässig. | Le montant doit être un nombre entier ; les décimales ne sont pas autorisées. | 金额必须为整数；不允许小数。 | 金額は整数である必要があります。小数は使用できません。 | 금액은 정수여야 하며 소수는 허용되지 않습니다.
"""



class I18n:
    def __init__(self):
        self.lang = "fa"
        self._tables = {}

    def set_language(self, lang):
        # توجه: هماهنگی فونت UI مسئولیت App است (متد App._apply_ui_font)؛ I18n فقط زبان را نگه می‌دارد.
        # آزمون دستی: تغییر زبان باید فقط self.lang را عوض کند و App ظاهر را جداگانه هماهنگ کند.
        self.lang = lang if lang == "fa" or lang in _LANG_ORDER else "fa"

    @property
    def rtl(self):
        return self.lang in RTL_LANGS

    def _build_table(self):
        """جدول ترجمه‌ی زبان غیرفارسی را می‌سازد؛ کش در _table مدیریت می‌شود."""
        column = _LANG_ORDER.index(self.lang) + 1
        table = {}
        for number, line in enumerate(_RAW.strip().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip().replace("\\n", "\n") for p in line.split(" | ")]
            if len(parts) != 9:
                AppLogger.warning(
                    f"I18n row {number} ignored: expected 9 columns, got {len(parts)}"
                )
                continue
            normalized_key = _norm_key(parts[0])
            if normalized_key in table:
                AppLogger.warning(
                    f"I18n row {number} ignored: duplicate key {parts[0]!r}"
                )
                continue
            table[normalized_key] = parts[column]
        return table

    def _table(self):
        # حتی جدول خالی فارسی هم یک بار ساخته و در کش نگهداری می‌شود.
        # آزمون دستی: دو بار _table() را برای fa و en فراخوانی کنید؛ شیء جدول هر زبان باید یکسان بماند.
        if self.lang not in self._tables:
            self._tables[self.lang] = {} if self.lang == "fa" else self._build_table()
        return self._tables[self.lang]

    def t(self, key, *args):
        # برای فارسی و سایر زبان‌ها فقط از جدول ترجمه استفاده می‌شود.
        text = self._table().get(_norm_key(key), key)
        if args:
            try:
                text = text.format(*args)
            except Exception as exc:
                AppLogger.warning(f"I18n format fallback for {key!r}: {exc}")
                # در خطای قالب‌بندی نیز همان مقدار جدول ترجمه یا کلید اصلی برگردانده می‌شود.
                text = self._table().get(_norm_key(key), key)
                try:
                    text = text.format(*args)
                except Exception as fallback_exc:
                    AppLogger.warning(f"I18n Persian fallback format failed: {fallback_exc}")
                    # مسیر جایگزین نهایی نیز بدون جایگزینی واژه‌ای عمل می‌کند.
                    text = self._table().get(_norm_key(key), key)
                    text = text.replace("{", "").replace("}", "")
        return text


i18n = I18n()
T = i18n.t


def _validate_raw_i18n():
    """Validate all raw translation rows and raise when malformed or duplicated."""
    seen = set()
    failures = []
    for number, line in enumerate(_RAW.strip().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(" | ")]
        if len(parts) != 9:
            failures.append(f"row {number}: expected 9 columns, got {len(parts)}")
            continue
        key = _norm_key(parts[0])
        if not key:
            failures.append(f"row {number}: empty key")
        elif any(not part for part in parts[1:]):
            failures.append(f"row {number}: empty translation column")
        elif key in seen:
            failures.append(f"row {number}: duplicate key {parts[0]!r}")
        else:
            seen.add(key)
    if failures:
        details = "; ".join(failures)
        AppLogger.warning(f"_validate_raw_i18n failed: {details}")
        raise AssertionError(f"_validate_raw_i18n failed: {details}")


def month_name(month):
    return T(MONTHS[month - 1])


# ----------------------------------------------------------------------
#  لایه‌ی داده (SQLite)
# ----------------------------------------------------------------------
# دو حساب مستقل‌اند؛ هرکدام مبلغ و ریزمبالغ واحدی خود را دارند،
# اما الگوریتم محاسبه و انتقال بدهی/بستانکاری برای هر دو یکسان است.
ASSESS = {KIND_CHARGE: ("charge_per_unit", "unit_charges"),
          KIND_CONTRIB: ("payment_per_unit", "unit_payments")}
ZERO_FLOW = (0, 0, 0, 0, 0, 0)   # شارژ، پرداختی، هزینه‌های دو حساب، درآمدهای دو حساب


# نبودن default با None تفاوت دارد؛ None صریح باید به‌عنوان مقدار پیش‌فرض حفظ شود.
_UNSET = object()



__all__ = [name for name in globals() if not name.startswith('__')]
