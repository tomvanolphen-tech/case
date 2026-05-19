# Swoep.AI — Invoice Processing Agent

Een Python-systeem dat inkomende facturen verwerkt tot een voorgesteld boekstuk. De operator is eindverantwoordelijk: niets wordt geboekt zonder expliciete goedkeuring.

---

## Architectuur

Elke factuur doorloopt altijd dezelfde acht stappen:

```
ingest → classify_tenant → extract → validate → propose → review → book_or_escalate → log
```

| Stap | Wat er gebeurt |
|------|----------------|
| `ingest` | Leest het factuurbestand, maakt unieke `run_id` aan |
| `classify_tenant` | Bepaalt voor welke klant de factuur is |
| `extract` | LLM extraheert alle velden + confidence + agent-concerns |
| `validate` | Deterministische checks: verplichte velden, bedragen, datum |
| `propose` | Mapt velden naar een journaalpost op basis van klantconfig |
| `review` | Operator-CLI: goedkeuren, corrigeren, escaleren of annuleren |
| `book_or_escalate` | Stuurt boekstuk naar de boekhoud-API (mock) |
| `log` | Slaat volledige audit-trail op in `runs/<run_id>.json` |

---

## Installatie

```bash
pip install -r requirements.txt
```

Vereiste omgevingsvariabele:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Linux/Mac
$env:ANTHROPIC_API_KEY = "sk-ant-..." # Windows PowerShell
```

---

## Gebruik

```bash
# Standaard gebruik
python main.py samples/invoice_001.txt --tenant acme

# Productie-omgeving
python main.py samples/invoice_001.txt --tenant acme --env prod

# Bestandstype expliciet opgeven
python main.py factuur.pdf --tenant acme --source-type pdf

# Automatische tenant-detectie (niet aanbevolen)
python main.py samples/invoice_001.txt --auto-classify
```

### Operator-menu

```
[a]  Goedkeuren & boeken
[fa] Force-approve (bij blocking concerns, vereist bevestiging)
[c]  Veld corrigeren
[e]  Escaleren
[q]  Afsluiten (opslaan als geëscaleerd)
[x]  Annuleren (niets opslaan, niets boeken)
```

### Velden corrigeren

Bij `[c]` kun je velden opgeven in het **Nederlands of Engels**:

| Nederlands | Engels | Omschrijving |
|-----------|--------|--------------|
| `leverancier` | `vendor` | Naam leverancier |
| `factuurnummer` | `invoice_number` | Factuurnummer |
| `factuurdatum` | `invoice_date` | Factuurdatum |
| `vervaldatum` | `due_date` | Vervaldatum |
| `totaal` | `amount_gross` | Totaal incl. BTW |
| `btw_bedrag` | `amount_vat` | BTW-bedrag |
| `subtotaal` | `amount_net` | Subtotaal excl. BTW |
| `btw_percentage` | `vat_rate` | BTW-tarief (bijv. 0.21) |
| `valuta` | `currency` | Valutacode (bijv. EUR) |
| `omschrijving` | `description` | Omschrijving |
| `rekening` | `suggested_acct` | Grootboekrekening |
| `kostenplaats` | — | Kostenplaats |

---

## Multi-tenant

Elke klant heeft een geïsoleerde directory:

```
tenants/<slug>/
├── config.yaml          # rekeningschema, verplichte velden, confidence-drempel
├── learned_rules.md     # operator-correcties als leesbare regels
└── examples.jsonl       # gecorrigeerde facturen als few-shot voorbeelden
```

**Nieuwe klant toevoegen = nieuwe map aanmaken, geen code:**

```bash
mkdir tenants/nieuwe-klant
# Maak config.yaml aan op basis van tenants/acme/config.yaml
```

---

## Leerloop

Wanneer een operator een veld corrigeert:

1. LLM formuleert een conceptregel in natuurlijke taal
2. Operator ziet de regel, kan aanpassen en bevestigt
3. Conflictcheck: nieuwe regel wordt gecontroleerd tegen bestaande regels
4. Regel opgeslagen in `learned_rules.md` met datum, scope en run-referentie
5. Voorbeeld opgeslagen in `examples.jsonl`

Volgende factuur van dezelfde tenant: de LLM krijgt de leerregel en het voorbeeld mee in de prompt en past het direct toe — zonder code-wijziging.

---

## Reproduceerbaar

Elke run schrijft `runs/<run_id>.json` met:

- De exacte prompts die naar het LLM zijn gestuurd
- Ruwe LLM-respons en confidence per veld
- Agent-concerns met reden en vervolgstappen
- Operator-acties en correcties
- Booking ID en omgeving (test/prod)

---

## Omgevingsvariabelen

| Variabele | Default | Omschrijving |
|-----------|---------|--------------|
| `ANTHROPIC_API_KEY` | — | Verplicht |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | LLM-model |
| `BOOKKEEPING_ENV` | `test` | Boekhoud-omgeving (`test` of `prod`) |
| `BOOKKEEPING_API_URL_TEST` | `https://api.boekhouding.test/v1` | Test-API URL |
| `BOOKKEEPING_API_URL_PROD` | `https://api.boekhouding.nl/v1` | Productie-API URL |
| `MOCK_FORCE_ERROR` | — | Zet op `1` om een 500-fout te simuleren |

---

## Ondersteunde bestandsformaten

| Formaat | Status |
|---------|--------|
| Plain text (`.txt`) | ✅ Werkt |
| PDF (`.pdf`) | 🔧 Stub — gebruik `pdfplumber` of `pypdf` |
| HTML (`.html`) | 🔧 Stub — gebruik `beautifulsoup4` |
| Excel (`.xlsx`) | 🔧 Stub — gebruik `openpyxl` |
| Scan/afbeelding | 🔧 Stub — gebruik `pytesseract` |

---

## Projectstructuur

```
├── main.py                  # Entry point
├── config.py                # Globale instellingen
├── core/
│   ├── models.py            # Dataclasses
│   ├── llm.py               # Anthropic SDK wrapper
│   ├── tenant.py            # Tenant I/O
│   └── rule_formulator.py   # LLM-regelformulering + conflictdetectie
├── pipeline/                # Één module per stap
├── adapters/                # Boekhoud-API en mailbox (mock + abstract)
├── tenants/                 # Per-klant configuratie en leerdata
├── samples/                 # Voorbeeldfacturen
└── runs/                    # Audit-logs per run (gitignored)
```

---

## Aannames

1. Facturen worden aangeleverd als plain text voor de MVP. Andere formaten zijn gestubbed met implementatie-instructies.
2. De tenant is bekend bij aanroep via `--tenant`. LLM-classificatie bestaat maar staat achter `--auto-classify`.
3. Geen authenticatie — de operator is wie het commando uitvoert.
4. De boekhoud-API is een mock die een realistisch HTTP-contract simuleert.
5. Pipeline is sequentieel, één factuur per run.
6. Run-logs worden niet automatisch opgeruimd.
