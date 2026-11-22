# Директивы АРАП (архив БЕМШ): синтаксис и роль

Дата: 22.11.2026. Статический анализ.
Ни один образ не изменялся.
Write set: только этот файл. Коммитов и push нет.

## 0. Что исправлено

АРАП - это НЕ только третий проход генерации слов.
Это АРХИВ БЕМШ со своим словарём управляющих карт.
Третий проход - лишь одна из ролей зоны 0152.

ФАКТ (тексты в зоне 0152, GOST-10859):
- 0152.0002 «ЗАПИСЬ АП НА АРХИВНУЮ ЛЕНТУ ЗАКОНЧИЛАСЬ»
- 0152.0151 «НЕТ УПРАВЛЯЮЩИХ КАРТ АРАПА»
- 0152.0157 «ОШИБКА СПРАВКИ»
- 0152.0223 «ТАКОЙ ОПЕРАЦИИ НЕТ»
- 0152.0241 «ИСПОРЧЕНА ПРОГРАММА В АРХИВЕ МЛ»
- 0152.0250 «НЕТ ИМЕНИ ДЛЯ ЗАПИСИ В АРХИВ»
  [docs/SEMANTIC/Z0152.md:16-23, :80-108, :186-207].
ФАКТ (зона 0151): «ОГЛАВЛЕНИЕ ТОМА», «ДАТА З П ОПЕРАЦ З П»,
«БЫЛИ ОШИБКИ В ЗАДАНИИ АРАП» [Z0151.md:25-30, :134-152].
ИНТЕРПРЕТАЦИЯ: АП = архив пакета/программ (ГИПОТЕЗА);
сам факт архивной плоскости - ФАКТ по текстам.

## 1. Методика

Искали во всех 4 репозиториях: re-bemsh, re-dispak, dispak,
simh/BESM6. Регистр не различается: в колодах Dispaka
карты пишутся строчными, в .be-проекте заглавными.

Условности:
- `↑` вместо `^`: в заданиях dispak разделитель печатается
  как `^`, в тексте проекта пишем `↑`
  [docs/RECONSTRUCTION-SETUP.md:36-38];
- 6 цифр в операнде = `NN` (лента) + `zzzz` (зона, восьм.);
  пример: 433100 = лента 43, зона 03100₈, а не номер зоны
  для besmtool [RECONSTRUCTION-SETUP.md:123-129];
- лента 42 - том 2099 только для чтения, лента 43 - тот же
  том «на ЗП» [RECONSTRUCTION-SETUP.md:32-34;
  dispak/dispak/make2099.b6:2-3].

## 2. Сводка: синтаксис и presumed action

Ниже `l` - число зон, `z` - зона, `NN` - лента.

```
ЗОНМОД   ЗОНМОДNNzzzz llll
  записать модуль; ФАКТ (с 1-1)
ЗОНГП    зонгп NNzzzz [l]
  зона группы П; ФАКТ синтаксис
БТМАЛФ   БТМАЛФ
  хвост записи; ФАКТ (с 1-1)
ЗПКОМП   ЗПКОМПNNzzzz
  запись «КОМП»; ГИПОТЕЗА
ЧТКОМП   ЧТКОМПNNzzzz
  чтение «КОМП»; ГИПОТЕЗА
БЛМАК    БЛМАК
  карта M-80; НЕ ИЗВЕСТНО
КВЧ$$$   КВЧ$$$     конец вычисл.; ФАКТ
ТРН$$$   ТРН$$$     конец трансл.; ФАКТ
КОНЕЦ    конец      конец карт; ГИПОТЕЗА
КНЦ$$$   КНЦ$$$     конец блок-карт; ФАКТ
ЕКОНЕЦ   _$ / ЕКОНЕЦ
  конец ввода; ФАКТ
МДЛ      мдл <имя>NNzzzz
  модуль + зона; ФАКТ
НАЗ      наз <адрес>
  вход модуля; ФАКТ
```

«WRITES/READS/END/SELECT» по ролям:
- пишет объект на диск/ленту: связка `1-1` + `БТМАЛФ` +
  `ЗОНМОДNNzzzz llll` (ФАКТ); вероятно также `ЗПКОМП`
  (ГИПОТЕЗА по имени и ленте 43 на ЗП);
- читает: `ЧТКОМПNNzzzz` (ГИПОТЕЗА по имени и ленте 42);
- конец архива/списка карт: `КОНЕЦ` в колоде АРАП
  (ГИПОТЕЗА), `ЕКОНЕЦ` конец ввода (ФАКТ);
- выбор зоны/библиотеки: `ЗОНМОД`, `ЗОНГП`, `МДЛ`,
  плюс `БЛМАК` как карта макробиблиотеки (ГИПОТЕЗА).

## 3. Доказательства по директивам

### 3.1 ЗОНМОД

ФАКТ синтаксис: `ЗОНМОД433900  0001` (два пробела перед
4-значным счётчиком). 146 колод с этой формой.
Примеры: dispak/dispak/sostav.b6:114,
re-dispak/ukachka.be.b6:619,
re-bemsh/tools/rebuild-zone.sh:117.
В комментарии anis6.b6:15 встречается `ЗОНМОД430012`
без счётчика.

ФАКТ действие: `poc3.py` с `make_job()` (`1-1` + `БТМАЛФ`)
печатает «МОДУЛЬ ТЕСТ ЗАПИСАН В ЗОНЫ С 433100 ПО 433100»,
`besmtool dump 2248 --start=03100 --length=1` даёт 6144 байт
с именем `ТЕСТ` в слове 1 [RECONSTRUCTION-SETUP.md:113-129,
:177-180]. То же зафиксировано в
analysis/OBJECT-MODULE-IDENTITY.md:11-12, :27-37.

ГИПОТЕЗА: 4-значное поле - длина в зонах.
re-dispak/modlist.src:2 прямо говорит:
«BEMSH does not seem to honor the length in ZONMOD».

НЕ ИЗВЕСТНО: точное соответствие `ЗОНМОД433900` ->
зона 03100₈ не выведено из текста транслятора
[RECONSTRUCTION-SETUP.md:127-129, :187-188].

### 3.2 ЗОНГП

ФАКТ: директива ИМЕЕТ операнд. Две формы:
1) `зонгп 430621     4` = зона + длина
   [re-dispak/rvs.src.b6:15-33, rvs.be:15-33;
   dispak/dispak/make2099.b6:17,21,24,27];
2) `зонгп 270000` = только зона
   [dispak/tests/bemsh-standalone/bemsh-standalone.b6:30,
   его же output.txt:9].
Итого 113 вхождений, из них 100 в re-dispak.

ФАКТ роль в архиве: наличие `зонгп` в строке `мдл`
включает модуль в верификацию `verify.pl`;
без `зонгп` модуль не проверяется
[re-dispak/AGENTS.md:736-745;
re-bemsh/docs/ADJACENT.md:71-74].
`verify.pl` читает пары (зона, длина, имя) из rvs.src.

ФАКТ (подтверждение оператора 22.11.2026):
ЗОНГП = «зоны готовых программ»; прежняя гипотеза
«группа программ» отклонена. НЕ ИЗВЕСТНО точное раскрытие ПФ:
Z0144.md:366-367 называет ЗОНГП сокращением паспорта/ОС
без исходника.

### 3.3 БТМАЛФ

ФАКТ: без операнда, 178 вхождений, всегда в хвосте колоды.
Стоит после `0-0`/`1-1` (и после `БЛМАК` в Монитор-80),
перед `КНЦ$$$`. Примеры:
dispak/dispak/sostav.b6:113,
dispak/tests/bemsh-ms/bemsh.b6:24,
re-bemsh/tools/rebuild-0137.sh:48.
В macros.b6:243 на его месте стоит `ЗПКОМП430070`.

ФАКТ: в связке с `1-1` даёт запись (см. 3.1).
ГИПОТЕЗА: обязательный «алфавитный» хвост задания,
разрешающий запись; НЕ ИЗВЕСТНО раскрытие аббревиатуры.
re-dispak/prn.sh:4 удаляет `БТМАЛФ` при переходе
`1-1` -> `0-0`, то есть карта связана именно с записью.

