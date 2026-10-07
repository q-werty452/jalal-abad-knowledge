# Offline query coverage v4

Result: **PASS**; queries: **23**; exact scoped routes: **12**; missing or conflict: **11**. Wrong entity: **0**; wrong territory: **0**.

Lookup requires the exact territory scope; no rule is spread to the whole region. MISSING_OR_CONFLICT is a safe abstention, not a claimed answer. Routes remain advisory.

| Question | Territory | Result | Targets | Sources |
|---|---|---|---|---|
| Кто чинит дороги в Кетмен-Добо? | ayyl_area:Кетмен-Добо | FOUND | v4-org-a73365c80b613d, v4-org-c343cadb650d52 | NEW-258, NEW-259 |
| Кто чинит дороги в Айры-Там? | ayyl_area:Айры-Там | FOUND | v4-org-9ede4e8e944f1b | NEW-264 |
| Кто чинит дороги в Көк-Арт? | ayyl_area:Көк-Арт | MISSING_OR_CONFLICT |  |  |
| Не горит фонарь в Уч-Терек | ayyl_area:Уч-Терек | FOUND | v4-org-9e63798926fdf8 | NEW-258 |
| Нет уличного света в Ынтымак | ayyl_area:Ынтымак | FOUND | v4-org-448a6f45c6a41a | NEW-264 |
| Мусор в Токтогуле | city:Токтогул | FOUND | v4-org-0b81feb03a556c | NEW-258 |
| Таштанды Айры-Там | ayyl_area:Айры-Там | FOUND | v4-org-9ede4e8e944f1b | NEW-264 |
| Нет воды в Токтогуле | city:Токтогул | FOUND | v4-org-105350cacebbf1 | NEW-258 |
| Вода в Ала-Бука | ayyl_area:Ала-Бука | FOUND | v4-org-2489d07ee2396b | NEW-264 |
| Канализация в Токтогуле | city:Токтогул | FOUND | v4-org-105350cacebbf1 | NEW-258 |
| Открытый люк в Айры-Там | ayyl_area:Айры-Там | FOUND | v4-org-9ede4e8e944f1b | NEW-264 |
| Электричество в Сузаке | ayyl_area:Сузак | FOUND | v4-org-31ec489ba63031 | NEW-265 |
| Земельный вопрос в Уч-Терек | ayyl_area:Уч-Терек | FOUND | v4-org-9e63798926fdf8 | NEW-258 |
| Сломан светофор в Токтогуле | city:Токтогул | MISSING_OR_CONFLICT |  |  |
| Нет дорожного знака в Токтогуле | city:Токтогул | MISSING_OR_CONFLICT |  |  |
| Школа в Токтогуле | district:Токтогул | MISSING_OR_CONFLICT |  |  |
| Детский сад в Токтогуле | district:Токтогул | MISSING_OR_CONFLICT |  |  |
| Медицинская помощь в Кара-Көл | city:Кара-Көл | MISSING_OR_CONFLICT |  |  |
| Социальная поддержка в Токтогуле | district:Токтогул | MISSING_OR_CONFLICT |  |  |
| Жилье в Сузаке | district:Сузак | MISSING_OR_CONFLICT |  |  |
| Нарушение порядка в Токтогуле | district:Токтогул | MISSING_OR_CONFLICT |  |  |
| Бродячие животные в Ала-Бука | district:Ала-Бука | MISSING_OR_CONFLICT |  |  |
| Нет воды в Кара-Көл | city:Кара-Көл | MISSING_OR_CONFLICT |  |  |
