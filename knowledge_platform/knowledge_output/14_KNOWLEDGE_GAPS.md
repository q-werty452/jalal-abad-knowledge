# Knowledge gaps

Каждый пункт нужен до публикации либо производственной маршрутизации.

## GAP-001 — Утверждённая матрица маршрутизации для пилота

- Зачем нужно / риск: Без неё предложения нельзя переводить в production rules.
- Запросить у: Мэрия и владельцы ведомств
- Желаемый формат: XLSX: тема, территория, первичный исполнитель, исключения, дата утверждения

## GAP-002 — Границы пилота и зоны обслуживания

- Зачем нужно / риск: Областные и городские учреждения смешаны.
- Запросить у: Мэрия
- Желаемый формат: Утверждённый перечень территорий и GeoJSON/GPKG

## GAP-003 — Актуальные публичные контакты и адреса

- Зачем нужно / риск: В документах смешаны служебные и личные номера; адреса местами расходятся.
- Запросить у: Мэрия и каждое ведомство
- Желаемый формат: Реестр контактов с public_contact и датой проверки

## GAP-004 — Утверждённые категории Django и соответствия тем

- Зачем нужно / риск: Кандидатные темы корпуса не равны действующим кодам.
- Запросить у: Владелец Django backend и мэрия
- Желаемый формат: Экспорт категорий, версий и маппинга

## GAP-005 — Актуальные официальные акты и сроки

- Зачем нужно / риск: Анкеты называют сроки без полного нормативного основания.
- Запросить у: Мэрия и юридические службы
- Желаемый формат: Реестр актов с номером, датой и действующей редакцией

## GAP-006 — Утверждённые названия RU/KY

- Зачем нужно / риск: Для большинства организаций подтверждён только один язык.
- Запросить у: Ведомства
- Желаемый формат: Двуязычный официальный реестр с aliases

## GAP-007 — Исключения и межведомственные случаи

- Зачем нужно / риск: Общая компетенция не определяет ответственного при пересечении функций.
- Запросить у: Мэрия и ведомства
- Желаемый формат: Таблица исключений и эскалаций

## GAP-008 — OCR/ручная проверка заблокированных файлов

- Зачем нужно / риск: Часть сканов и старых форматов не даёт проверяемого текста.
- Запросить у: Владельцы документов
- Желаемый формат: Поисковые PDF/DOCX или заверенная расшифровка

## GAP-009 — Публичность и права на публикацию

- Зачем нужно / риск: Даже сведения из предоставленной таблицы не помечены как разрешённые к публикации.
- Запросить у: Мэрия и ведомства
- Желаемый формат: Поле publication_status и письменное согласование

## GAP-010 — Тождественность похожих названий и RU/KY пар

- Зачем нужно / риск: Близкие названия электрических, архивных, дорожных и экологических структур встречаются в разных источниках; автоматическое объединение может создать ложную организацию.
- Запросить у: Мэрия и соответствующие ведомства
- Желаемый формат: Реестр стабильных ID, официальных названий RU/KY и подтверждённых aliases

## Proposed routing requiring approval

Следующие правила пока имеют `verification_status=proposed`: route-proposed-zhalal-abad-elektr-tarmaktary-ishkanasyelektrenergiyasy-menen-obl-7f6f40c, route-proposed-zhalalabatgaz-filialyzharatylysh-gazy-menen-kamsyzdoo-e2f96cd, route-proposed-zhalal-abadtagy-synoo-sertifikatsiyaloo-zhana-metrologiya-borboru-d850783, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-aksy-raionduk-finan-760ef08, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-toguz-toro-raionduk-097da7f, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-tash-komur-shaardyk-308db4d, route-proposed-aiyl-bankkalkty-bank-kyzmattary-menen-teiloo-f4b6d33, route-proposed-tash-komur-shaardyk-statistika-bolumustatistikalyk-maalymattardy-7632b4b, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-suzak-raionduk-fina-0624060, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-manas-shaardyk-fina-9b10742, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-kara-kol-shaardyk-f-cb1ed2b, route-proposed-zher-agenttiginin-aksy-filialymyizam-cheginde-zherge-tiesheluu-do-0a69d26, route-proposed-kyrgyz-respublikasynyn-transport-zhana-kommunikatsiyalar-ministrl-ac4a30c, route-proposed-kyrgyz-respublikasynyn-transport-zhana-kommunikatsiyalar-ministrl-f33f499, route-proposed-kyrgyz-respublikasynyn-suu-resurstary-aiyl-charba-zhana-kaira-ish-553902b, route-proposed-kyrgyz-respublikasynyn-finansy-ministrliginin-chatkal-raionduk-fi-745743a, route-proposed-chatkal-raionduk-agrardyk-onukturuu-bashkarmalygyagrardyk-choiron-07861e3, route-proposed-bazar-korgon-raionduk-suu-charba-bashkarmalygydyikandardy-sugat-s-4bb91fc, route-proposed-tyshky-ishter-ministrliginin-osh-zhalal-abad-zhana-batken-oblusta-ef2703c, route-proposed-kyrgyz-respublikasynyn-ministrler-kabinetine-karashtuu-zher-resur-91afd23, route-proposed-zhalal-abad-osumduktordu-khimiyalashtyruu-korgoo-zhana-karantin-b-3dd5f0f, route-proposed-suzak-raionduk-veterinariya-mal-charbasyn-onukturuu-zhaiyt-zhana-cad1fd6, route-proposed-naryn-syr-daryya-suu-resurstary-bassein-bashkarmalygynaryn-syr-da-b67789d, route-proposed-krsrachzhkiozhmne-karashtuu-aiyl-charba-osumduktorun-zhana-bagban-2bcf07a, route-proposed-krsrachzhkiozhmne-karashtuu-veterinardyk-zhana-fitosanitardyk-koz-2f8b4a8, route-proposed-aiyl-charbada-kooperatsiyaloo-mekhanizatsiyaloo-zhana-innovatsiya-f926492, route-proposed-bazar-korgon-raionduk-shaar-kuruu-zhana-arkhitektura-bashkarmalyg-12398c5, route-proposed-kr-ekonomika-zhana-kommertsiya-ministrliginin-aimaktar-aralyk-bas-e82def1.

## Blocked documents

Требуют OCR, конвертации или визуального извлечения: SRC-049, SRC-114, SRC-122, SRC-144, SRC-148, SRC-155, SRC-156, SRC-170, SRC-174, SRC-175, SRC-192, SRC-207.