### 3.4 ЧТКОМП / ЗПКОМП

ФАКТ: `ЧТКОМП420070` (150 вхождений) стоит перед режимом
`0-0`/`1-1` почти в каждом задании МАКРО-БЕМШ.
`ЗПКОМП430070` - одно вхождение, macros.b6:243.

ГИПОТЕЗА: ЧТ = чтение с ленты 42 зоны 0070,
ЗП = запись на ленту 43 зоны 0070; «КОМП» - область
компиляции/состояние компилятора. Ленты 42/43 -
один том 2099 в режимах чтение/запись.
НЕ ИЗВЕСТНО, что именно лежит в зоне 0070.
Связь с текстом «В КОМПИЛЯЦИЮ» (0170.0376) -
только гипотеза [TEXT-CONSTANTS-ALL.md:377].

### 3.5 БЛМАК

ФАКТ: без операнда, 6 вхождений:
bemsh.b6:23, bemsh-standalone.b6:30, output-файлы
этих тестов, re-dispak/testdks/vnimanije.be:120,
re-dispak/AGENTS.md:340, archive/ara.md:660.
Стоит после `0-0`, перед `БТМАЛФ`.

ГИПОТЕЗА: карта выбора макробиблиотеки/макро-трассировки
в диалекте Монитор-80. Вне этого диалекта отсутствует,
что ожидаемо и не признак другой версии
[docs/ADJACENT-2.md:68-71].
НЕ ИЗВЕСТНО раскрытие аббревиатуры.

### 3.6 КВЧ / ТРН / КНЦ / ЕКОНЕЦ

ФАКТ по встроенным комментариям re-dispak/AGENTS.md:337-342:
- `КВЧ$$$` ; конец вычислений (задачи)
- `ТРН$$$` ; конец трансляции
- `КНЦ$$$` ; конец диспетчерского блока
- `ЕКОНЕЦ` ; финальная карта ввода
`ТРН$$$` подставляется всегда, даже при диалоговом
наборе [re-dispak/inserp.be:1241-1247].

### 3.7 МДЛ / НАЗ

ФАКТ: `мдл <имя>NNzzzz` задаёт имя модуля и зону на
ленте; `наз <6 цифр>` задаёт entry/адрес.
Примеры: make2099.b6:15-27, rvs.src.b6:15-33.
re-dispak/rvs.pl заменяет директивы МДЛ на реальные
адреса из modloc.txt [re-dispak/AGENTS.md:66-69].
`КОНЕЦ` (make2099.b6:28) завершает список карт АРАП.

## 4. «НАЗ КОНЕЦ ЗОНГП ПФГП00» (зона 0144.1765-1775)

Это НЕ одна команда, а хвост цепочки GOST-слов
в пуле диагностики ядра. Побайтово (6 знаков/слово,
7-битный GOST-10859, один знак на байт):

```
1765  ЗАМ000
1766  ЗАМ
1767  МДЛ
1770  ПЕЧМДЛ
1771  ПЕЧФП
1772  НАЗ
1773  КОНЕЦ
1774  ЗОНГП
1775  ПФГП00
```

Источники: docs/SEMANTIC/Z0144.md:244-258, :58,
docs/SEMANTIC/P-TEXT-B1.md:79-87,
docs/TEXT-CONSTANTS-ALL.md:357.
Полная фраза в Z0144.md:244-245:
«ЗАМ...МДЛ ПЕЧ...ФП НАЗ КОНЕЦ ЗОНГП ПФГП00».

ФАКТ: байты и прочтение однозначны; зоны 0144 и 0544
байтово идентичны [Z0544.md:14-19].
ФАКТ: в Z0544.md:113 дана интерпретация:
«список имен/ops таблицы (замена, печать, конец...)».
ФАКТ: в реальных колодах встречаются 4 из 9 этих слов
как карты: МДЛ, НАЗ, ЗОНГП, КОНЕЦ
(make2099.b6:15-28; rvs.src.b6:15-33).
Ещё один список тех же карт в GOST-листинге:
re-dispak/archive/malichev_2048.md:721-727
(КОНЕЦ, МДЛ, НАЗ, ЗОНГП 0000).

ГИПОТЕЗА: это таблица ключевых слов управляющих карт
АРАП, использоваемая при разборе задания и при
диагностике «НЕТ УПРАВЛЯЮЩИХ КАРТ АРАПА» /
«ТАКОЙ ОПЕРАЦИИ НЕТ» (0152.0151, 0152.0223).
Об этом же: Z0144.md:246 «финальные маркеры зон/печати»,
SERVICE-TABLES-B-OTHER.md:135 «message text (GOST)».

НЕ ИЗВЕСТНО:
- точный смысл «ПФГП00» и «ЗОНГП» как сокращений
  [Z0144.md:366-367];
- природа списка: меню команд или служебная таблица
  сообщений [P-TEXT-B1.md:188-193];
- значения «ЗАМ», «ПЕЧМДЛ», «ПЕЧФП» как карт
  (в наших колодах не найдены).

Вывод: фраза показывает, что словарь управляющих карт
АРАП существует и на машинном уровне, в 7-битном
GOST-тексте ядра, а не только в синтаксисе колод.
Кодировка: 0x20...0x3e = А...Я, 0x00...0x09 = 0...9,
0x0a...0x0f = знаки и пробел
[MACRO-BEMSH-ARCHITECTURE.md:543-544].

## 5. Почему 0-0 не пишет, а 1-1 пишет

ФАКТ: режим 0-0 не изменил ни одного байта томов
2048/2053/2099/2248
[MACRO-TABLE-FORMAT-VERIFIED.md:159-161;
MACRO-BEMSH-ARCHITECTURE.md §7.4:794-799].
Там же сказано: «Попытки 1-1 / БТМАЛФ / ЗОНГП не привели
к записи», сообщение «ЗАПИСАН В ЗОНЫ» не печатается.

ФАКТ: позже `poc3.py` (make_job, `1-1` + `БТМАЛФ`)
успешно записал модуль [RECONSTRUCTION-SETUP.md:113-129,
:177-180]. Обязателен ещё и правильный порядок томов
в BESM6_PATH и лента 43 «на ЗП»
[RECONSTRUCTION-SETUP.md:32-34].

ГИПОТЕЗА: в неудачных опытах решающим был режим 0-0
(карты-заглушки печатаются, но запись не выполняется),
либо отсутствие полного набора карт/ленты на запись.
Точные строки тех неудачных колод в документах не
приведены, поэтому выбрать между «режим» и «набор карт»
по имеющимся данным нельзя. Это честный blocker.

## 6. Приложение: все вхождения (путь:строка)

Пути даны относительно /home/azizz/Yandex.Disk/.
Список собран `grep -rniI` по *.b6, *.be, *.txt, *.mcr,
*.bemsh в 4 репозиториях. Строчные и заглавные формы
объединены. `^` в колодах заменён на `↑` только в
иллюстрациях выше; здесь приведены исходные строки.

