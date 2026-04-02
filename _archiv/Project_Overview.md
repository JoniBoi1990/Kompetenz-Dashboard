# Kompetenz-Dashboard — Projektübersicht

## Was ist das Kompetenz-Dashboard?

Das Kompetenz-Dashboard ist eine digitale Lernplattform für den Chemieunterricht. Es verbindet zwei bislang getrennte Werkzeuge — den Testgenerator und den Notenrechner — zu einer einheitlichen Oberfläche und ergänzt sie um neue Funktionen wie Kompetenzanträge und Terminbuchungen.

Schülerinnen und Schüler sehen jederzeit ihren aktuellen Lernstand. Lehrerinnen und Lehrer pflegen Bewertungen ein, generieren individuelle Tests und behalten den Überblick über alle Klassen.

---

## Rollen

### Schülerin / Schüler
Kann sich einloggen und sieht ausschließlich die eigenen Daten. Hat keinen Zugriff auf andere Schülerinnen und Schüler.

### Lehrerin / Lehrer
Hat Zugriff auf alle Klassen, kann Bewertungen eintragen, Tests generieren und Kompetenzanträge prüfen. Verwaltet außerdem die Inhalte des Dashboards (Kompetenzen, Fragen, Notenschlüssel).

---

## Kompetenzen

Das Fach Chemie ist in zwei Arten von Kompetenzen unterteilt:

