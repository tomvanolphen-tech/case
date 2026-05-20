# Verbeteringen — Swoep.AI Factuurverwerking

Dit document beschrijft alle verbeteringen die zijn doorgevoerd in het factuurverwerkingssysteem. Per verbetering staat het probleem, de oplossing, de gewijzigde bestanden en hoe je het kunt testen.

---

## Verbetering A — Blocking concern bij ontbrekende BTW-splitsing

### Probleem

Wanneer een factuur geen subtotaal (`amount_net`) én geen BTW-bedrag (`amount_vat`) bevatte, berekende het systeem stilzwijgend niks en ging verder met de boeking. De operator zag geen melding dat de BTW-splitsing onduidelijk was, waardoor er onjuiste journaalregels geboekt konden worden.

### Oplossing

De functie `propose()` detecteert nu dit geval en:

1. Maakt een journaalregel op het brutobedrag (zonder splitsing), gemarkeerd met "incl. BTW, splitsing onbekend".
2. Voegt een **blocking concern** toe zodat de operator het probleem ziet én de boeking niet kan goedkeuren zonder correctie.

Het blocking concern meldt:

> *"BTW-splitsing kan niet worden vastgesteld: zowel subtotaal als BTW-bedrag ontbreken. Corrigeer 'subtotaal' of 'btw_bedrag' via [c] voordat je akkoord gaat."*

### Gewijzigde bestanden

- `pipeline/propose.py` — regels 63–77: detectie en toevoeging van het blocking concern

### Hoe te testen

Verwerk een factuur die alleen een totaalbedrag vermeldt, zonder aparte BTW-regel of subtotaal:

```
python main.py <factuur-zonder-btw> --tenant acme
```

Het reviewscherm toont een rode blocking-melding. De [a] akkoord-optie is geblokkeerd totdat de operator via [c] het subtotaal of BTW-bedrag corrigeert.

---

## Verbetering B — Volledige boeking vastgelegd in runs JSON

### Probleem

Na een boeking werd de bevestiging opgeslagen in een apart `BOOK-*.json` bestand. Het centrale run-log (`runs/<run_id>.json`) bevatte geen boekinformatie. Daardoor waren twee bestanden nodig om een run volledig te reconstrueren, en de API-aanvraag zelf was nergens zichtbaar.

### Oplossing

De boekingsadapter retourneert nu een audit-dict met twee blokken:

- `booking_request` — de exacte HTTP POST die verstuurd is (methode, URL, body)
- `booking_response` — het antwoord van de boekhoudings-API (statuscode, booking_id, timestamp)

Dit audit-dict wordt via `**booking_audit` rechtstreeks in de stap `book_or_escalate` van het run-log opgeslagen. Er is geen apart BOOK-bestand meer.

### Gewijzigde bestanden

- `adapters/bookkeeping.py` — regels 105–117: opbouw van het audit-dict
- `main.py` — regel 151: spreiding van het audit-dict in het run-log

### Hoe te testen

Verwerk en boek een factuur volledig:

```
python main.py samples/invoice_001.txt --tenant acme
```

Open het aangemaakte bestand `runs/<run_id>.json`. De stap `book_or_escalate` bevat:

```json
"book_or_escalate": {
  "status": "booked",
  "booking_id": "BOOK-TEST-...",
  "booking_request": {
    "method": "POST",
    "url": "https://api.boekhouding.test/v1/invoices",
    "body": { ... }
  },
  "booking_response": {
    "status_code": 201,
    "booking_id": "BOOK-TEST-...",
    "message": "Invoice booked successfully",
    "timestamp": "..."
  }
}
```

---

## Verbetering C — Reden voor rekeningkeuze zichtbaar in reviewscherm

### Probleem

Het reviewscherm toonde welke rekening voorgesteld werd (bijv. 4350), maar niet waarom. De operator wist niet of het een AI-suggestie was, een vendor-mapping uit de config, of gewoon de standaard-fallback. Hierdoor keurde de operator iets goed zonder de redenering te kennen.

### Oplossing