### БТМАЛФ  (178 вхождений)
```
dispak/dispak/disp99.b6:1614:БТМАЛФ
dispak/dispak/e64.b6:1440:БТМАЛФ
dispak/dispak/ekdisp.b6:256:БТМАЛФ
dispak/dispak/macros.b6:244:БТМАЛФ
dispak/dispak/sostav.b6:113:БТМАЛФ
dispak/dispak/spe66.b6:315:БТМАЛФ
dispak/tests/bemsh-ms/bemsh.b6:24:бтмалф
dispak/tests/bemsh-ms/output.txt:38:      БТМАЛФ
dispak/tests/bemsh-standalone/bemsh-standalone.b6:31:бтмалф^
dispak/tests/bemsh-standalone/output.txt:8:БТМАЛФ
dispak/tests/pprog01/output.txt:7:БТМАЛФ
dispak/tests/pprog01/pprog01.b6:50:бтмалф^
dispak/tests/pprog02/output.txt:7:БТМАЛФ
dispak/tests/pprog02/pprog02.b6:59:бтмалф^
dispak/tests/pprog03/output.txt:7:БТМАЛФ
dispak/tests/pprog03/pprog03.b6:58:бтмалф^
dispak/tests/pprog04/output.txt:7:БТМАЛФ
dispak/tests/pprog04/pprog04.b6:63:бтмалф^
dispak/tests/pprog05/output.txt:7:БТМАЛФ
dispak/tests/pprog05/pprog05.b6:61:бтмалф^
dispak/tests/pprog06-md/output.txt:7:БТМАЛФ
dispak/tests/pprog06-md/pprog06-md.b6:54:бтмалф^
dispak/tests/pprog06/output.txt:7:БТМАЛФ
dispak/tests/pprog06/pprog06.b6:65:бтмалф^
dispak/tests/pprog07/output.txt:7:БТМАЛФ
dispak/tests/pprog07/pprog07.b6:57:бтмалф^
dispak/tests/pprog08/output.txt:7:БТМАЛФ
dispak/tests/pprog08/pprog08.b6:42:бтмалф^
dispak/tests/pprog09/output.txt:7:БТМАЛФ
dispak/tests/pprog09/pprog09.b6:49:бтмалф^
dispak/tests/pprog10/output.txt:7:БТМАЛФ
dispak/tests/pprog10/pprog10.b6:56:бтмалф^
re-dispak/apunkt.be.b6:350:БТМАЛФ^
re-dispak/arfa.be.b6:3654:БТМАЛФ^
re-dispak/arkhin.be.b6:1870:БТМАЛФ^
re-dispak/avmd.be.b6:2167:БТМАЛФ^
re-dispak/avml.be.b6:1140:БТМАЛФ^
re-dispak/avrasp.be.b6:1610:БТМАЛФ^
re-dispak/bac.be.b6:1926:БТМАЛФ^
re-dispak/backup/vnimanije.be:121:бтмалф
re-dispak/benson.be.b6:392:БТМАЛФ^
re-dispak/boek1.be.b6:3982:БТМАЛФ^
re-dispak/bonbot.be.b6:2089:БТМАЛФ^
re-dispak/bop.be.b6:490:БТМАЛФ^
re-dispak/bop1.be.b6:566:БТМАЛФ^
re-dispak/bop2.be.b6:284:БТМАЛФ^
re-dispak/cirkul.be.b6:674:БТМАЛФ^
re-dispak/clock.be.b6:275:БТМАЛФ^
re-dispak/consul.be.b6:439:БТМАЛФ^
re-dispak/diski.be.b6:2552:БТМАЛФ^
re-dispak/disp70.be.b6:3362:БТМАЛФ^
re-dispak/dmlmb.be.b6:2909:БТМАЛФ^
re-dispak/dnepr.be.b6:1945:БТМАЛФ^
re-dispak/dudka.be.b6:371:БТМАЛФ^
re-dispak/e60.be.b6:468:БТМАЛФ^
re-dispak/e60d.be.b6:216:БТМАЛФ^
re-dispak/e64.be.b6:1537:БТМАЛФ^
re-dispak/e71tk.be.b6:734:БТМАЛФ^
re-dispak/ek2.be.b6:576:БТМАЛФ^
re-dispak/ek3.be.b6:566:БТМАЛФ^
re-dispak/ek4.be.b6:485:БТМАЛФ^
re-dispak/ek5.be.b6:560:БТМАЛФ^
re-dispak/ek6.be.b6:549:БТМАЛФ^
re-dispak/ek7.be.b6:350:БТМАЛФ^
re-dispak/ekgdr.be.b6:1922:БТМАЛФ^
re-dispak/eko.be.b6:391:БТМАЛФ^
re-dispak/ekst.be.b6:500:БТМАЛФ^
re-dispak/ekvvod.bak.b6:2179:БТМАЛФ^
re-dispak/ekvvod.be.b6:1921:БТМАЛФ^
re-dispak/esml.be.b6:2327:БТМАЛФ^
re-dispak/espi80.be.b6:439:БТМАЛФ^
re-dispak/espl.be.b6:345:БТМАЛФ^
re-dispak/esuvvk.be.b6:140:БТМАЛФ^
re-dispak/gen.be.b6:2322:БТМАЛФ^
re-dispak/gens.be.b6:2372:БТМАЛФ^
re-dispak/gens1.be.b6:2169:БТМАЛФ^
re-dispak/gens2.be.b6:1138:БТМАЛФ^
re-dispak/gidra.be.b6:1654:БТМАЛФ^
re-dispak/gnus.be.b6:307:БТМАЛФ^
re-dispak/gp1.be.b6:584:БТМАЛФ^
re-dispak/gp2.be.b6:132:БТМАЛФ^
re-dispak/gp3.be.b6:189:БТМАЛФ^
re-dispak/gp4.be.b6:598:БТМАЛФ^
re-dispak/gruppa.be.b6:332:БТМАЛФ^
re-dispak/io.be.b6:294:БТМАЛФ^
re-dispak/janus.be.b6:1727:БТМАЛФ^
re-dispak/kachka.be.b6:89:БТМАЛФ^
re-dispak/kanal.be.b6:2637:БТМАЛФ^
re-dispak/kch.be.b6:206:БТМАЛФ^
re-dispak/khlam.be.b6:2750:БТМАЛФ^
re-dispak/khlam.be.bak.20260905_171321.b6:2084:БТМАЛФ^
re-dispak/kit.be.b6:194:БТМАЛФ^
re-dispak/komar.be.b6:1112:БТМАЛФ^
re-dispak/konfus.be.b6:1109:БТМАЛФ^
re-dispak/konvoy.be.b6:490:БТМАЛФ^
re-dispak/kz.be.b6:608:БТМАЛФ^
re-dispak/kz1.be.b6:1964:БТМАЛФ^
re-dispak/mott.be.b6:2893:БТМАЛФ^
re-dispak/nakopl.be.b6:1326:БТМАЛФ^
re-dispak/nakzad.be.b6:1619:БТМАЛФ^
re-dispak/nereza.be.b6:1752:БТМАЛФ^
re-dispak/nerot.be.b6:494:БТМАЛФ^
re-dispak/nombob.be.b6:1629:БТМАЛФ^
re-dispak/nrkod.be.b6:1226:БТМАЛФ^
re-dispak/nrot.be.b6:352:БТМАЛФ^
re-dispak/obraz.be.b6:1773:БТМАЛФ^
re-dispak/osa.be.b6:3177:БТМАЛФ^
re-dispak/osaner.be.b6:941:БТМАЛФ^
re-dispak/ovd.be.b6:1794:БТМАЛФ^
re-dispak/pchkz.be.b6:1456:БТМАЛФ^
re-dispak/pechat.be.b6:1507:БТМАЛФ^
re-dispak/perekh.be.b6:1854:БТМАЛФ^
re-dispak/pgs.be.b6:1641:БТМАЛФ^
re-dispak/pibesm.be.b6:443:БТМАЛФ^
re-dispak/plan.be.b6:500:БТМАЛФ^
re-dispak/plan2.be.b6:1189:БТМАЛФ^
re-dispak/plbesm.be.b6:355:БТМАЛФ^
re-dispak/prik1.be.b6:586:БТМАЛФ^
re-dispak/prik2.be.b6:529:БТМАЛФ^
re-dispak/prik3.be.b6:379:БТМАЛФ^
re-dispak/prik4.be.b6:693:БТМАЛФ^
re-dispak/prik5.be.b6:617:БТМАЛФ^
re-dispak/prik6.be.b6:608:БТМАЛФ^
re-dispak/prik7.be.b6:548:БТМАЛФ^
re-dispak/prik8.be.b6:183:БТМАЛФ^
re-dispak/prikaz.be.b6:1708:БТМАЛФ^
re-dispak/priskv.be.b6:609:БТМАЛФ^
re-dispak/proces.be.b6:2691:БТМАЛФ^
re-dispak/prorok.be.b6:755:БТМАЛФ^
re-dispak/puskach.be.b6:767:БТМАЛФ^
re-dispak/ra.be.b6:2424:БТМАЛФ^
re-dispak/resurs.be.b6:2368:БТМАЛФ^
re-dispak/rezarkh.be.b6:668:БТМАЛФ^
re-dispak/robot.be.b6:1750:БТМАЛФ^
re-dispak/rpipl.be.b6:393:БТМАЛФ^
re-dispak/sbor80.be.b6:1187:БТМАЛФ^
re-dispak/serp.be.b6:4354:БТМАЛФ^
re-dispak/serp2.be.b6:2192:БТМАЛФ^
re-dispak/serp3.be.b6:1809:БТМАЛФ^
re-dispak/serp4.be.b6:2851:БТМАЛФ^
re-dispak/serp5.be.b6:1258:БТМАЛФ^
re-dispak/siprog.be.b6:1564:БТМАЛФ^
re-dispak/skor1.be.b6:737:БТМАЛФ^
re-dispak/skor2.be.b6:814:БТМАЛФ^
re-dispak/slojka.be.b6:1973:БТМАЛФ^
re-dispak/sme.be.b6:668:БТМАЛФ^
re-dispak/smena1.be.b6:687:БТМАЛФ^
re-dispak/smena2.be.b6:322:БТМАЛФ^
re-dispak/smena3.be.b6:618:БТМАЛФ^
re-dispak/sostav.be.b6:118:БТМАЛФ^
re-dispak/spe66.be.b6:511:БТМАЛФ^
re-dispak/spoe67.be.b6:241:БТМАЛФ^
re-dispak/stat1s.be.b6:514:БТМАЛФ^
re-dispak/stat2s.be.b6:461:БТМАЛФ^
re-dispak/svyaz.be.b6:529:БТМАЛФ^
re-dispak/svyaz7.be.b6:1792:БТМАЛФ^
re-dispak/term.be.b6:772:БТМАЛФ^
re-dispak/termas.be.b6:1801:БТМАЛФ^
re-dispak/testdks/test_sis_k71.be.b6:532:БТМАЛФ^
re-dispak/testdks/vnimanije.be:121:бтмалф
re-dispak/testdks/vnimanije.txt:1012:бтмалф^
re-dispak/testdks/vnimanije_rez.txt:37:      БТМАЛФ‾
re-dispak/trakh.be.b6:1040:БТМАЛФ^
re-dispak/trubka.be.b6:858:БТМАЛФ^
re-dispak/tupr.be.b6:149:БТМАЛФ^
re-dispak/uchet.be.b6:241:БТМАЛФ^
re-dispak/ukachka.be.b6:619:БТМАЛФ^
re-dispak/ukachka.be.bak.b6:559:БТМАЛФ^
re-dispak/upryach.be.b6:491:БТМАЛФ^
re-dispak/v1k.be.b6:1213:БТМАЛФ^
re-dispak/v3v4.be.b6:2064:БТМАЛФ^
re-dispak/v6v7.be.b6:2072:БТМАЛФ^
re-dispak/vektor.be.b6:259:БТМАЛФ^
re-dispak/visp.be.b6:429:БТМАЛФ^
re-dispak/vydach1.be.b6:2595:БТМАЛФ^
re-dispak/vydins.be.b6:3004:БТМАЛФ^
re-dispak/vyzovd.be.b6:683:БТМАЛФ^
re-dispak/vzu.be.b6:2709:БТМАЛФ^
```

