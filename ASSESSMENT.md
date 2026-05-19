# Assessment — Swoep.AI Invoice Processing Agent

**Repo:** https://github.com/tomvanolphen-tech/case
**Tijdsbesteding:** ~4 uur
**Datum:** 2026-05-19

---

## A. Architectuur & ontwerpkeuzes

### Op hoofdlijnen

Elke factuur doorloopt acht stappen, sequentieel, één factuur per run:

```
ingest → classify_tenant → extract → validate → propose → review → book_or_escalate → log
```

| Stap | Verantwoordelijkheid | Deterministisch? |
|------|----------------------|------------------|
| `ingest` | Lees bestand, normaliseer naar tekst, ken `run_id` toe | Ja |
| `classify_tenant` | Bepaal voor welke klant de factuur is (CLI-arg of LLM-fallback) | Ja (CLI) / Nee (auto) |
| `extract` | LLM extraheert velden + confidence + agent-concerns | Nee |
| `validate` | Verplichte velden, rekenkundige consistentie, datum, duplicaten | Ja |
| `propose` | Mapt velden naar journaalpost o.b.v. tenant-config | Ja |
| `review` | Operator-CLI: goedkeuren, corrigeren, escaleren, annuleren | Mens-in-de-lus |
| `book_or_escalate` | Verstuurt boekstuk naar boekhoud-API (mock) of escaleert | Ja |
| `log` | Schrijft volledige audit-trail naar `runs/<run_id>.json` | Ja |

### Componenten en verantwoordelijkheden

```
main.py                     ── orkestratie van de 8-stappen pipeline
config.py                   ── omgevingsvariabelen, paden
core/
  models.py                 ── dataclasses (FieldValue, Concern, ProposedBooking, ...)
  llm.py                    ── thin wrapper rond Anthropic SDK
  tenant.py                 ── lees/schrijf tenant config + leerregels + voorbeelden
  rule_formulator.py        ── LLM die operator-correcties tot regels formuleert
pipeline/                   ── één module per stap (extract, validate, propose, review, ...)
adapters/
  bookkeeping.py            ── abstract interface + Mock implementatie
  mailbox.py                ── escalatie-kanaal (mock)
tenants/<slug>/
  config.yaml               ── rekeningschema, vereiste velden, confidence-drempel
  learned_rules.md          ── operator-correcties als leesbare regels
  examples.jsonl            ── gecorrigeerde facturen als few-shot voorbeelden
runs/<run_id>.json          ── volledige audit-trail per run
```

### Gegevensstroom

```
factuur.{txt,pdf,xlsx,html}
        │
        ▼
   [ingest]                                            run_id, raw_text, source_type
        │
        ▼
   [classify_tenant] ◀── --tenant acme                 tenant_slug
        │
        ▼
   [extract] ◀── tenant config, learned_rules, examples
        │                                              ExtractionResult
        │                                                ├─ fields + confidence
        │                                                ├─ line_items
        │                                                └─ agent_concerns
        ▼
   [validate] ◀── tenant config, run-log historie
        │                                              ValidationResult
        │                                                └─ concerns (validator)
        ▼
   [propose] ◀── tenant.account_mapping
        │                                              ProposedBooking
        │                                                └─ journal_lines (D/C)
        ▼
   [review]  ◀──▶  operator CLI
        │           │
        │           ├─ [c] corrigeren → re-propose
        │           ├─ [a] goedkeuren
        │           ├─ [fa] force-approve (vereist bevestiging)
        │           ├─ [e] escaleren
        │           └─ [x] annuleren (niets opslaan)
        │
        │           bij correctie + bevestiging:
        │             → LLM formuleert regel
        │             → conflictcheck tegen learned_rules.md
        │             → schrijf naar learned_rules.md + examples.jsonl
        ▼
   [book_or_escalate]
        │
        ├─ approve / force_approve → POST /invoices (mock)
        └─ escalate / quit        → mailbox (mock)
        │
        ▼
   [log] → runs/<run_id>.json
```

### Ontwerpkeuzes die ook anders hadden gekund