De functie `_resolve_account_code()` geeft naast de rekeningcode nu ook een reden terug. Die reden wordt als **info-concern** toegevoegd aan de `ProposedBooking`, zodat het automatisch zichtbaar is in het reviewscherm onder "AGENT- EN VALIDATOR-BEVINDINGEN".

De mogelijke redenen zijn:

| Situatie | Reden |
|---|---|
| AI heeft een rekening gesuggereerd | `AI-suggestie (confidence: 0.97)` |
| Vendor staat in config vendors-mapping | `Vendor-mapping in config: KPN → 4300` |
| Geen specifieke match gevonden | `Standaard kostenrekening (geen specifieke match gevonden)` |

De info-melding ziet er zo uit in het reviewscherm:

> *"Rekeningkeuze: 4200 — AI-suggestie (confidence: 0.97)"*

### Gewijzigde bestanden

- `pipeline/propose.py` — regels 4–21: `_resolve_account_code()` retourneert nu `tuple[str, str]`
- `pipeline/propose.py` — regels 44–50: info-concern wordt toegevoegd aan `all_concerns`

### Hoe te testen

Verwerk een factuur:

```
python main.py samples/invoice_001.txt --tenant acme
```

In het reviewscherm, onder de sectie "AGENT- EN VALIDATOR-BEVINDINGEN", verschijnt een info-regel met de rekeningkeuze en de reden. Er is geen extra display-code nodig — info-concerns worden al getoond.

---

## Verbetering D — Beheerscherm voor geleerde regels

### Probleem

Geleerde regels konden alleen worden toegevoegd tijdens het verwerken van een factuur (via een operator-correctie). Er was geen manier om regels te bekijken, te bewerken of te verwijderen buiten een actieve run. Dit betekende:

- Conflicterende regels (bijv. twee regels voor dezelfde vendor met verschillende rekeningen) konden niet worden opgeruimd.
- De operator kon niet nagaan wat de agent "weet".
- Een developer moest handmatig in markdown-bestanden editen om fouten te herstellen.

### Oplossing

Twee onderdelen zijn toegevoegd:

**1. Parse- en mutatiefuncties in `core/tenant.py`**

| Functie | Werking |
|---|---|
| `list_rules(slug)` | Parset `learned_rules.md` en geeft een lijst van `ParsedRule`-objecten terug (nummer, datum, scope, tekst, run-referentie) |
| `delete_rule(slug, rule_number)` | Verwijdert één regel en hernummert de rest |
| `update_rule(slug, rule_number, new_text)` | Vervangt de tekst van één regel |
| `_rewrite_rules(slug, rules)` | Interne helper: schrijft het volledige bestand opnieuw vanuit een lijst regels |

**2. Interactieve CLI via `main.py --manage-rules`**

Het scherm toont een overzicht van alle regels met opties om te verwijderen, bewerken of volledig te bekijken:

```
========================================================
  GELEERDE REGELS  |  ACME Corp
========================================================

  [1] 2026-05-19  vendor: PostNL B.V.
      "Facturen van PostNL B.V. worden altijd geboekt op rekening 4350..."

  [2] 2026-05-19  vendor: Staples Nederland B.V.
      "Facturen van Staples... rekening 4200..."

  [3] 2026-05-19  vendor: Staples Nederland B.V.
      "Facturen van Staples... rekening 4100..."

--------------------------------------------------------
  [d <nr>] Verwijder regel   [e <nr>] Bewerk regel
  [v <nr>] Bekijk volledig   [q] Terug
--------------------------------------------------------
```

Na een verwijdering hernummert het systeem automatisch de overige regels.

### Gewijzigde bestanden

- `core/tenant.py` — regels 85–160: `list_rules()`, `delete_rule()`, `update_rule()`, `_rewrite_rules()`
- `main.py` — regels 168–250: `manage_rules_cli()` functie
- `main.py` — regels 261–262: `--manage-rules` argument in de argumentparser

### Hoe te testen

Start het beheerscherm:

```
python main.py --manage-rules --tenant acme
```

Het scherm toont een regeloverzicht. Test de volgende acties:

