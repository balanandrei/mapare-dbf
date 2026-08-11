# Generare DBF din rapoarte de Trezorerie (XML → DBF)

Scriptul `generate_dbf.py` ia rapoarte XML de execuție bugetară de la Trezorerie
(„Execuție Angajamente bugetare”, generate de Oracle BI Publisher) și produce
pentru fiecare raport un fișier **DBF**, cu structura de câmpuri cerută (aceeași
cu a unui `forex.dbf` de referință: `SURSA`, `CAPITOL`, `DENCAP`, `ARTICOL`,
`DENART` + 13 câmpuri numerice de sume).

Maparea dintre tag-urile din XML și câmpurile din DBF (ex. `COD_FUNCTIONAL` →
`CAPITOL`, `PLATI_TREZ` → `PL_TREZ`) e cea din `mapare taguri.xlsx` și e scrisă
direct în script, în `TAG_MAP`.

Pentru fiecare folder de intrare cu rapoarte XML, scriptul produce câte un
`.dbf` pentru fiecare raport (nu le combină — fiecare raport e o lună/dată
separată).

Nu are nevoie de biblioteci externe — doar Python 3.11 sau mai nou.

---

## Structura proiectului

```
mapare-dbf/
├── generate_dbf.py       # scriptul - nu are nevoie de biblioteci externe
├── config.example.toml   # model de config - copiaza-l ca "config.toml" si editeaza-l
├── ruleaza_windows.bat   # dublu-click pe el ca sa rulezi totul pe Windows
├── .gitignore
└── README.md
```

`config.toml` (cel real, cu folderele tale) **nu se ține în git** — îl creezi
local dintr-o copie a `config.example.toml`, ca să nu ajungă căi personale de
pe calculatorul tău în repo. Pașii sunt mai jos.

---

## Configurare (`config.toml`)

Copiază `config.example.toml`, redenumește copia în `config.toml`, apoi
deschide-o cu Notepad și pune folderele tale:

```toml
input_folders = [
    "C:\\Users\\andisoft\\Documents\\RAPOARTE TREZORERIE 2026",
]
output_folder = "C:\\Users\\andisoft\\Documents\\Rapoarte_DBF"
```

- `input_folders` — unul sau mai multe foldere cu rapoarte `.xml`. **Fiecare
  folder produce propriul set de fișiere `.dbf`** (câte unul per raport),
  într-un subfolder cu numele lui, în `output_folder`.
- Pe Windows folosește `\\` (dublu backslash) în căi, cum e mai sus.

---

## Cum se rulează pe Windows (pas cu pas)

### 1. Instalează Python (o singură dată)

1. Intră pe <https://www.python.org/downloads/> și apasă butonul mare
   **„Download Python”**.
2. Rulează fișierul descărcat. **FOARTE IMPORTANT:** bifează căsuța
   **„Add Python to PATH”** din partea de jos a primei ferestre, apoi apasă
   **„Install Now”**.
3. Așteaptă să termine și apasă **Close**.

### 2. Pune fișierele la un loc

Copiază în același folder (ex. pe Desktop, un folder numit `Mapare`):
- `generate_dbf.py`
- `config.example.toml`
- `ruleaza_windows.bat`

### 3. Creează și editează `config.toml`

Copiază `config.example.toml`, redenumește copia în `config.toml`. Click-dreapta
pe el → **Deschide cu → Notepad**. Schimbă `input_folders` și `output_folder`
cu folderele tale (vezi mai sus). Salvează (Ctrl+S) și închide.

### 4. Rulează

**Dublu-click pe `ruleaza_windows.bat`.**

Se deschide o fereastră neagră, apar mesaje despre câte fișiere XML au fost
procesate, iar la final scrie **„Gata!”**. Fișierele `.dbf` sunt în folderul
de output pe care l-ai pus în config. Apasă o tastă ca să închizi fereastra.

> Dacă apare „python nu este recunoscut...”, înseamnă că la pasul 1 nu a fost
> bifat **„Add Python to PATH”**. Dezinstalează Python și reinstalează bifând
> căsuța.

---

## Rulare din linia de comandă (opțional, pentru avansați)

```
python generate_dbf.py                 # foloseste config.toml de langa script
python generate_dbf.py alt_config.toml # foloseste alt fisier de config
```

Pe Mac/Linux: `python3` în loc de `python`.

---

## Ce se întâmplă dacă un XML e stricat sau o sumă nu încape în DBF?

- Dacă un fișier XML e corupt sau nu are rânduri de detaliu, scriptul îl
  raportează ca `ESUAT`, **continuă** cu restul fișierelor și afișează la
  final lista celor eșuate. Un singur fișier problematic nu oprește tot
  procesul.
- Câmpurile numerice din DBF au o lățime fixă (ex. `REC_NEPL` are loc doar
  pentru sume până la `99999.99`). Dacă o sumă din XML e mai mare și nu
  încape, câmpul respectiv e **lăsat gol** în loc să fie trunchiat greșit,
  iar scriptul afișează un avertisment cu rândul și câmpul afectat — ca să
  poată fi verificat manual. Acesta e comportamentul observat și în
  `forex.dbf` de referință.