### ЗОНМОД  (148 вхождений)
```
dispak/dispak/disp99.b6:1615:ЗОНМОД430142  0004
dispak/dispak/e64.b6:1441:ЗОНМОД430140  0002
dispak/dispak/ekdisp.b6:257:ЗОНМОД430147  0001
dispak/dispak/sostav.b6:114:ЗОНМОД430146  0001
dispak/dispak/spe66.b6:316:ЗОНМОД430150  0001
re-dispak/apunkt.be.b6:351:ЗОНМОД430011  0001^
re-dispak/arfa.be.b6:3655:ЗОНМОД430012  0005^
re-dispak/arkhin.be.b6:1871:ЗОНМОД430017  0003^
re-dispak/avmd.be.b6:2168:ЗОНМОД430003  0002^
re-dispak/avml.be.b6:1141:ЗОНМОД430005  0002^
re-dispak/avrasp.be.b6:1611:ЗОНМОД430007  0002^
re-dispak/bac.be.b6:1927:ЗОНМОД430022  0002^
re-dispak/benson.be.b6:393:ЗОНМОД430024  0001^
re-dispak/boek1.be.b6:3983:ЗОНМОД430032  0004^
re-dispak/bonbot.be.b6:2090:ЗОНМОД430025  0002^
re-dispak/bop.be.b6:491:ЗОНМОД430027  0001^
re-dispak/bop1.be.b6:567:ЗОНМОД430030  0001^
re-dispak/bop2.be.b6:285:ЗОНМОД430031  0001^
re-dispak/cirkul.be.b6:675:ЗОНМОД430325  0001^
re-dispak/clock.be.b6:276:ЗОНМОД430326  0001^
re-dispak/consul.be.b6:440:ЗОНМОД430000  0001^
re-dispak/diski.be.b6:2553:ЗОНМОД430104  0003^
re-dispak/disp70.be.b6:3363:ЗОНМОД430107  0005^
re-dispak/dmlmb.be.b6:2910:ЗОНМОД430114  0003^
re-dispak/dnepr.be.b6:1946:ЗОНМОД430117  0002^
re-dispak/dudka.be.b6:372:ЗОНМОД430002  0001^
re-dispak/e60.be.b6:469:ЗОНМОД430327  0001^
re-dispak/e60d.be.b6:217:ЗОНМОД430330  0001^
re-dispak/e64.be.b6:1538:ЗОНМОД430331  0002^
re-dispak/e71tk.be.b6:735:ЗОНМОД430333  0001^
re-dispak/ek2.be.b6:577:ЗОНМОД430334  0001^
re-dispak/ek3.be.b6:567:ЗОНМОД430335  0001^
re-dispak/ek4.be.b6:486:ЗОНМОД430336  0001^
re-dispak/ek5.be.b6:561:ЗОНМОД430337  0001^
re-dispak/ek6.be.b6:550:ЗОНМОД430340  0001^
re-dispak/ek7.be.b6:351:ЗОНМОД430341  0001^
re-dispak/ekgdr.be.b6:1923:ЗОНМОД430344  0002^
re-dispak/eko.be.b6:392:ЗОНМОД430346  0001^
re-dispak/ekst.be.b6:501:ЗОНМОД430347  0001^
re-dispak/ekvvod.bak.b6:2180:ЗОНМОД430342  0002^
re-dispak/ekvvod.be.b6:1922:ЗОНМОД430342  0002^
re-dispak/esml.be.b6:2328:ЗОНМОД430121  0003^
re-dispak/espi80.be.b6:440:ЗОНМОД430124  0001^
re-dispak/espl.be.b6:346:ЗОНМОД430125  0001^
re-dispak/esuvvk.be.b6:141:ЗОНМОД430126  0001^
re-dispak/gen.be.b6:2323:ЗОНМОД430062  0003^
re-dispak/gens.be.b6:2373:ЗОНМОД430065  0002^
re-dispak/gens1.be.b6:2170:ЗОНМОД430067  0003^
re-dispak/gens2.be.b6:1139:ЗОНМОД430072  0001^
re-dispak/gidra.be.b6:1655:ЗОНМОД430073  0003^
re-dispak/gnus.be.b6:308:ЗОНМОД430076  0001^
re-dispak/gp1.be.b6:585:ЗОНМОД430077  0001^
re-dispak/gp2.be.b6:133:ЗОНМОД430100  0001^
re-dispak/gp3.be.b6:190:ЗОНМОД430101  0001^
re-dispak/gp4.be.b6:599:ЗОНМОД430102  0001^
re-dispak/gruppa.be.b6:333:ЗОНМОД430103  0001^
re-dispak/inserp.be:1245:*    ТОМ НА ЗП. (НАПРИМЕР РЕЖИМ
    "ЗОНМОД"), НАДО НАБИРАТЬ
re-dispak/io.be.b6:295:ЗОНМОД430001  0001^
re-dispak/janus.be.b6:1728:ЗОНМОД430350  0002^
re-dispak/kachka.be.b6:90:ЗОНМОД430132  0001^
re-dispak/kanal.be.b6:2638:ЗОНМОД430127  0003^
re-dispak/kch.be.b6:207:ЗОНМОД430145  0001^
re-dispak/khlam.be.b6:2751:ЗОНМОД430322  0003^
re-dispak/khlam.be.bak.20260905_171321.b6:2085:ЗОНМОД430322
    0003^
re-dispak/kit.be.b6:195:ЗОНМОД430136  0001^
re-dispak/komar.be.b6:1113:ЗОНМОД430140  0002^
re-dispak/konfus.be.b6:1110:ЗОНМОД430143  0002^
re-dispak/konvoy.be.b6:491:ЗОНМОД430142  0001^
re-dispak/kz.be.b6:609:ЗОНМОД430133  0001^
re-dispak/kz1.be.b6:1965:ЗОНМОД430134  0002^
re-dispak/mott.be.b6:2894:ЗОНМОД430150  0003^
re-dispak/nakopl.be.b6:1327:ЗОНМОД430155  0002^
re-dispak/nakzad.be.b6:1620:ЗОНМОД430153  0002^
re-dispak/nereza.be.b6:1753:ЗОНМОД430157  0003^
re-dispak/nerot.be.b6:495:ЗОНМОД430162  0001^
re-dispak/nombob.be.b6:1630:ЗОНМОД430163  0002^
re-dispak/nrkod.be.b6:1227:ЗОНМОД430165  0001^
re-dispak/nrot.be.b6:353:ЗОНМОД430166  0001^
re-dispak/obraz.be.b6:1774:ЗОНМОД430167  0003^
re-dispak/osa.be.b6:3178:ЗОНМОД430174  0003^
re-dispak/osaner.be.b6:942:ЗОНМОД430177  0001^
re-dispak/ovd.be.b6:1795:ЗОНМОД430172  0002^
re-dispak/pchkz.be.b6:1457:ЗОНМОД430232  0002^
re-dispak/pechat.be.b6:1508:ЗОНМОД430204  0002^
re-dispak/perekh.be.b6:1855:ЗОНМОД430202  0002^
re-dispak/pgs.be.b6:1642:ЗОНМОД430200  0002^
re-dispak/pibesm.be.b6:444:ЗОНМОД430206  0001^
re-dispak/plan.be.b6:501:ЗОНМОД430207  0001^
re-dispak/plan2.be.b6:1190:ЗОНМОД430210  0002^
re-dispak/plbesm.be.b6:356:ЗОНМОД430212  0001^
re-dispak/prik1.be.b6:587:ЗОНМОД430213  0001^
re-dispak/prik2.be.b6:530:ЗОНМОД430214  0001^
re-dispak/prik3.be.b6:380:ЗОНМОД430215  0001^
re-dispak/prik4.be.b6:694:ЗОНМОД430216  0001^
re-dispak/prik5.be.b6:618:ЗОНМОД430217  0001^
re-dispak/prik6.be.b6:609:ЗОНМОД430220  0001^
re-dispak/prik7.be.b6:549:ЗОНМОД430221  0001^
re-dispak/prik8.be.b6:184:ЗОНМОД430222  0001^
re-dispak/prikaz.be.b6:1709:ЗОНМОД430223  0002^
re-dispak/priskv.be.b6:610:ЗОНМОД430225  0001^
re-dispak/proces.be.b6:2692:ЗОНМОД430227  0002^
re-dispak/prorok.be.b6:756:ЗОНМОД430226  0001^
re-dispak/puskach.be.b6:768:ЗОНМОД430231  0001^
re-dispak/ra.be.b6:2425:ЗОНМОД430234  0004^
re-dispak/resurs.be.b6:2369:ЗОНМОД430241  0002^
re-dispak/rezarkh.be.b6:669:ЗОНМОД430240  0001^
re-dispak/robot.be.b6:1751:ЗОНМОД430243  0002^
re-dispak/rpipl.be.b6:394:ЗОНМОД430245  0001^
re-dispak/sbor80.be.b6:1188:ЗОНМОД430246  0002^
re-dispak/serp.be.b6:4355:ЗОНМОД430253  0004^
re-dispak/serp2.be.b6:2193:ЗОНМОД430257  0003^
re-dispak/serp3.be.b6:1810:ЗОНМОД430262  0003^
re-dispak/serp4.be.b6:2852:ЗОНМОД430265  0002^
re-dispak/serp5.be.b6:1259:ЗОНМОД430267  0002^
re-dispak/siprog.be.b6:1565:ЗОНМОД430271  0002^
re-dispak/skor1.be.b6:738:ЗОНМОД430273  0001^
re-dispak/skor2.be.b6:815:ЗОНМОД430274  0001^
re-dispak/slojka.be.b6:1974:ЗОНМОД430275  0002^
re-dispak/sme.be.b6:669:ЗОНМОД430277  0001^
re-dispak/smena1.be.b6:688:ЗОНМОД430300  0001^
re-dispak/smena2.be.b6:323:ЗОНМОД430301  0001^
re-dispak/smena3.be.b6:619:ЗОНМОД430302  0001^
re-dispak/sostav.be.b6:119:ЗОНМОД430303  0001^
re-dispak/spe66.be.b6:512:ЗОНМОД430305  0001^
re-dispak/spoe67.be.b6:242:ЗОНМОД430304  0001^
re-dispak/stat1s.be.b6:515:ЗОНМОД430306  0001^
re-dispak/stat2s.be.b6:462:ЗОНМОД430307  0001^
re-dispak/svyaz.be.b6:530:ЗОНМОД430250  0001^
re-dispak/svyaz7.be.b6:1793:ЗОНМОД430251  0002^
re-dispak/term.be.b6:773:ЗОНМОД430311  0001^
re-dispak/termas.be.b6:1802:ЗОНМОД430312  0001^
re-dispak/testdks/anis6.b6:15:         *       ЗОНМОД430012
re-dispak/trakh.be.b6:1041:ЗОНМОД430313  0002^
re-dispak/trubka.be.b6:859:ЗОНМОД430315  0001^
re-dispak/tupr.be.b6:150:ЗОНМОД430316  0001^
re-dispak/uchet.be.b6:242:ЗОНМОД430321  0001^
re-dispak/ukachka.be.b6:620:ЗОНМОД430317  0001^
re-dispak/ukachka.be.bak.b6:560:ЗОНМОД430317  0001^
re-dispak/upryach.be.b6:492:ЗОНМОД430320  0001^
re-dispak/v1k.be.b6:1214:ЗОНМОД430036  0002^
re-dispak/v3v4.be.b6:2065:ЗОНМОД430040  0003^
re-dispak/v6v7.be.b6:2073:ЗОНМОД430043  0003^
re-dispak/vektor.be.b6:260:ЗОНМОД430046  0001^
re-dispak/visp.be.b6:430:ЗОНМОД430052  0001^
re-dispak/vydach1.be.b6:2596:ЗОНМОД430053  0003^
re-dispak/vydins.be.b6:3005:ЗОНМОД430056  0003^
re-dispak/vyzovd.be.b6:684:ЗОНМОД430061  0001^
re-dispak/vzu.be.b6:2710:ЗОНМОД430047  0003^
```

