# Mini CRM pre dvoch používateľov

Jednoduchá CRM aplikácia vo Flasku s podporou dvoch predvolených účtov, nahrávania súborov a vetvením úloh.

## Požiadavky
- Python 3.11+
- virtualenv (odporúčaný)

## Inštalácia
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Spustenie
```bash
python app.py
```
Aplikácia beží na `http://localhost:5000`.

## Prihlásenie
- `manager` / `manager123`
- `agent` / `agent123`

## Funkcie
- Prehľad posledných kontaktov a úloh na úvodnej stránke.
- Správa kontaktov s detailom a poznámkami.
- Vetvené úlohy (možnosť vybrať nadradenú úlohu) a priraďovanie k používateľom.
- Nahrávanie súborov ku kontaktom alebo konkrétnym úlohám, s históriou nahrávania.
- Jednoduchá zmena stavu úloh priamo v detaile kontaktu.
