# Azure AD App Registration – Kompetenz-Dashboard

**An:** IT-Verantwortliche/r
**Betreff:** Einmalige Einrichtung einer App Registration für eine schulinterne Web-App
**Aufwand:** ca. 10–15 Minuten

---

## Hintergrund

Für den internen Einsatz an der Schule wird eine Web-App betrieben, die Microsoft 365-Konten zur Anmeldung nutzt (Single Sign-On über Azure AD). Die App läuft auf einem externen Server und kommuniziert über die Microsoft Graph API mit SharePoint und den Benutzergruppen.

Es wird eine **App Registration** im Azure Active Directory der Schule benötigt. Die App selbst muss nicht im Azure Marketplace veröffentlicht werden — sie ist ausschließlich für interne Nutzer (Schüler und Lehrer der Schule) zugänglich.

---

## Schritt-für-Schritt-Anleitung

### 1. Azure Portal öffnen

[portal.azure.com](https://portal.azure.com) → mit Administrator-Konto der Schule anmelden.

---

### 2. App Registration anlegen

**Azure Active Directory → App Registrierungen → Neue Registrierung**

| Feld | Wert |
|------|------|
| Name | `Kompetenz-Dashboard` |
| Unterstützte Kontotypen | **Nur Konten in diesem Organisationsverzeichnis** (Single Tenant) |
| Umleitungs-URI (Typ: Web) | `https://bhof.uber.space/auth/callback` |

→ **Registrieren** klicken.

---

### 3. IDs notieren

Nach der Registrierung auf der Übersichtsseite:

| Bezeichnung im Portal | Weitergeben als |
|-----------------------|-----------------|
| Anwendungs-ID (Client) | `AZURE_CLIENT_ID` |
| Verzeichnis-ID (Mandant) | `AZURE_TENANT_ID` |

---

### 4. Client Secret erstellen

**Zertifikate & Geheimnisse → Neuer geheimer Clientschlüssel**

| Feld | Wert |
|------|------|
| Beschreibung | `Kompetenz-Dashboard Produktiv` |
| Ablauf | 24 Monate |

→ **Hinzufügen** klicken.

**Wichtig:** Den angezeigten **Wert** (nicht die ID) sofort kopieren — er wird danach nicht mehr vollständig angezeigt.

| Bezeichnung | Weitergeben als |
|-------------|-----------------|
| Geheimer Clientschlüssel (Wert) | `AZURE_CLIENT_SECRET` |

---

### 5. API-Berechtigungen vergeben

**API-Berechtigungen → Berechtigung hinzufügen → Microsoft Graph → Delegierte Berechtigungen**

Folgende drei Berechtigungen auswählen und hinzufügen:

| Berechtigung | Zweck |
|--------------|-------|
| `User.Read` | Angemeldeten Nutzer lesen (Name, E-Mail, Rollen) |
| `GroupMember.Read.All` | Klassenzugehörigkeit der Schüler auslesen |
| `Sites.ReadWrite.All` | Kompetenzdaten in SharePoint lesen und schreiben |

Anschließend: **Administratorzustimmung für [Schulname] erteilen** (der blaue Button mit dem Häkchen).

> Ohne diese Zustimmung müsste jeder Nutzer die Berechtigungen beim ersten Login einzeln bestätigen.

---

### 6. App-Rolle „Lehrer" definieren

Damit die App zwischen Lehrer- und Schüler-Accounts unterscheiden kann, wird eine App-Rolle benötigt.

**App-Rollen → App-Rolle erstellen**

| Feld | Wert |
|------|------|
| Anzeigename | `Lehrer` |
| Zulässige Mitgliedertypen | Benutzer/Gruppen |
| Wert | `Lehrer` |
| Beschreibung | `Lehrkräfte mit erweitertem Zugriff` |
| App-Rolle aktivieren | ✓ |

→ **Anwenden**.

---

### 7. Lehrkräfte der Rolle zuweisen

**Azure Active Directory → Unternehmensanwendungen → Kompetenz-Dashboard → Benutzer und Gruppen → Benutzer/Gruppe hinzufügen**

- Alle Lehrkräfte (einzeln oder als Gruppe) auswählen
- Rolle: `Lehrer` auswählen
- → **Zuweisen**

Schüler-Accounts werden **nicht** zugewiesen — sie erhalten automatisch eingeschränkten Zugriff.

---

## Zusammenfassung: Was bitte weitergeleitet werden soll

Nach Abschluss der Einrichtung bitte folgende drei Werte sicher übermitteln (z.B. verschlüsselte E-Mail oder persönlich):

```
AZURE_CLIENT_ID     = <Anwendungs-ID>
AZURE_TENANT_ID     = <Verzeichnis-ID>
AZURE_CLIENT_SECRET = <Geheimer Clientschlüssel, Wert>
```

---

## Sicherheitshinweise

- Die App verwendet den **OAuth 2.0 Authorization Code Flow** (MSAL Python) — der Industry-Standard für Web-Apps mit Microsoft-Anmeldung.
- Kein Passwort der Nutzer wird von der App gespeichert oder verarbeitet.
- Die Anmeldung erfolgt ausschließlich über Microsoft — die App sieht nur den Namen, die E-Mail-Adresse und die zugewiesene Rolle.
- Der Client Secret wird nur auf dem Server gespeichert und verlässt diesen nicht.
- Die App ist ausschließlich für Konten des Schulverzeichnisses zugänglich (Single Tenant).

---

## Bei Rückfragen

Die App entspricht dem Standard-MSAL-OAuth2-Flow, wie er in der offiziellen Microsoft-Dokumentation beschrieben ist:
[learn.microsoft.com/azure/active-directory/develop/quickstart-register-app](https://learn.microsoft.com/azure/active-directory/develop/quickstart-register-app)
