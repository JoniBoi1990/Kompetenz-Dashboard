# Phase-0-Checkliste: Kompetenz-Dashboard einrichten

**Für:** IT-Administrator der Schule
**Geschätzte Zeit:** ca. 30–45 Minuten
**Voraussetzung:** Zugang zum Microsoft 365 Admin Center (Entra ID) mit globaler Admin-Rolle

---

## Teil A — Azure Entra ID: App registrieren

### 1. App-Registrierung anlegen

1. Öffne [https://entra.microsoft.com](https://entra.microsoft.com)
2. Navigiere zu **Anwendungen → App-Registrierungen → Neue Registrierung**
3. Felder ausfüllen:
   - **Name:** `Kompetenz-Dashboard`
   - **Unterstützte Kontotypen:** *Nur Konten in diesem Organisationsverzeichnis*
   - **Umleitungs-URI:** Plattform `Web`, URI: `https://dashboard.schule.de/auth/callback`
4. Klicke **Registrieren**

> Notiere nach der Registrierung:
> - **Anwendungs-ID (Client-ID):** `________________________________`
> - **Verzeichnis-ID (Mandanten-ID):** `________________________________`

---

### 2. Client-Secret erstellen

1. In der App-Registrierung: **Zertifikate & Geheimnisse → Neuer geheimer Clientschlüssel**
2. Beschreibung: `Dashboard VPS`, Ablauf: **24 Monate**
3. Klicke **Hinzufügen**

> Notiere den **Wert** sofort (er wird nur einmal angezeigt!):
> - **Client-Secret:** `________________________________`

---

### 3. API-Berechtigungen setzen

1. Navigiere zu **API-Berechtigungen → Berechtigung hinzufügen → Microsoft Graph**
2. Wähle **Delegierte Berechtigungen**, füge hinzu:
   - `openid`
   - `profile`
   - `email`
   - `User.Read`
   - `BookingsAppointment.ReadWrite.All` *(optional, nur für Phase 4)*
3. Klicke **Administratorzustimmung erteilen für [Schule]** → Bestätigen

---

### 4. App-Rollen definieren

1. In der App-Registrierung: **App-Rollen → App-Rolle erstellen**
2. Erste Rolle:
   - **Anzeigename:** `Lehrer`
   - **Zulässige Membertypen:** Benutzer/Gruppen
   - **Wert:** `Lehrer`
   - **Beschreibung:** `Lehrerzugang mit Schreibrecht auf Kompetenzen`
   - Aktiviert: ✅
3. Zweite Rolle (optional, zur Klarheit):
   - **Anzeigename:** `Schueler`
   - **Wert:** `Schueler`
   - **Beschreibung:** `Schülerzugang (Lesezugang)`
   - Aktiviert: ✅

---

### 5. Rollen den Benutzerkonten zuweisen

1. Navigiere zu **Unternehmensanwendungen → Kompetenz-Dashboard → Benutzer und Gruppen**
2. Klicke **Benutzer/Gruppe hinzufügen**
3. Weise zu:
   - Lehrerkonto(en) → Rolle **Lehrer**
   - Schülergruppe (oder einzelne Konten) → Rolle **Schueler** *(optional)*

> Schüler ohne explizite Rollenzuweisung werden automatisch als Schueler behandelt (Fallback über UPN-Muster).

---

### 6. Teams-Tab vorbereiten (für Phase 5, jetzt schon eintragen)

1. In der App-Registrierung: **Authentifizierung → Plattform hinzufügen → Single-Page-Application**
2. Umleitungs-URI: `https://dashboard.schule.de/`
3. Unter **Implizite Genehmigung**: beide Optionen **deaktiviert** lassen
4. Unter **Erweiterte Einstellungen → Anwendungs-ID-URI**: setze auf
   `api://dashboard.schule.de/<Client-ID-von-oben>`

---

## Teil B — VPS: Zugangsdaten übergeben

Übergib dem Entwickler (Lehrer) die folgenden Werte **sicher** (z. B. per verschlüsselter E-Mail oder direkt in die `.env`-Datei auf dem Server eintragen):

| Variable | Wert |
|----------|------|
| `AZURE_CLIENT_ID` | *(Anwendungs-ID von oben)* |
| `AZURE_CLIENT_SECRET` | *(Client-Secret von oben)* |
| `AZURE_TENANT_ID` | *(Verzeichnis-ID von oben)* |
| `DOMAIN` | `dashboard.schule.de` |

---

## Teil C — DNS-Eintrag (falls noch nicht vorhanden)

Lege einen A-Record an:

| Name | Typ | Wert |
|------|-----|------|
| `dashboard` | A | `<IP-Adresse des VPS>` |

TTL: 300 Sekunden (5 min) für schnelles Propagieren beim ersten Setup.

---

## Checkliste Zusammenfassung

- [ ] App-Registrierung erstellt
- [ ] Client-ID notiert
- [ ] Mandanten-ID notiert
- [ ] Client-Secret erstellt und notiert
- [ ] API-Berechtigungen gesetzt + Administratorzustimmung erteilt
- [ ] App-Rolle `Lehrer` erstellt
- [ ] Lehrerkonto der Rolle `Lehrer` zugewiesen
- [ ] SPA-Plattform + Anwendungs-ID-URI gesetzt (für Teams Tab)
- [ ] Zugangsdaten sicher an Entwickler übergeben
- [ ] DNS A-Record gesetzt

---

## Kontakt bei Fragen

Bei Unklarheiten zu den Entra-ID-Schritten:
→ [Microsoft-Dokumentation: App registrieren](https://learn.microsoft.com/de-de/entra/identity-platform/quickstart-register-app)

---

*Erstellt für das Kompetenz-Dashboard-Projekt. Vertraulich — enthält nach Ausfüllen Zugangsdaten.*