### ЗОНГП  (113 вхождений)
```
dispak/dispak/make2099.b6:17:зонгп 430100     3^
dispak/dispak/make2099.b6:21:зонгп 430103     1^
dispak/dispak/make2099.b6:24:зонгп 430104     1^
dispak/dispak/make2099.b6:27:зонгп 430105     1^
dispak/tests/bemsh-standalone/bemsh-standalone.b6:32:зонгп
    270000^
dispak/tests/bemsh-standalone/output.txt:38:ЗОНГП=270000
    СВ.ЗОНА = 270001  АМИН=01000 АМАКС=01011 АСВОБ=01012
dispak/tests/bemsh-standalone/output.txt:9:ЗОНГП 270000
re-bemsh/analysis/xref.txt:76798: 01774  конд     п'ЗОНГП '
    -    -        -
re-bemsh/analysis/xref.txt:76828: 01774  конд     п'ЗОНГП '
    -    -        -
re-bemsh/bemsh/MBE-Z0144.be:2213:        КОНД П'ЗОНГП='
    , Э62+Э62: авто-мода
re-bemsh/bemsh/MBE-Z0144.be:2616:        КОНД П'ЗОНГП '
    , Э62+Э62: авто-мода
re-bemsh/bemsh/MBE-Z0145.be:766:        КОНД П'ЗОНГП='
    , Э62+Э62: авто-мода
re-bemsh/bemsh/MBE2-Z0544.be:4032:        КОНД П'ЗОНГП '
    , EXP-бит: адрес >7777
re-dispak/rvs.be:15:мдл   дисп70430000^наз   000010^зонгп
    430621     4^
re-dispak/rvs.be:18:мдл   качка 430040^наз   072000^зонгп
    430625     2^
re-dispak/rvs.be:21:мдл   мотт  430030^наз   076000^зонгп
    430627     1^
re-dispak/rvs.be:22:мдл   гнус  430070^наз   020000^зонгп
    430736     1^
re-dispak/rvs.be:24:мдл   авмд  430110^наз   020000^зонгп
    430605     1^
re-dispak/rvs.be:25:мдл   прик6 430120^наз   021000^зонгп
    430534     1^
re-dispak/rvs.be:26:мдл   боэк1 430130^наз   015000^зонгп
    430475     2^
re-dispak/rvs.be:28:мдл   дмлмб 430150^наз   064000^зонгп
    430755     2^
re-dispak/rvs.be:30:мдл   есмл  430160^наз   062000^зонгп
    430671     1^
re-dispak/rvs.be:31:мдл   э71тк 430170^наз   011400^зонгп
    430572     1^
re-dispak/rvs.be:32:мдл   consul430174^наз   011000^зонгп
    430567     1^
re-dispak/rvs.be:33:мдл   бонбот430164^наз   030000^зонгп
    430422     1^
re-dispak/rvs.src.b6:100:мдл   овд   430172^наз
    010000^зонгп 430610     1^
re-dispak/rvs.src.b6:101:мдл   пгс   430200^наз
    010000^зонгп 430611     1^
re-dispak/rvs.src.b6:102:мдл   дисп70430107^наз
    000010^зонгп 430621     4^
re-dispak/rvs.src.b6:105:мдл   качка 430132^наз
    072000^зонгп 430625     2^
re-dispak/rvs.src.b6:110:мдл   мотт  430150^наз
    076000^зонгп 430627     1^
re-dispak/rvs.src.b6:111:мдл   кз1   430134^наз
    010000^зонгп 430670     1^
re-dispak/rvs.src.b6:112:мдл   есмл  430121^наз
    062000^зонгп 430671     1^
re-dispak/rvs.src.b6:113:мдл   янус  430350^наз
    050000^зонгп 430674     1^
re-dispak/rvs.src.b6:114:мдл   конфус430143^наз
    070000^зонгп 430676     1^
re-dispak/rvs.src.b6:115:мдл   связь7430251^наз
    040000^зонгп 430677     1^
re-dispak/rvs.src.b6:116:мдл   оса   430174^наз
    040000^зонгп 430706     2^
re-dispak/rvs.src.b6:117:мдл   связь 430250^наз
    010000^зонгп 430716     1^
re-dispak/rvs.src.b6:118:мдл   еспи80430124^наз
    011000^зонгп 430717     1^
re-dispak/rvs.src.b6:120:мдл   осанер430177^наз
    010000^зонгп 430720     1^
re-dispak/rvs.src.b6:121:мдл   авмл  430005^наз
    010000^зонгп 430725     1^
re-dispak/rvs.src.b6:122:мдл   гп1   430077^наз
    010000^зонгп 430730     1^
re-dispak/rvs.src.b6:124:мдл   гнус  430076^наз
    020000^зонгп 430736     1^
re-dispak/rvs.src.b6:126:мдл   учет  430321^наз
    010000^зонгп 430737     1^
re-dispak/rvs.src.b6:127:мдл   конвой430142^наз
    070000^зонгп 430744     1^
re-dispak/rvs.src.b6:128:мдл   выдинс430056^наз
    002000^зонгп 430752     2^
re-dispak/rvs.src.b6:129:мдл   канал 430127^наз
    020000^зонгп 430754     1^
re-dispak/rvs.src.b6:130:мдл   дмлмб 430114^наз
    064000^зонгп 430755     2^
re-dispak/rvs.src.b6:132:мдл   архин 430017^НАЗ
    076000^ЗОНГП 430501     1^
re-dispak/rvs.src.b6:133:мдл   трах  430313^НАЗ
    066000^ЗОНГП 430504    1^
re-dispak/rvs.src.b6:134:мдл   гидра 430073^НАЗ
    076000^ЗОНГП 430514     1^
re-dispak/rvs.src.b6:135:мдл   комар 430140^НАЗ
    000001^ЗОНГП 430523     2^
re-dispak/rvs.src.b6:136:мдл   арфа  430012^НАЗ
    070000^ЗОНГП 430721     3^
re-dispak/rvs.src.b6:138:мдл   образ 430167^НАЗ
    076000^ЗОНГП 430724     1^
re-dispak/rvs.src.b6:139:мдл   нереза430157^НАЗ
    076000^ЗОНГП 430757     1^
re-dispak/rvs.src.b6:140:мдл   сипрог430271^наз
    000001^зонгп 430454     2^
re-dispak/rvs.src.b6:142:мдл   ген   430062^НАЗ
    070000^ЗОНГП 430461     2^
re-dispak/rvs.src.b6:143:мдл   серп4 430265^НАЗ
    006000^ЗОНГП 430533     1^
re-dispak/rvs.src.b6:144:мдл   серп  430253^наз
    000001^зонгп 430731     4^
re-dispak/rvs.src.b6:146:мдл   серп5 430267^НАЗ
    006000^ЗОНГП 430405     1^
re-dispak/rvs.src.b6:147:мдл   серп3 430262^НАЗ
    006000^ЗОНГП 430735     1^
re-dispak/rvs.src.b6:148:мдл   бац   430022^наз
    006000^зонгп 430513     1^
re-dispak/rvs.src.b6:149:мдл   сбор80430246^наз
    000001^зонгп 431311     1^
re-dispak/rvs.src.b6:150:мдл   накзад430153^наз
    002000^зонгп 431312     2^
re-dispak/rvs.src.b6:151:мдл   накопл430155^наз
    002000^зонгп 431314     1^
re-dispak/rvs.src.b6:152:мдл   выдач1430053^наз
    002000^зонгп 431315     2^
re-dispak/rvs.src.b6:15:мдл   печать430204^наз
    010000^зонгп 430401     1^
re-dispak/rvs.src.b6:16:мдл   э64   430331^наз
    010000^зонгп 430407     1^
re-dispak/rvs.src.b6:17:мдл   робот 430243^наз
    010000^зонгп 430410     1^
re-dispak/rvs.src.b6:18:мдл   трубка430315^наз
    010000^зонгп 430413     1^
re-dispak/rvs.src.b6:19:мдл   термас430312^наз
    062000^зонгп 430414     1^
re-dispak/rvs.src.b6:20:мдл   процес430227^наз
    010000^зонгп 430415     1^
re-dispak/rvs.src.b6:21:мдл   пускач430231^наз
    010000^зонгп 430416     1^
re-dispak/rvs.src.b6:22:мдл   аврасп430007^наз
    010000^зонгп 430417     1^
re-dispak/rvs.src.b6:23:мдл   экввод430342^наз
    010000^зонгп 430420     1^
re-dispak/rvs.src.b6:24:мдл   ресурс430241^наз
    030000^зонгп 430421     1^
re-dispak/rvs.src.b6:25:мдл   бонбот430025^наз
    030000^зонгп 430422     1^
re-dispak/rvs.src.b6:26:мдл   в1к   430036^наз
    010000^зонгп 430423     1^
re-dispak/rvs.src.b6:27:мдл   номбоб430163^наз
    010000^зонгп 430426     1^
re-dispak/rvs.src.b6:28:мдл   приказ430223^наз
    010000^зонгп 430427     1^
re-dispak/rvs.src.b6:29:мдл   генс2 430072^наз
    060000^зонгп 430471     1^
re-dispak/rvs.src.b6:30:мдл   боэк1 430032^наз
    015000^зонгп 430475     2^
re-dispak/rvs.src.b6:32:мдл   вектор430046^наз
    010000^зонгп 430500     1^
re-dispak/rvs.src.b6:33:мдл   тупр  430316^наз
    024000^зонгп 430520     1^
re-dispak/rvs.src.b6:36:мдл   перех 430202^наз
    002000^зонгп 430525     1^
re-dispak/rvs.src.b6:37:мдл   вызовд430061^наз
    002000^зонгп 430526     1^
re-dispak/rvs.src.b6:38:мдл   циркул430325^наз
    020000^зонгп 430531     1^
re-dispak/rvs.src.b6:42:мдл   днепр 430117^наз
    010000^зонгп 430532     1^
re-dispak/rvs.src.b6:43:мдл   прик4 430216^наз
    020000^зонгп 430534     1^
re-dispak/rvs.src.b6:47:мдл   апункт430011^наз
    010000^зонгп 430535     1^
re-dispak/rvs.src.b6:48:мдл   генс  430065^наз
    070000^зонгп 430551     1^
re-dispak/rvs.src.b6:49:мдл   генс1 430067^наз
    060000^зонгп 430552     1^
re-dispak/rvs.src.b6:50:мдл   гп2   430100^наз
    010000^зонгп 430561     1^
re-dispak/rvs.src.b6:54:мдл   в3в4  430040^наз
    010000^зонгп 430562     1^
re-dispak/rvs.src.b6:55:мдл   эк5   430337^наз
    010400^зонгп 430563     1^
re-dispak/rvs.src.b6:57:мдл   план  430207^наз
    010400^зонгп 430564     1^
re-dispak/rvs.src.b6:58:мдл   э60д  430330^наз
    010000^зонгп 430565     1^
re-dispak/rvs.src.b6:62:мдл   нерот 430162^наз
    010000^зонгп 430566     1^
re-dispak/rvs.src.b6:65:мдл   эко   430346^наз
    010000^зонгп 430567     1^
re-dispak/rvs.src.b6:68:мдл   э60   430327^наз
    010000^зонгп 430570     1^
re-dispak/rvs.src.b6:71:мдл   упрячь430320^наз
    010400^зонгп 430571     1^
re-dispak/rvs.src.b6:74:мдл   боп   430027^наз
    011000^зонгп 430572     1^
re-dispak/rvs.src.b6:76:мдл   нрот  430166^наз
    010000^зонгп 430573     1^
re-dispak/rvs.src.b6:80:мдл   часы  430326^наз
    050000^зонгп 430574     1^
re-dispak/rvs.src.b6:81:мдл   слойка430275^наз
    010000^зонгп 430575     1^
re-dispak/rvs.src.b6:82:мдл   боп1  430030^наз
    010000^зонгп 430576     1^
re-dispak/rvs.src.b6:85:мдл   нркод 430165^наз
    010000^зонгп 430577     1^
re-dispak/rvs.src.b6:86:мдл   в6в7  430043^наз
    010000^зонгп 430600     1^
re-dispak/rvs.src.b6:87:мдл   экгдр 430344^наз
    010000^зонгп 430601     1^
re-dispak/rvs.src.b6:88:мдл   смена1430300^наз
    010000^зонгп 430602     1^
re-dispak/rvs.src.b6:92:мдл   экст  430347^наз
    010000^зонгп 430603     1^
re-dispak/rvs.src.b6:96:мдл   пчкз  430232^наз
    010000^зонгп 430604     1^
re-dispak/rvs.src.b6:97:мдл   авмд  430003^наз
    020000^зонгп 430605     1^
re-dispak/rvs.src.b6:98:мдл   эк7   430341^наз
    010000^зонгп 430607     1^
```