| # | Keuze | Alternatief | Waarom deze kant op |
|---|-------|-------------|---------------------|
| 1 | LLM voor extractie | Regelgebaseerd (regex/template per leverancier) | Eén implementatie werkt voor onbekende leveranciers en talen. Tradeoff: niet-deterministisch → daarom een aparte deterministische validator achter de LLM. |
| 2 | Tenant-config in filesystem | Database (Postgres, etc.) | Transparant, in git te zetten, geen infra nodig. Schaalt slecht bij honderden tenants en bij concurrent writes op `learned_rules.md`. |
| 3 | Sequentieel, één factuur per run | Async / batch worker | MVP — simpel, makkelijk te debuggen. Productie met volume vereist een queue. |
| 4 | Operator-eindverantwoordelijk | Auto-approve boven confidence X | Het kerncontract is "niets boeken zonder akkoord". Een fout geboekt grootboek terugdraaien is duurder dan een operator-minuut. |
| 5 | Run-log per JSON-bestand | Centrale audit-database | Reproduceerbaar, transparant, makkelijk te delen voor één run. Maar duplicate-check via globbing schaalt slecht (zie risico's). |
| 6 | Leerloop via natural-language regels | Fine-tuning per tenant | Leesbaar, aanpasbaar door operator, geen ML-pipeline nodig. Prompt-lengte groeit met aantal regels — op enig moment is herindexering nodig. |
| 7 | Mock-adapter met expliciet HTTP-contract | Directe functie-aanroep stub | Vervangbaar door echte client zonder pipeline-wijziging. Contract zichtbaar in code. |
| 8 | CLI als operator-interface | Web-UI vanaf dag 1 | Snel werkend, focus op pipeline-logica. `review.py` is geabstraheerd zodat een web-UI later kan zonder pipeline-aanpassingen. |
| 9 | Per-tenant confidence-drempel | Globale drempel | Klanten met grote, gestandaardiseerde facturen kunnen scherper, kleine klanten ruimer. |
| 10 | Concerns met severity uit twee bronnen (LLM + validator) | Alleen één bron | LLM ziet semantische twijfel ("ambigue leverancier"); validator ziet harde regels ("BTW klopt niet"). Samenvoegen in één lijst voor operator. |
| 11 | Force-approve met expliciete typecode bevestiging | Stille override | Maakt de mens-in-de-lus zichtbaar in de audit log: `operator_confirmation` veld bewaart de bevestiging letterlijk. |
| 12 | Operator-correcties worden via LLM tot regels geformuleerd, met conflictcheck | Direct opslaan zonder review | Voorkomt regelvervuiling en tegenstrijdige regels. Tradeoff: extra LLM-call per correctie. |

---

## B. Wat we nodig hebben om dit echt te bouwen

### Development & test

**Van ons (Swoep.AI / dev-team):**
- Anthropic API-key (sandbox, beperkt budget)
- CI-omgeving (GitHub Actions volstaat)
- Lokale Python 3.11+ omgeving
- Mock-boekhoud-adapter (al aanwezig)

**Van de klant per administratie:**
- 20–50 voorbeeldfacturen, gemixt:
  - verschillende leveranciers
  - verschillende talen (NL/EN, evt. DE/FR)
  - verschillende formaten (PDF gescand, PDF native, e-facturen, Excel)
  - inclusief randgevallen: creditfacturen, deelfacturen, valuta ≠ EUR, verlegde BTW
- Rekeningschema (welke grootboekrekeningen, welke nummers)
- Mapping van vaste leveranciers naar standaard-grootboekrekeningen
- Lijst van verplichte velden voor deze klant
- Confidence-drempel afspraak (bv. 0.85 standaard, 0.95 voor grote bedragen?)
- 5–10 historisch correct geboekte facturen om `examples.jsonl` te seeden
- BTW-bijzonderheden (verlegde BTW, 0%-tarief, internationale leveranciers)
- Antwoord op: "Wat is een 'blocking' situatie waar de operator nooit zelf mag beslissen?"

### Productie

**Van ons:**
- Productie-omgeving (cloud of on-prem — keuze) met:
  - Python runtime
  - Persistente storage voor `runs/` en `tenants/`
  - Backup-strategie voor `learned_rules.md` en `examples.jsonl` (verlies = verlies van leerwerk)
- Anthropic API-key (productie, met passende rate-limit en spend-cap)
- Monitoring: confidence-drift per tenant, escalation rate, force-approve rate, foutpercentage van LLM-parsing
- Logging-infrastructuur met retentie- en privacy-beleid

**Van de klant:**
- Echte boekhoud-API:
  - URL + auth-mechanisme (OAuth? API key? mTLS?)
  - Volledig API-contract (request/response schema, foutcodes, rate-limits)
  - Sandbox-omgeving om tegen te testen
  - Idempotency-key support? (Belangrijk — zie risico's)
- Escalatie-kanaal:
  - Welke mailbox of welk ticket-systeem?
  - SLA op opvolging
- Authenticatie/autorisatie:
  - Wie zijn de operators? (named users met audit-trail?)
  - Wie mag force-approven?
  - SSO-integratie?
- Wettelijk / governance:
  - Bewaartermijn voor factuurdata + run-logs (AVG, fiscale bewaarplicht 7 jaar)
  - Wie tekent eindverantwoordelijk voor boekingen?
  - PII-scrubbing afspraken (vendor-namen, persoonsgegevens in omschrijvingen)
  - Wie heeft toegang tot `learned_rules.md` en welke approval flow voor wijzigingen?
- Onboarding-proces:
  - Wie maakt nieuwe tenant aan en valideert de config?
  - Hoe wordt het rekeningschema gesynchroniseerd met het echte grootboek?

### Niet-functioneel

- SLA-afspraken (uptime, max latency per factuur)
- Kostenrapportage (LLM-tokens per tenant — wie betaalt wat?)
- Incident-respons proces (wat als de LLM systematisch fout gaat?)

---

## C. Code

Werkende implementatie in deze repo:

- **Entry point:** `main.py`
- **Run:**
  ```bash
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=sk-ant-...
  python main.py samples/invoice_001.txt --tenant acme
  ```
- **Twee voorbeeldtenants:** `tenants/acme/`, `tenants/betaworks/`
- **Voorbeeldfacturen:** `samples/`

Geïmplementeerd:
- Volledige 8-stappen pipeline, draaibaar end-to-end
- LLM-extractie met confidence + agent-concerns (Claude Sonnet 4.6)
- Validator: verplichte velden, confidence-drempel, rekenkundige consistentie, datum-checks, duplicate-detectie via run-log scan
- Operator-CLI met `[a]`, `[fa]`, `[c]`, `[e]`, `[q]`, `[x]`
- Leerloop: correctie → LLM-regelformulering → conflictcheck → opslaan in `learned_rules.md` + `examples.jsonl`
- Mock-boekhoud-adapter met expliciet HTTP-contract (`POST /invoices`), met simulatie van 422 en 500
- Volledige run-log per factuur (`runs/<run_id>.json`) met prompts, ruwe LLM-respons, alle stap-resultaten
- Multi-tenant via filesystem (nieuwe klant = nieuwe map, geen code)
- Bestandsformaten: plain text, PDF (`pdfplumber`), HTML (`beautifulsoup4`), Excel (`openpyxl`); OCR is gestubd

---

## D. Reflectie

### Wat ik bewust niet heb gedaan in deze 4 uur, en waarom

**1. Geen tests.** Bewust uitgesteld om eerst end-to-end functionaliteit werkend te hebben — pas dan weet je wat het te testen gedrag eigenlijk is. Voor een systeem dat met geldwerkstroom werkt is dit het allereerste dat ik zou toevoegen na deze 4 uur. `validate.py`, `propose.py`, `duplicate_check.py` zijn pure functies en lenen zich uitstekend voor unit-tests; pipeline-stappen kunnen end-to-end getest worden met gefixeerde LLM-respons.

**2. Geen echte database.** Tenant-config en run-logs leven op het filesystem. Voor een MVP transparant en in git te zetten; bij volume (>1000 facturen, >50 tenants) loop je tegen schaalproblemen aan — vooral de duplicate-check die nu *elke* run-log leest.

**3. Geen authenticatie / multi-user.** Operator = wie het commando uitvoert. Werkt voor MVP en demo; productie vereist named users met audit-trail per actie.

**4. Geen async / batch.** Eén factuur per run, sequentieel. Simpel om te debuggen, maar bij 1000 facturen per dag wil je een queue worker met retry-logic.

**5. Geen idempotentie op `book()`.** Als de boekhoud-API call slaagt maar het log-schrijven daarna faalt, kan een retry tot een dubbele boeking leiden.

**6. Geen schema-validatie op `tenants/<slug>/config.yaml`.** Een typo in `required_fields` of `account_mapping` faalt pas tijdens runtime, mogelijk halverwege een factuur.

**7. Geen retentie / PII-scrubbing op run-logs.** Logs bevatten volledige factuurinhoud (vendors, mogelijk persoonsgegevens) en complete prompts. AVG-relevant zodra dit live gaat.

**8. Geen observability.** Geen metrics op confidence-drift, escalation-rate of force-approve-rate per tenant. Voor een leersysteem essentieel om te zien of `learned_rules.md` daadwerkelijk helpt of regressies veroorzaakt.

**9. OCR is alleen een stub.** `pytesseract`-integratie is voorzien maar niet getest met echte scans.

**10. Geen real-API client.** Alleen de mock-adapter — een echte implementatie hangt af van het API-contract van de boekhoudleverancier.

### Volgende stap als ik door zou gaan

Geprioriteerd, in deze volgorde:

1. **Tests + CI.** `pytest` voor `validate.py`, `propose.py`, `duplicate_check.py` (deterministisch — geen LLM nodig). GitHub Actions workflow zodat elke push gevalideerd wordt. Voorwaarde voor alle volgende stappen.
2. **Idempotentie op `book()`.** Client-side idempotency key (hash van invoice_number + vendor + amount + tenant) zodat retry geen dubbele boeking oplevert.
3. **Schema-validatie op tenant-config.** Pydantic of jsonschema bij laden; faal vroeg met een leesbare foutmelding.
4. **Index voor duplicate-detectie.** Aparte `bookings.jsonl` of SQLite met (tenant, vendor, invoice_number, amount, run_id) zodat de check O(1) wordt en niet afhankelijk is van run-log retentie.
5. **Retentie- en PII-beleid in run-logs.** Configureerbare opschoning + redactie van velden die geen audit-waarde toevoegen.
6. **Metrics-dashboard.** Per tenant: aantal facturen, escalation rate, force-approve rate, gemiddelde confidence, aantal correcties per veld. Zodat je ziet of de leerloop werkt.

### Grootste risico in dit ontwerp

**Banaliteit-bias op de operator.** Het hele systeem hangt erop dat de operator de voorgestelde boeking serieus reviewt. Bij volume (50+ facturen per dag, meeste correct) treedt onvermijdelijk reflexmatig goedkeuren op. De LLM kan systematisch verkeerd extraheren — bijvoorbeeld door een prompt-injection in factuurtekst, of door modeldrift bij een Claude-versie-update — en als die output "redelijk" oogt zal een vermoeide operator er doorheen klikken.

Mitigaties die in het huidige ontwerp zitten:
- Validator achter de LLM die hard rekent (BTW-som, datum, verplichte velden)
- Blocking concerns blokkeren `[a]` volledig — alleen `[fa]` met letterlijke bevestigingscode
- Confidence-drempel per tenant
- Volledige audit-trail per run

Wat ontbreekt en wat ik zou toevoegen:
- Tweede onafhankelijke LLM-pass die de eerste extractie controleert (cross-check), tegen extra kosten
- Mogelijkheid om hoogwaardige facturen (boven X euro) een tweede operator-paar-ogen te vereisen
- Een dashboard dat force-approve-rate per operator monitort; een operator die structureel veel force-approved is een rood signaal
- Detectie van prompt-injection-pogingen in factuurtekst (eenvoudige heuristieken: instructies zoals "ignore previous", "you are now ...", verdachte tokens)

Het tweede risico, met afstand: de **dubbele-boeking-race** in `book_or_escalate`. Zonder idempotency key kan een crash tussen API-call en log-schrijven tot een dubbele boeking leiden bij retry. Dit is sluipender dan de operator-bias omdat er geen menselijke kans is om het te merken — de boeking is al gebeurd.

---

*Bijlage: `Eisen.docx` in de repo bevat de formele eisen waar de implementatie op gebaseerd is.*