- `v 1` — bekijk de volledige tekst van regel 1
- `d 2` — verwijder regel 2 (met bevestigingsvraag); controleer dat `learned_rules.md` is bijgewerkt en hernummerd
- `e 1` — bewerk de tekst van regel 1; controleer de nieuwe tekst in `learned_rules.md`
- `q` — sluit het scherm af

---

## Verbetering E — Originele factuurtext inzien tijdens review

### Probleem

De operator kon tijdens de review niet de originele factuur raadplegen. Als de AI een veld onzeker of onjuist had geëxtraheerd, moest de operator het bronbestand apart openen. Dit verhoogde het risico op blinde goedkeuring.

### Oplossing

Een nieuwe optie `[v]` is toegevoegd aan het reviewmenu. Na het indrukken verschijnt de volledige ruwe factuurtext direct in de terminal, waarna het menu opnieuw verschijnt.

```
── ORIGINELE FACTUURTEXT ──────────────────────────
FACTUUR

Exact Software B.V.
...
────────────────────────────────────────────────────
```

### Gewijzigde bestanden

- `pipeline/review.py` — `_print_menu()`: `[v]` toegevoegd aan het menu
- `pipeline/review.py` — `run_review()`: `elif choice == "v"` handler toegevoegd

### Hoe te testen

Verwerk een factuur en druk tijdens de review op `[v]`. De originele factuurtext verschijnt en het menu keert daarna terug.

---

## Verbetering F — "Geleerde regel" als aparte redenering voor rekeningkeuze

### Probleem

Als de AI een rekeningnummer suggereerde op basis van een geleerde regel, toonde het reviewscherm "AI-suggestie (confidence: 0.97)". De operator kon niet zien of de suggestie uit de AI's eigen kennis kwam of uit een eerder door hem opgeslagen correctie.

### Oplossing

`_resolve_account_code()` controleert nu of er een geleerde regel bestaat voor de huidige vendor die het gesuggereerde rekeningnummer verklaart. Als dat zo is, toont het reviewscherm:

> *"Rekeningkeuze: 4350 — Geleerde regel: PostNL B.V. → 4350"*

De prioriteitsvolgorde is nu expliciet:
1. Geleerde regel (vendor-specifiek)
2. AI-suggestie (eigen redenering LLM)
3. Vendor-mapping in config.yaml
4. Standaard kostenrekening

### Gewijzigde bestanden

- `pipeline/propose.py` — `_resolve_account_code()`: `slug` parameter toegevoegd, lookup op geleerde regels

### Hoe te testen

Verwerk een factuur van een vendor waarvoor een geleerde regel bestaat (bijv. PostNL na een eerdere correctie). Het reviewscherm toont "Geleerde regel: PostNL B.V. → 4350" in plaats van "AI-suggestie".

---

## Verbetering G — Relevantie filtering van few-shot voorbeelden

### Probleem

Bij elke factuurverwerking werden altijd de 3 meest recente voorbeelden meegestuurd naar de AI, ongeacht de vendor. Een recent Staples-voorbeeld is weinig nuttig als je een PostNL-factuur verwerkt — en kan zelfs verwarring veroorzaken.

### Oplossing

De nieuwe functie `load_relevant_examples()` sorteert voorbeelden op relevantie: voorbeelden waarvan de vendor in de huidige factuurtext voorkomt, gaan als eerste naar de AI. De overige slots worden gevuld met de meest recente andere voorbeelden.

Voorbeeld: bij 4 opgeslagen voorbeelden (2x PostNL, 2x Staples) en een nieuwe PostNL-factuur sturen we de 2 PostNL-voorbeelden als eerste, dan de meest recente Staples als derde.

### Gewijzigde bestanden

- `core/tenant.py` — nieuwe functie `load_relevant_examples(slug, raw_text, n)`
- `pipeline/extract.py` — `extract()` gebruikt nu `load_relevant_examples()` i.p.v. `load_recent_examples()`

### Hoe te testen

Sla voorbeelden op van meerdere vendors. Verwerk daarna een factuur van een specifieke vendor en controleer in het run-log (`runs/<tenant>/<run_id>.json`) onder `steps.extract.user_prompt` dat de vendor-relevante voorbeelden bovenaan staan.

