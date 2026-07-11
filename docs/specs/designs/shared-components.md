# Shared Components

Komponenten, die **beide** Seiten verwenden. Liegen unter `shared/` im Prototyp.

---

## `<Navbar active="…">`

Fixe Top-Bar:
- `sticky top-0`, height 56 px (`h-14`)
- `bg-white border-b border-gray-200`
- Container: `max-w-[1280px] mx-auto px-6`

Inhalt von links nach rechts:
1. **Logo** (verlinkt auf Projektübersicht)
2. **Drei Tabs**: Projekte / Stundensätze / Todo
3. Spacer
4. Benutzername „admin" (`text-sm text-gray-600`)
5. „Abmelden"-Button (sekundär)

### Aktiver vs. inaktiver Tab

```tsx
// aktiv
"bg-blue-50 text-blue-700 font-medium"

// inaktiv
"text-gray-600 hover:text-gray-900 hover:bg-gray-100"
```

Alle Tabs: `px-3 py-1.5 rounded-md text-sm transition`.

### Props

```ts
interface NavbarProps {
  active: "projekte" | "stundensaetze" | "todo";
}
```

Tab-Reihenfolge: **Projekte → Stundensätze → Todo**.

### Logo

Logo-Datei: `frontend/public/logo.svg` — einfach durch eine andere Datei ersetzen.

Markup: `<img src="/logo.svg" alt="Forge" className="h-7 w-auto" />`

---

## Icons

Alle Icons sind Inline-SVG-Komponenten, 13–14 px (außer wo anders angegeben).
Sie verwenden `currentColor` als Fill/Stroke und akzeptieren `{...props}`
(für `className`, Größe, etc.).

| Komponente         | Größe | Verwendung                                |
|--------------------|-------|-------------------------------------------|
| `IconCalc`         | 13    | Spalten-Header für **berechnete** Spalten |
| `IconDB`           | 13    | Spalten-Header für **ERP**-Spalten        |
| `IconPencil`       | 14    | „Bearbeiten" / editierbare Zellen        |
| `IconArchive`      | 14    | „Archivieren"-Button                     |
| `IconArrowLeft`    | 14    | Breadcrumb zurück                         |
| `IconWarning`      | 13    | Dreieck — Plan-Überschreitung             |
| `IconCheck`        | 13    | Häkchen — im Plan                         |
| `IconSearch`       | 16    | Suchfeld (aktuell nicht verwendet)        |
| `IconPlus`         | 14    | Primärer „+ Neues…"-Button                |
| `IconUser`         | 14    | Avatar-Placeholder „Nicht zugewiesen"     |
| `IconSort`         | 10×14 | Doppel-Chevron für Sortier-Header         |
| `IconFolderEmpty`  | 80    | Empty-State-Illustration                  |

### `IconSort` Props

```tsx
<IconSort dir="asc" />   // ▲ opak, ▼ transluzent
<IconSort dir="desc" />  // ▲ transluzent, ▼ opak
<IconSort dir={null} />  // beide transluzent (Idle/Hover-Hint)
```