### ЗПКОМП  (1 вхождений)
```
dispak/dispak/macros.b6:243:ЗПКОМП430070
```

### ЧТКОМП  (150 вхождений)
```
dispak/dispak/disp99.b6:1613:ЧТКОМП420070
dispak/dispak/e64.b6:1439:ЧТКОМП420070
dispak/dispak/ekdisp.b6:255:ЧТКОМП420070
dispak/dispak/sostav.b6:112:ЧТКОМП420070
dispak/dispak/spe66.b6:314:ЧТКОМП420070
re-dispak/apunkt.be.b6:348:ЧТКОМП420070^
re-dispak/arfa.be.b6:3652:ЧТКОМП420070^
re-dispak/arkhin.be.b6:1868:ЧТКОМП420070^
re-dispak/avmd.be.b6:2165:ЧТКОМП420070^
re-dispak/avml.be.b6:1138:ЧТКОМП420070^
re-dispak/avrasp.be.b6:1608:ЧТКОМП420070^
re-dispak/bac.be.b6:1924:ЧТКОМП420070^
re-dispak/backup/vnimanije.be:127:ЧТКОМП420070
re-dispak/benson.be.b6:390:ЧТКОМП420070^
re-dispak/boek1.be.b6:3980:ЧТКОМП420070^
re-dispak/bonbot.be.b6:2087:ЧТКОМП420070^
re-dispak/bop.be.b6:488:ЧТКОМП420070^
re-dispak/bop1.be.b6:564:ЧТКОМП420070^
re-dispak/bop2.be.b6:282:ЧТКОМП420070^
re-dispak/cirkul.be.b6:672:ЧТКОМП420070^
re-dispak/clock.be.b6:273:ЧТКОМП420070^
re-dispak/consul.be.b6:437:ЧТКОМП420070^
re-dispak/diski.be.b6:2550:ЧТКОМП420070^
re-dispak/disp70.be.b6:3360:ЧТКОМП420070^
re-dispak/dmlmb.be.b6:2907:ЧТКОМП420070^
re-dispak/dnepr.be.b6:1943:ЧТКОМП420070^
re-dispak/dudka.be.b6:369:ЧТКОМП420070^
re-dispak/e60.be.b6:466:ЧТКОМП420070^
re-dispak/e60d.be.b6:214:ЧТКОМП420070^
re-dispak/e64.be.b6:1535:ЧТКОМП420070^
re-dispak/e71tk.be.b6:732:ЧТКОМП420070^
re-dispak/ek2.be.b6:574:ЧТКОМП420070^
re-dispak/ek3.be.b6:564:ЧТКОМП420070^
re-dispak/ek4.be.b6:483:ЧТКОМП420070^
re-dispak/ek5.be.b6:558:ЧТКОМП420070^
re-dispak/ek6.be.b6:547:ЧТКОМП420070^
re-dispak/ek7.be.b6:348:ЧТКОМП420070^
re-dispak/ekgdr.be.b6:1920:ЧТКОМП420070^
re-dispak/eko.be.b6:389:ЧТКОМП420070^
re-dispak/ekst.be.b6:498:ЧТКОМП420070^
re-dispak/ekvvod.bak.b6:2177:ЧТКОМП420070^
re-dispak/ekvvod.be.b6:1919:ЧТКОМП420070^
re-dispak/esml.be.b6:2325:ЧТКОМП420070^
re-dispak/espi80.be.b6:437:ЧТКОМП420070^
re-dispak/espl.be.b6:343:ЧТКОМП420070^
re-dispak/esuvvk.be.b6:138:ЧТКОМП420070^
re-dispak/gen.be.b6:2320:ЧТКОМП420070^
re-dispak/gens.be.b6:2370:ЧТКОМП420070^
re-dispak/gens1.be.b6:2167:ЧТКОМП420070^
re-dispak/gens2.be.b6:1136:ЧТКОМП420070^
re-dispak/gidra.be.b6:1652:ЧТКОМП420070^
re-dispak/gnus.be.b6:305:ЧТКОМП420070^
re-dispak/gp1.be.b6:582:ЧТКОМП420070^
re-dispak/gp2.be.b6:130:ЧТКОМП420070^
re-dispak/gp3.be.b6:187:ЧТКОМП420070^
re-dispak/gp4.be.b6:596:ЧТКОМП420070^
re-dispak/gruppa.be.b6:330:ЧТКОМП420070^
re-dispak/io.be.b6:292:ЧТКОМП420070^
re-dispak/janus.be.b6:1725:ЧТКОМП420070^
re-dispak/kachka.be.b6:87:ЧТКОМП420070^
re-dispak/kanal.be.b6:2635:ЧТКОМП420070^
re-dispak/kch.be.b6:204:ЧТКОМП420070^
re-dispak/khlam.be.b6:2748:ЧТКОМП420070^
re-dispak/khlam.be.bak.20260905_171321.b6:2082:ЧТКОМП420070^
re-dispak/kit.be.b6:192:ЧТКОМП420070^
re-dispak/komar.be.b6:1110:ЧТКОМП420070^
re-dispak/konfus.be.b6:1107:ЧТКОМП420070^
re-dispak/konvoy.be.b6:488:ЧТКОМП420070^
re-dispak/kz.be.b6:606:ЧТКОМП420070^
re-dispak/kz1.be.b6:1962:ЧТКОМП420070^
re-dispak/mott.be.b6:2891:ЧТКОМП420070^
re-dispak/nakopl.be.b6:1324:ЧТКОМП420070^
re-dispak/nakzad.be.b6:1617:ЧТКОМП420070^
re-dispak/nereza.be.b6:1750:ЧТКОМП420070^
re-dispak/nerot.be.b6:492:ЧТКОМП420070^
re-dispak/nombob.be.b6:1627:ЧТКОМП420070^
re-dispak/nrkod.be.b6:1224:ЧТКОМП420070^
re-dispak/nrot.be.b6:350:ЧТКОМП420070^
re-dispak/obraz.be.b6:1771:ЧТКОМП420070^
re-dispak/osa.be.b6:3175:ЧТКОМП420070^
re-dispak/osaner.be.b6:939:ЧТКОМП420070^
re-dispak/ovd.be.b6:1792:ЧТКОМП420070^
re-dispak/pchkz.be.b6:1454:ЧТКОМП420070^
re-dispak/pechat.be.b6:1505:ЧТКОМП420070^
re-dispak/perekh.be.b6:1852:ЧТКОМП420070^
re-dispak/pgs.be.b6:1639:ЧТКОМП420070^
re-dispak/pibesm.be.b6:441:ЧТКОМП420070^
re-dispak/plan.be.b6:498:ЧТКОМП420070^
re-dispak/plan2.be.b6:1187:ЧТКОМП420070^
re-dispak/plbesm.be.b6:353:ЧТКОМП420070^
re-dispak/prik1.be.b6:584:ЧТКОМП420070^
re-dispak/prik2.be.b6:527:ЧТКОМП420070^
re-dispak/prik3.be.b6:377:ЧТКОМП420070^
re-dispak/prik4.be.b6:691:ЧТКОМП420070^
re-dispak/prik5.be.b6:615:ЧТКОМП420070^
re-dispak/prik6.be.b6:606:ЧТКОМП420070^
re-dispak/prik7.be.b6:546:ЧТКОМП420070^
re-dispak/prik8.be.b6:181:ЧТКОМП420070^
re-dispak/prikaz.be.b6:1706:ЧТКОМП420070^
re-dispak/priskv.be.b6:607:ЧТКОМП420070^
re-dispak/proces.be.b6:2689:ЧТКОМП420070^
re-dispak/prorok.be.b6:753:ЧТКОМП420070^
re-dispak/puskach.be.b6:765:ЧТКОМП420070^
re-dispak/ra.be.b6:2422:ЧТКОМП420070^
re-dispak/resurs.be.b6:2366:ЧТКОМП420070^
re-dispak/rezarkh.be.b6:666:ЧТКОМП420070^
re-dispak/robot.be.b6:1748:ЧТКОМП420070^
re-dispak/rpipl.be.b6:391:ЧТКОМП420070^
re-dispak/sbor80.be.b6:1185:ЧТКОМП420070^
re-dispak/serp.be.b6:4352:ЧТКОМП420070^
re-dispak/serp2.be.b6:2190:ЧТКОМП420070^
re-dispak/serp3.be.b6:1807:ЧТКОМП420070^
re-dispak/serp4.be.b6:2849:ЧТКОМП420070^
re-dispak/serp5.be.b6:1256:ЧТКОМП420070^
re-dispak/siprog.be.b6:1562:ЧТКОМП420070^
re-dispak/skor1.be.b6:735:ЧТКОМП420070^
re-dispak/skor2.be.b6:812:ЧТКОМП420070^
re-dispak/slojka.be.b6:1971:ЧТКОМП420070^
re-dispak/sme.be.b6:666:ЧТКОМП420070^
re-dispak/smena1.be.b6:685:ЧТКОМП420070^
re-dispak/smena2.be.b6:320:ЧТКОМП420070^
re-dispak/smena3.be.b6:616:ЧТКОМП420070^
re-dispak/sostav.be.b6:116:ЧТКОМП420070^
re-dispak/spe66.be.b6:509:ЧТКОМП420070^
re-dispak/spoe67.be.b6:239:ЧТКОМП420070^
re-dispak/stat1s.be.b6:512:ЧТКОМП420070^
re-dispak/stat2s.be.b6:459:ЧТКОМП420070^
re-dispak/svyaz.be.b6:527:ЧТКОМП420070^
re-dispak/svyaz7.be.b6:1790:ЧТКОМП420070^
re-dispak/term.be.b6:770:ЧТКОМП420070^
re-dispak/termas.be.b6:1799:ЧТКОМП420070^
re-dispak/testdks/test_sis_k71.be.b6:530:ЧТКОМП420070^
re-dispak/testdks/vnimanije.be:127:ЧТКОМП420070
re-dispak/testdks/vnimanije.txt:1018:*чткомп420070^
re-dispak/trakh.be.b6:1038:ЧТКОМП420070^
re-dispak/trubka.be.b6:856:ЧТКОМП420070^
re-dispak/tupr.be.b6:147:ЧТКОМП420070^
re-dispak/uchet.be.b6:239:ЧТКОМП420070^
re-dispak/ukachka.be.b6:617:ЧТКОМП420070^
re-dispak/ukachka.be.bak.b6:557:ЧТКОМП420070^
re-dispak/upryach.be.b6:489:ЧТКОМП420070^
re-dispak/v1k.be.b6:1211:ЧТКОМП420070^
re-dispak/v3v4.be.b6:2062:ЧТКОМП420070^
re-dispak/v6v7.be.b6:2070:ЧТКОМП420070^
re-dispak/vektor.be.b6:257:ЧТКОМП420070^
re-dispak/visp.be.b6:427:ЧТКОМП420070^
re-dispak/vydach1.be.b6:2593:ЧТКОМП420070^
re-dispak/vydins.be.b6:3002:ЧТКОМП420070^
re-dispak/vyzovd.be.b6:681:ЧТКОМП420070^
re-dispak/vzu.be.b6:2707:ЧТКОМП420070^
```

### БЛМАК  (6 вхождений)
```
dispak/tests/bemsh-ms/bemsh.b6:23:блмак
dispak/tests/bemsh-ms/output.txt:37:      БЛМАК
dispak/tests/bemsh-standalone/bemsh-standalone.b6:30:блмак^
dispak/tests/bemsh-standalone/output.txt:7:БЛМАК
re-dispak/backup/vnimanije.be:120:блмак
re-dispak/testdks/vnimanije.be:120:блмак
```