---

## Verbetering H — Scaffolding voor nieuwe tenant

### Probleem

Een nieuwe klant toevoegen vereiste kennis van de interne mapstructuur en YAML-indeling. Een fout in `config.yaml` (verkeerde inspringing, ontbrekend veld) leidde tot een cryptische Python-fout diep in de pipeline — niet bij het aanmaken van de klant.

### Oplossing

Twee onderdelen:

**1. `create_tenant()` in `core/tenant.py`**

Maakt automatisch de volledige tenantmap aan met:
- `config.yaml` op basis van een ingevuld template met verstandige standaardwaarden
- Lege `learned_rules.md` met juiste header
- Leeg `examples.jsonl`

**2. YAML-validatie in `load_tenant_config()`**

Bij elke opstart controleert het systeem of `config.yaml` geldig YAML is en de verplichte velden (`name`, `account_mapping`) bevat. Een heldere foutmelding wijst direct naar het probleem.

**3. `--new-tenant` CLI in `main.py`**

```
python main.py --new-tenant
```

Interactief scherm vraagt slug, naam, BTW-nummer en valuta. Daarna is de tenant klaar voor gebruik.

### Gewijzigde bestanden

- `core/tenant.py` — `_CONFIG_TEMPLATE`, `create_tenant()`, YAML-validatie in `load_tenant_config()`
- `main.py` — `new_tenant_cli()` functie en `--new-tenant` argument

### Hoe te testen

```
python main.py --new-tenant
```

Vul een nieuwe slug in (bijv. `testklant`). Controleer dat `tenants/testklant/` bestaat met `config.yaml`, `learned_rules.md` en `examples.jsonl`. Verwerk daarna direct een factuur voor die tenant.

---

## Verbetering I — Run-logs per tenant in eigen submap

### Probleem

Alle run-logs van alle klanten lagen in dezelfde `runs/` map. Bij meerdere klanten werd het onmogelijk om snel alle facturen van één specifieke klant terug te vinden zonder handmatig JSON-bestanden te scannen.

### Oplossing

Run-logs worden nu opgeslagen in `runs/<tenant_slug>/<run_id>.json`. De submap wordt automatisch aangemaakt als die nog niet bestaat. Bestaande logs in de platte `runs/` map blijven onaangetast.

### Gewijzigde bestanden

- `pipeline/log.py` — `save_run_log()`: pad gewijzigd naar `config.RUNS_DIR / run_log.tenant_slug / run_id`

### Hoe te testen

Verwerk een factuur voor tenant `acme`. Het log verschijnt in `runs/acme/<run_id>.json` in plaats van `runs/<run_id>.json`.

---

## Verbetering J — Originele factuurtext inzien in de browser

### Probleem

In de webinterface kon de operator de originele factuur niet raadplegen tijdens de review. Als de AI een veld verkeerd had geëxtraheerd, moest de operator het bronbestand apart openen. Dit verhoogde het risico op blinde goedkeuring.

### Oplossing

Een knop **"Bekijk factuur"** is toegevoegd aan de actiebalk onderaan het reviewscherm. Na het klikken klapt de originele factuurtext open boven de velden. Een tweede klik verbergt de tekst weer.

De ruwe tekst wordt via de bestaande status-API meegestuurd (`raw_text` veld) en in de browser getoond in een leesbaar blok.

### Gewijzigde bestanden

- `web/routers/pipeline.py` — `raw_text` toegevoegd aan de `_serialise_run()` response
- `static/pages/review.html` — inklapbaar factuur-paneel en "Bekijk factuur" knop in de actiebalk
- `static/js/review.js` — `toggleRawText()` functie en koppeling aan de knop

### Hoe te testen

Start de server en verwerk een factuur via de browser:

```
python -m uvicorn web.app:app --reload --port 8000
```

Open het reviewscherm en klik op **"Bekijk factuur"** in de actiebalk. De originele factuurtext verschijnt boven de geëxtraheerde velden. Klik opnieuw om te verbergen.
