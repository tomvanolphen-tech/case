# Verbeteringen — Swoep.AI Factuurverwerking

Dit document beschrijft de vier verbeteringen die zijn doorgevoerd in het factuurverwerkingssysteem. Per verbetering staat het probleem, de oplossing, de gewijzigde bestanden en hoe je het kunt testen.

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