### Einfache Kompetenzen (ibK)
Inhaltsbezogene Kompetenzen — konkrete Fachinhalte, die eine Schülerin oder ein Schüler beherrschen soll (z. B. „Den Rutherford'schen Streuversuch beschreiben"). Sie sind in **Themen** gruppiert (Thema 1: Atombau, Thema 2: Salze usw.) und werden binär bewertet: **nachgewiesen** oder **nicht nachgewiesen**.

### Niveau-Kompetenzen (pbK)
Prozessbezogene Kompetenzen — fächerübergreifende Fähigkeiten wie Dokumentieren, Argumentieren oder Experimentieren. Sie werden auf einer **Skala von 0–3** bewertet:

| Stufe | Bezeichnung |
|-------|-------------|
| 0 | noch nicht nachgewiesen |
| 1 | Beginner |
| 2 | Advanced |
| 3 | Expert |

Zu jeder Niveau-Kompetenz kann die Lehrkraft einen konkreten Nachweis (z. B. ein Protokoll oder ein Erklärvideo) mit Link hinterlegen.

---

## Unterrichtsstand

Die Lehrkraft legt fest, welche Kompetenzen bisher im Unterricht behandelt wurden. Dieser **Unterrichtsstand** dient als Basis für die Notenberechnung: Nur die behandelten Kompetenzen fließen in die aktuelle Note ein.

Ausnahme: Hat eine Schülerin oder ein Schüler eine Kompetenz eigenständig nachgewiesen, die noch nicht im Unterrichtsstand ist, wird auch diese angerechnet. Vorauseilendes Lernen wird also belohnt.

---

## Schüler-Dashboard

Auf der Startseite sehen Schülerinnen und Schüler:

- Ihre aktuelle **Punktzahl** relativ zum Unterrichtsstand (ohne Note — nur als Prozentwert)
- Eine vollständige Tabelle aller einfachen und Niveau-Kompetenzen mit dem jeweiligen Status
- Zu jeder Niveau-Kompetenz die Chronik aller bisherigen Nachweise

### Planungsmodus
Ein optionaler Planungsmodus erlaubt es, **Was-wäre-wenn-Szenarien** durchzuspielen: Schülerinnen und Schüler können gedanklich Kompetenzen als nachgewiesen markieren und sehen sofort, wie sich ihre Note verändern würde. Dieser Modus ist rein informativ und ändert keine echten Daten.

---

## Notenrechner

Ein eigenständiger Bereich, der die Berechnung der Note transparent macht. Die Note ergibt sich aus dem Verhältnis der erreichten Punkte zur maximal erreichbaren Punktzahl im Unterrichtsstand. Der **Notenschlüssel** (welcher Prozentsatz entspricht welcher Note) kann von der Lehrkraft angepasst werden.

---

## Testgenerator

### Aus Lehrersicht
Die Lehrkraft wählt Schülerin oder Schüler, Titel und die zu prüfenden Kompetenzen aus. Das System wählt automatisch eine passende Aufgabenstellung zu jeder Kompetenz. In einer **Vorschau** können einzelne Fragen vor dem Druck noch ausgetauscht werden. Per Knopfdruck wird ein fertig formatiertes PDF erzeugt.

### Aus Schülersicht
Schülerinnen und Schüler können über das Dashboard einen **Testwunsch** einreichen: Sie wählen die Kompetenzen, zu denen sie geprüft werden möchten (bereits nachgewiesene sind gesperrt), und bestätigen. Die Lehrkraft wird benachrichtigt, überprüft den Wunsch und erstellt daraus den Test.

---

## Kompetenzanträge

Hat eine Schülerin oder ein Schüler eine Kompetenz bereits eigenständig nachgewiesen — z. B. durch eine eigene Recherche oder ein Protokoll aus dem Unterricht — kann sie oder er direkt aus dem Dashboard heraus einen **Antrag** stellen:

- Bei **einfachen Kompetenzen**: kurze Beschreibung, wie der Nachweis erbracht wurde (nur Bezüge zur letzten Unterrichtsstunde, max. 7 Tage alt)
- Bei **Niveau-Kompetenzen**: Link zur eigenen Arbeit (z. B. OneDrive, OneNote)

Die Lehrkraft sieht alle offenen Anträge gesammelt auf einer Übersichtsseite und kann sie **annehmen** oder **ablehnen**. Bei Niveau-Kompetenzen vergibt die Lehrkraft bei Annahme das entsprechende Niveau und kann optional eine Begründung hinterlegen. Bei Ablehnung ist eine Begründung erforderlich, damit die Schülerin oder der Schüler den Antrag überarbeiten kann.

---

## Terminbuchung

Nach dem Einreichen eines Testwunsches wird die Schülerin oder der Schüler auf die Buchungsseite weitergeleitet, auf der sie oder er direkt einen Termin mit der Lehrkraft vereinbaren kann (Microsoft Bookings).

---

## Verwaltung (nur Lehrkraft)

### Kompetenzen bearbeiten
Die Liste aller Kompetenzen kann über eine Verwaltungsoberfläche gepflegt werden: neue Kompetenzen hinzufügen, bestehende bearbeiten oder entfernen, Themen zuordnen. Alternativ können Kompetenzen per CSV-Import aus den bestehenden Schulunterlagen (ibK- und pbK-Tabellen) eingelesen werden.

### Testfragen verwalten
Zu jeder einfachen Kompetenz können mehrere Aufgabenvarianten hinterlegt werden. Der Testgenerator wählt daraus zufällig aus, sodass verschiedene Schülerinnen und Schüler unterschiedliche, aber gleichwertige Fragen erhalten.

### Notenschlüssel anpassen
Die Zuordnung von Prozentwerten zu Noten kann jederzeit angepasst werden. Es stehen vorkonfigurierte Vorlagen zur Verfügung; alternativ kann ein eigener Schlüssel als CSV-Datei hochgeladen werden. Änderungen wirken sich sofort auf alle Notenberechnungen aus.

---

## Datenschutz und Zugriff

- Jede Schülerin und jeder Schüler sieht **ausschließlich die eigenen Daten**
- Der Zugang erfolgt über das **Microsoft-Schulkonto** (kein zusätzliches Passwort)
- Alle Daten liegen in der **Microsoft 365-Umgebung der Schule** (SharePoint-Listen) — es werden keine Schülerdaten auf externen Servern gespeichert
- Die Anwendung selbst läuft auf einem Schulserver (Uberspace) und ist nur über HTTPS erreichbar
