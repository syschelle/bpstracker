import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Activity, Euro, Globe2, HelpCircle, History, LogOut, Menu, Moon, Plus, RefreshCcw, Settings, ShieldCheck, Sun, Droplets, Thermometer, Trash2, UserCog, Wind, Zap } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, setToken } from './api';
import packageJson from '../package.json';
import type { AirSensorCurrent, AirSensorSettings, BackupInfo, CurrencyCode, CurrentValuesApiSettings, Device, DevicePurpose, DeviceType, FinanceSettings, KindleDisplaySettings, Language, Measurement, HistoryTotals, PublicDashboardSettings, RetentionSettings, SimulationSettings, Summary, UiSettings, User } from './types';

type Tab = 'dashboard' | 'history' | 'setup' | 'account' | 'help';
type TranslationKey = keyof typeof translations.de;
type Translator = (key: TranslationKey, vars?: Record<string, string | number>) => string;
type Theme = 'light' | 'dark';

const APP_VERSION = `v${packageJson.version}`;

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translator;
};

const translations = {
  de: {
    appSubtitle: 'Balkon-Photovoltaik-System Monitoring',
    loginTitle: 'Einloggen',
    installTitle: 'Ersteinrichtung',
    installHint: 'Diese Installation hat noch keinen Admin-Zugang. Lege jetzt den ersten Admin-Benutzer an. Es werden keine Benutzer oder Passwörter aus der .env übernommen.',
    username: 'Benutzername',
    password: 'Passwort',
    confirmPassword: 'Passwort wiederholen',
    installButton: 'Admin anlegen',
    installPasswordMismatch: 'Die Passwörter stimmen nicht überein.',
    installCompleteLoginNow: 'Admin wurde angelegt. Bitte melde dich jetzt an.',
    installFailed: 'Ersteinrichtung fehlgeschlagen',
    loginButton: 'Login',
    wait: 'Bitte warten…',
    loginHint: 'Melde dich mit dem eingerichteten Admin- oder Viewer-Zugang an. Initiale Zugangsdaten werden nicht mehr in der .env gespeichert.',
    loginFailed: 'Login fehlgeschlagen',
    twoFaFailed: '2FA fehlgeschlagen',
    twoFaCodeOrRecovery: '2FA-Code oder Recovery-Code',
    twoFaPlaceholder: '123456 oder ABCD-EFGH-IJKL-MNOP',
    confirm2fa: '2FA bestätigen',
    dashboard: 'Dashboard',
    history: 'Historie',
    setup: 'Setup',
    githubRepository: 'GitHub-Repository',
    githubRepositoryHint: 'Projektseite, Quellcode und Updates findest du im GitHub-Repository.',
    openGithubRepository: 'GitHub-Repository öffnen',
    help: 'Hilfe',
    helpTitle: 'Hilfe & Dokumentation',
    helpHint: 'Diese Hilfeseite zeigt die README-Dokumentation direkt in der Anwendung. Die Sprache folgt der aktuellen Sprachwahl im Header.',
    helpLoadFailed: 'Hilfedokumentation konnte nicht geladen werden.',
    account2fa: 'Admin 2FA',
    logout: 'Logout',
    menu: 'Menü',
    showMenu: 'Menü öffnen',
    hideMenu: 'Menü schließen',
    themeLight: 'Helles Theme',
    themeDark: 'Dunkles Theme',
    toggleTheme: 'Theme wechseln',
    switchLanguage: 'Sprache wechseln',
    achievementTitle: 'Energiespar-Erfolg',
    achievementGoLive: '🪖 GoLive: Super, es läuft – aber du bist noch auf der dunklen Seite der Macht!',
    achievementFirstSolar: '☀️ Erster Sonnenstrom: Auf dem Weg zum Stromimperium!',
    achievementCoffee: '☕ Kaffee-Kasse geladen: Du hast schon Geld für einen Kaffee gespart!',
    achievementCake: '🍰 Kuchen-Level erreicht: Die Sonne spendiert dir ein Stück Kuchen.',
    achievementPizza: '🍕 Pizza-Power: Deine Anlage hat eine Pizza verdient.',
    achievementMovie: '🎬 Kino-Abend: Die Sonne hat dir fast den Eintritt bezahlt.',
    achievementPlant: '🌱 Pflanzenfreund: Deine Ersparnis fühlt sich schon ziemlich grün an.',
    achievementGadget: '🔌 Technik-Bonus: Das reicht schon für ein kleines Smart-Home-Gadget.',
    achievementDinner: '🍽️ Sonnen-Dinner: Deine PV spart sich Richtung Abendessen.',
    achievementAmortization25: '🚀 Viertel geschafft: 25 % deiner Investition sind wieder drin.',
    achievementAmortization50: '⚡ Halbe Macht: 50 % Amortisation erreicht.',
    achievementAmortization75: '🛡️ Fast durch: 75 % der Investition sind zurück.',
    achievementAmortization100: '🏆 Breakeven: Deine Anlage hat sich amortisiert!',
    roleAdmin: 'Admin',
    roleViewer: 'Viewer',
    gridPower: 'Hausbezug',
    gridPowerSubtitle: '',
    gridShareGauge: 'Aktueller Anteil Netzbezug / Solar',
    gridShareGaugeSubtitle: 'zeigt, welcher Anteil der aktuellen Leistung aus Netzbezug und Solar stammt',
    gridImportShare: 'Netzbezug',
    solarShare: 'Solar',
    noPowerData: 'Keine aktuelle Leistung',
    totalCurrently: 'Aktuell gesamt',
    gridExporting: 'Netz speist aktuell ein',
    solarSocket: 'Solar',
    solarSocketSubtitle: 'aktuell an der Einspeisesteckdose',
    importedToday: 'Bezug',
    exportedToday: 'Einspeisung',
    solarToday: 'Solar',
    totalConsumption: 'Verbrauch gesamt',
    totalBalance: 'Gesamtbilanz',
    solarTodaySubtitle: 'an der Einspeisesteckdose',
    dailyBalance: 'Tagesbilanz',
    dailyCostBalance: 'Tageskostenbilanz',
    totalCostBalance: 'Gesamtkostenbilanz',
    consumptionCost: 'Verbrauchskosten',
    savings: 'Einsparung',
    savingsCalculation: 'Solar × kWh-Preis',
    investment: 'Investition',
    amortization: 'Amortisation',
    breakevenProgress: 'Breakeven-Fortschritt',
    remaining: 'Rest',
    enterInvestment: 'Investitionskosten im Setup eintragen',
    estimatedRemaining: 'Voraussichtlich verbleibend',
    untilApprox: 'ca. bis {date}',
    basedOnToday: 'auf Basis der heutigen Einsparung',
    financeCalculationHint: 'Berechnung: Verbrauchskosten = Bezug × kWh-Preis. Einsparung = Solarproduktion × kWh-Preis. Tageswerte nutzen die Tagesbilanz, Gesamtwerte nutzen dauerhaft gespeicherte Tagesaggregate und aktuelle Zählerstände.',
    deviceStatus: 'Gerätestatus',
    dashboardDeviceMeasurements: 'Gerätestatus & aktuelle Messwerte',
    refresh: 'Aktualisieren',
    name: 'Name',
    host: 'Host',
    status: 'Status',
    model: 'Modell',
    lastPoll: 'Letzter Abruf',
    error: 'Fehler',
    online: 'online',
    offline: 'offline',
    latestMeasurements: 'Aktuelle Messwerte',
    noLatestMeasurement: 'Noch keine Messung',
    time: 'Zeit',
    device: 'Gerät',
    source: 'Quelle',
    channel: 'Kanal',
    phase: 'Phase',
    power: 'Leistung',
    total: 'Gesamt',
    voltage: 'Spannung',
    current: 'Strom',
    dashboardLoadFailed: 'Dashboard konnte nicht geladen werden',
    csvDownloaded: 'CSV wurde heruntergeladen.',
    csvExport: 'CSV Export',
    powerW: 'Leistung W',
    languageSettings: 'Sprache',
    languageHint: 'Diese Einstellung speichert die Standardsprache serverseitig, z. B. für das Kindle-Display. Die Sprache im Browser kann zusätzlich im Header per Cookie geändert werden.',
    languageLabel: 'Oberflächensprache',
    german: 'Deutsch',
    english: 'English',
    saveLanguage: 'Sprache speichern',
    languageSaved: 'Sprache wurde gespeichert.',
    timezoneSettings: 'Zeitzone',
    timezoneHint: 'Die Zeitzone gilt für Zeitangaben in der Weboberfläche und für das Kindle-PNG. Sommerzeit und Winterzeit werden über die IANA-Zeitzone automatisch berücksichtigt.',
    timezoneLabel: 'Zeitzone',
    timezoneEuropeBerlin: 'Europa/Berlin',
    timezoneEuropeLondon: 'Europa/London',
    timezoneUtc: 'UTC',
    timezoneAmericaNewYork: 'Amerika/New York',
    timezoneSaved: 'Zeitzone wurde gespeichert.',
    saveTimezone: 'Zeitzone speichern',
    userAccess: 'Benutzerzugänge',
    userAccessHint: 'Der Admin wird bei der Ersteinrichtung angelegt. Ein Viewer kann optional hier erstellt oder geändert werden; er darf Dashboard und Historie sehen, aber kein Setup öffnen. Benutzernamen werden frei vergeben und im Klartext gespeichert; Passwörter werden mit Argon2id gehasht. 2FA ist nur für den Admin vorgesehen.',
    newPassword: 'Neues Passwort',
    unchangedPlaceholder: 'leer lassen = unverändert',
    saveAdmin: 'Admin speichern',
    saveViewer: 'Viewer erstellen/speichern',
    adminSaved: 'Admin wurde gespeichert.',
    viewerSaved: 'Viewer wurde gespeichert.',
    twoFaManagedInTab: '2FA verwaltest du im Reiter „Admin 2FA“.',
    viewerNoSetup: 'Der Viewer hat keinen Zugriff auf Setup und 2FA.',
    role: 'Rolle',
    twoFa: '2FA',
    active: 'Aktiv',
    yes: 'ja',
    no: 'nein',
    enabled: 'aktiv',
    disabled: 'aus',
    financeValues: 'Finanzwerte',
    financeHint: 'Diese Werte werden für Verbrauchskosten, Einsparung und Amortisation im Dashboard verwendet. Einspeisung wird nicht vergütet.',
    feedInNotPaidHint: 'Einspeisung wird mit 0 vergütet. Die Akku-Bewertung nutzt den eingespeisten Überschuss als möglichen Speicher-Nutzen.',
    enableBatteryAnalysis: 'Akku-Amortisationsberechnung aktivieren',
    batteryAnalysisDisabled: 'Akku-Amortisationsberechnung ist deaktiviert.',
    batteryDetails: 'Berechnungsdetails',
    copyBatteryDetails: 'Details kopieren',
    batteryDetailsCopied: 'Kopiert',
    batteryCost: 'Akku-Kosten',
    batteryCapacity: 'Akku-Kapazität',
    batteryAnalysis: 'Akku-Bewertung',
    batterySavingsToday: 'Potentielle Akku-Ersparnis heute',
    batteryUsableSurplusToday: 'Nutzbarer Überschuss heute',
    batteryPayback: 'Akku-Amortisation ohne offene BKW-Restkosten',
    batteryCombinedPayback: 'Akku inkl. offener BKW-Amortisation',
    batteryCombinedInvestment: 'Offene BKW-Restkosten + Akku',
    batteryOpenBps: 'Offene BKW-Restkosten',
    batteryWorthwhile: 'Akku lohnt sich rechnerisch',
    batteryNotWorthwhile: 'Akku lohnt sich rechnerisch noch nicht',
    batteryMissing: 'Akku-Preis und Kapazität im Setup eintragen.',
    batteryAssumption: 'Annahme: Einspeisung wird nicht vergütet, Akku-Wirkungsgrad 90 %, maximal ein Lade-/Entladezyklus pro Tag. Wenn das Balkonkraftwerk noch nicht amortisiert ist, werden die offenen Restkosten mit berücksichtigt.',
    financeSaved: 'Finanzwerte wurden gespeichert.',
    currency: 'Währung',
    currencyHint: 'Die Währung gilt für kWh-Preis, Investitionskosten, Einsparung und Amortisation. Es findet keine automatische Umrechnung statt.',
    currencyEur: 'Euro (€)',
    currencyUsd: 'US-Dollar ($)',
    currencyGbp: 'Pfund (£)',
    kwhPrice: 'kWh-Preis',
    investmentCost: 'Investitionskosten',
    saveFinance: 'Finanzwerte speichern',
    retentionSettings: 'Datenaufbewahrung',
    retentionHint: 'Rohmesswerte werden nur für die eingestellte Zeit behalten. Tagesaggregate bleiben dauerhaft erhalten und werden für Gesamtbilanz und Amortisation genutzt.',
    rawRetentionDays: 'Rohdaten-Aufbewahrung',
    daysUnit: 'Tage',
    dailyAggregates: 'Tagesaggregate',
    dailyAggregatesHint: 'bleiben dauerhaft erhalten',
    saveRetention: 'Aufbewahrung speichern',
    retentionSaved: 'Datenaufbewahrung wurde gespeichert.',
    retentionCurrent: 'Aktuelle Rohdaten-Aufbewahrung: {days} Tage',
    backupSettings: 'Backup',
    backupHint: 'Erstellt ein verschlüsseltes Backup mit Datenbank-Dump, Konfiguration und Backend-Daten. Das Passwort wird nur für dieses Backup verwendet und nicht gespeichert.',
    backupPassword: 'Backup-Passwort',
    backupConfirmPassword: 'Passwort wiederholen',
    createEncryptedBackup: 'Verschlüsseltes Backup erstellen',
    backupPasswordWarning: 'Ohne dieses Passwort kann das Backup nicht wiederhergestellt werden.',
    backupCreated: 'Backup wurde erstellt.',
    existingBackups: 'Vorhandene Backups',
    download: 'Download',
    deleteBackup: 'Löschen',
    backupDeleteConfirm: 'Dieses Backup wirklich löschen?',
    backupPasswordMismatch: 'Die Passwörter stimmen nicht überein.',
    backupPasswordTooShort: 'Das Backup-Passwort muss mindestens 12 Zeichen lang sein.',
    noBackups: 'Keine Backups vorhanden.',
    backupSize: 'Größe',
    created: 'Erstellt',
    simulationSettings: 'Simulation',
    simulationHint: 'Erzeugt realistische Demo-Werte ohne echte Geräte: 800-Watt-Balkon-PV und typischer 2-Personen-Haushalt mit Schwankungen.',
    enableSimulation: 'Simulation aktivieren',
    simulationSaved: 'Simulation wurde gespeichert.',
    saveSimulation: 'Simulation speichern',
    simulationWarning: 'Bei aktivierter Simulation zeigt Dashboard, Historie, Kindle-Display, Luftdaten und JSON-API simulierte Werte an. Produktivdaten werden nicht verändert.',
    matrixBanner: 'Du bist in der Matrix 😎 Simulation läuft!',
    resetValuesSettings: 'Werte zurücksetzen',
    resetValuesHint: 'Löscht alle Messwerte, Tagesaggregate und flüchtigen Wert-Caches. Geräte, Benutzer und Setup-Einstellungen bleiben erhalten.',
    resetValuesWarning: 'Achtung: Diese Aktion kann nicht rückgängig gemacht werden. Gib reset ein, um zu bestätigen.',
    resetConfirmationLabel: 'Bestätigung',
    resetValuesButton: 'Alle Werte löschen',
    resetValuesDone: 'Alle Werte wurden gelöscht.',
    resetValuesConfirmPlaceholder: 'reset',
    publicDashboardSettings: 'Öffentliches Dashboard',
    publicDashboardHint: 'Aktiviert eine separate Dashboard-Seite ohne Login. Besucher sehen nur Dashboard-Kacheln und, falls konfiguriert, aktuelle Luftdaten.',
    enablePublicDashboard: 'Öffentliches Dashboard aktivieren',
    publicDashboardSaved: 'Öffentliches Dashboard wurde gespeichert.',
    publicDashboardLink: 'Öffentlicher Dashboard-Link',
    openPublicDashboard: 'Öffentliches Dashboard öffnen',
    publicDashboardDisabledHint: 'Nur aktivieren, wenn Besucher diese Werte ohne Anmeldung sehen dürfen.',
    publicDashboardTitle: 'Öffentliches Dashboard',
    publicDashboardLoadFailed: 'Öffentliches Dashboard konnte nicht geladen werden',
    currentValuesApiSettings: 'JSON-API',
    currentValuesApiHint: 'Stellt aktuelle BPSTracker-Werte als JSON unter /api/current-values bereit. Deaktiviere diese Option, wenn du die Schnittstelle nicht nutzt.',
    enableCurrentValuesApi: 'JSON-API aktivieren',
    currentValuesApiSaved: 'JSON-API wurde gespeichert.',
    saveCurrentValuesApi: 'JSON-API speichern',
    currentValuesApiDisabledHint: 'Wenn deaktiviert, liefert /api/current-values keine Werte aus.',
    showJsonPreview: 'JSON-Vorschau anzeigen',
    refreshJsonPreview: 'JSON-Vorschau aktualisieren',
    hideJsonPreview: 'JSON-Vorschau ausblenden',
    jsonPreviewHint: 'Die Vorschau ruft die JSON-API direkt auf und zeigt die aktuelle Antwort.',
    kindleDisplaySettings: 'Kindle-Display',
    kindleDisplayHint: 'Erzeugt das Kindle-PNG unter /api/kindle/display.png. Das Bild bleibt als optional öffentlicher Cache-Endpunkt für Kindle-Abrufe verfügbar; Refresh und Meta sind Admin-only.',
    enableKindleDisplay: 'Kindle-Display aktivieren',
    kindleDisplaySaved: 'Kindle-Display wurde gespeichert.',
    saveKindleDisplay: 'Kindle-Display speichern',
    kindleDisplayDisabledHint: 'Wenn deaktiviert, wird kein neues Kindle-PNG mehr erzeugt und die API liefert deaktiviert zurück.',
    showKindlePreview: 'Kindle-Vorschau anzeigen',
    hideKindlePreview: 'Kindle-Vorschau ausblenden',
    refreshKindlePreview: 'Kindle-Vorschau aktualisieren',
    kindlePreviewHint: 'Die Vorschau zeigt das aktuelle PNG, so wie es der Kindle abrufen würde.',
    airSensorSettings: 'Luftdatensensor',
    airSensorHint: 'Optionaler LAN-Sensor unter /data.json. Öffentliche, Loopback- und Metadata-IP-Adressen sowie Redirects werden blockiert. Angezeigt werden Temperatur, Luftfeuchte, PM10 (SDS_P1) und PM2.5 (SDS_P2) nur im Header; es werden keine historischen Daten gespeichert.',
    enableAirSensor: 'Luftdatensensor aktivieren',
    airSensorHost: 'IP/Hostname des Luftdatensensors',
    airSensorSaved: 'Luftdatensensor wurde gespeichert.',
    saveAirSensor: 'Luftdatensensor speichern',
    temperature: 'Temperatur',
    humidity: 'Luftfeuchte',
    fineDust: 'Feinstaub',
    newShellyDevice: 'Neues Shelly-Gerät',
    devicePurpose: 'Zweck',
    devicePurposeAuto: 'Automatisch erkennen',
    devicePurposeGrid: 'Hausbezug / Netz',
    devicePurposeSolar: 'Solar / Einspeisung',
    devicePurposeConsumer: 'Verbraucher / Sonstiges',
    devicePurposeIgnored: 'Ignorieren',
    devicePurposeHint: 'Der Zweck steuert, ob ein Shelly als Netz-/Hausbezug, Solar-Einspeisung oder nur als Rohmessgerät gezählt wird. Mehrere Solar-/Einspeisegeräte werden summiert.',
    type: 'Typ',
    autoDetection: 'Auto-Erkennung',
    ipHostname: 'IP/Hostname',
    shellyUserOptional: 'Shelly-Benutzer optional',
    shellyPasswordOptional: 'Shelly-Passwort optional',
    pollingSeconds: 'Polling Sekunden',
    addDevice: 'Gerät hinzufügen',
    configuredDevices: 'Konfigurierte Geräte',
    polling: 'Polling',
    actions: 'Aktionen',
    all: 'alle',
    deviceSaved: 'Gerät gespeichert.',
    pollStarted: 'Poll gestartet und gespeichert.',
    deleteConfirm: 'Gerät wirklich löschen?',
    edit: 'Bearbeiten',
    saveChanges: 'Änderungen speichern',
    cancel: 'Abbrechen',
    test: 'Test',
    pollNow: 'Jetzt pollen',
    deviceUpdated: 'Gerät wurde aktualisiert.',
    clearShellyPassword: 'Shelly-Passwort löschen',
    passwordEditHint: 'Leer lassen = Shelly-Passwort bleibt unverändert.',
    editDevice: 'Gerät bearbeiten',
    ok: 'OK',
    accountRole: 'Rolle',
    twoFaStatus: '2FA',
    notActive: 'nicht aktiv',
    twoFaHint: 'Das TOTP-Secret wird verschlüsselt gespeichert. Recovery-Codes werden nur gehasht gespeichert und können einmalig statt des 2FA-Codes verwendet werden.',
    setup2fa: '2FA einrichten',
    regenerateRecoveryCodes: 'Recovery-Codes neu erzeugen',
    disable2fa: '2FA deaktivieren',
    authenticatorCode: 'Code aus Authenticator-App',
    enable2fa: '2FA aktivieren',
    twoFaEnabledMessage: '2FA wurde aktiviert. Sichere die Recovery-Codes jetzt; sie werden später nicht erneut angezeigt.',
    twoFaDisabledMessage: '2FA wurde deaktiviert. Alle Recovery-Codes wurden gelöscht.',
    recoveryRegenerated: 'Neue Recovery-Codes wurden erzeugt. Die alten Codes sind ungültig.',
    recoveryCodes: 'Recovery-Codes',
    recoveryHint: 'Speichere diese Codes sicher ab. Jeder Code ist nur einmal verwendbar und wird nicht im Klartext gespeichert.',
    reached: 'erreicht',
    lessThanOneDay: '< 1 Tag',
    days: 'Tage',
    months: 'Monate',
    years: 'Jahre',
    none: '—'
  },
  en: {
    appSubtitle: 'Balcony Photovoltaic System Monitoring',
    loginTitle: 'Sign in',
    installTitle: 'Initial setup',
    installHint: 'This installation does not have an admin account yet. Create the first admin user now. No users or passwords are imported from the .env file.',
    username: 'Username',
    password: 'Password',
    confirmPassword: 'Repeat password',
    installButton: 'Create admin',
    installPasswordMismatch: 'The passwords do not match.',
    installCompleteLoginNow: 'Admin has been created. Please sign in now.',
    installFailed: 'Initial setup failed',
    loginButton: 'Sign in',
    wait: 'Please wait…',
    loginHint: 'Sign in with the configured admin or viewer account. Initial credentials are no longer stored in the .env file.',
    loginFailed: 'Login failed',
    twoFaFailed: '2FA failed',
    twoFaCodeOrRecovery: '2FA code or recovery code',
    twoFaPlaceholder: '123456 or ABCD-EFGH-IJKL-MNOP',
    confirm2fa: 'Confirm 2FA',
    dashboard: 'Dashboard',
    history: 'History',
    setup: 'Setup',
    githubRepository: 'GitHub repository',
    githubRepositoryHint: 'Project page, source code and updates are available in the GitHub repository.',
    openGithubRepository: 'Open GitHub repository',
    help: 'Help',
    helpTitle: 'Help & documentation',
    helpHint: 'This help page shows the README documentation directly inside the application. The language follows the current language selection in the header.',
    helpLoadFailed: 'Help documentation could not be loaded.',
    account2fa: 'Admin 2FA',
    logout: 'Logout',
    menu: 'Menu',
    showMenu: 'Open menu',
    hideMenu: 'Close menu',
    themeLight: 'Light theme',
    themeDark: 'Dark theme',
    toggleTheme: 'Toggle theme',
    switchLanguage: 'Change language',
    achievementTitle: 'Solar saving achievement',
    achievementGoLive: '🪖 Go-live: great, it runs — but you are still on the dark side of the power!',
    achievementFirstSolar: '☀️ First solar power: on the way to your electricity empire!',
    achievementCoffee: '☕ Coffee fund unlocked: you have already saved enough for a coffee!',
    achievementCake: '🍰 Cake level reached: the sun is buying you a slice of cake.',
    achievementPizza: '🍕 Pizza power: your system has earned a pizza.',
    achievementMovie: '🎬 Movie night: the sun nearly paid your ticket.',
    achievementPlant: '🌱 Plant friend: your savings are looking nicely green.',
    achievementGadget: '🔌 Gadget bonus: enough for a small smart-home gadget.',
    achievementDinner: '🍽️ Solar dinner: your PV is saving its way toward dinner.',
    achievementAmortization25: '🚀 Quarter complete: 25% of your investment is back.',
    achievementAmortization50: '⚡ Half power: 50% amortization reached.',
    achievementAmortization75: '🛡️ Almost there: 75% of the investment is back.',
    achievementAmortization100: '🏆 Break-even: your system has paid for itself!',
    roleAdmin: 'Admin',
    roleViewer: 'Viewer',
    gridPower: 'Home import',
    gridPowerSubtitle: '',
    gridShareGauge: 'Current grid / solar share',
    gridShareGaugeSubtitle: 'shows how much of the current power comes from grid import and solar',
    gridImportShare: 'Grid import',
    solarShare: 'Solar',
    noPowerData: 'No current power',
    totalCurrently: 'Current total',
    gridExporting: 'Grid is currently exporting',
    solarSocket: 'Solar',
    solarSocketSubtitle: 'current at the feed-in socket',
    importedToday: 'Import',
    exportedToday: 'Export',
    solarToday: 'Solar',
    totalConsumption: 'Total consumption',
    totalBalance: 'Total energy balance',
    solarTodaySubtitle: 'at the feed-in socket',
    dailyBalance: 'Daily energy balance',
    dailyCostBalance: 'Daily cost balance',
    totalCostBalance: 'Total cost balance',
    consumptionCost: 'Consumption cost',
    savings: 'Savings',
    savingsCalculation: 'Solar × kWh price',
    investment: 'Investment',
    amortization: 'Amortization',
    breakevenProgress: 'Breakeven progress',
    remaining: 'Remaining',
    enterInvestment: 'Enter investment costs in Setup',
    estimatedRemaining: 'Estimated remaining',
    untilApprox: 'approx. until {date}',
    basedOnToday: 'based on today’s savings',
    financeCalculationHint: 'Calculation: consumption cost = import × kWh price. Savings = solar production × kWh price. Daily values use the daily balance; total values use permanently stored daily aggregates and current counters.',
    deviceStatus: 'Device status',
    dashboardDeviceMeasurements: 'Device status & latest measurements',
    refresh: 'Refresh',
    name: 'Name',
    host: 'Host',
    status: 'Status',
    model: 'Model',
    lastPoll: 'Last poll',
    error: 'Error',
    online: 'online',
    offline: 'offline',
    latestMeasurements: 'Latest measurements',
    noLatestMeasurement: 'No measurement yet',
    time: 'Time',
    device: 'Device',
    source: 'Source',
    channel: 'Channel',
    phase: 'Phase',
    power: 'Power',
    total: 'Total',
    voltage: 'Voltage',
    current: 'Current',
    dashboardLoadFailed: 'Dashboard could not be loaded',
    csvDownloaded: 'CSV has been downloaded.',
    csvExport: 'CSV export',
    powerW: 'Power W',
    languageSettings: 'Language',
    languageHint: 'This setting applies to the entire web interface. German is the default language.',
    languageLabel: 'Interface language',
    german: 'Deutsch',
    english: 'English',
    saveLanguage: 'Save language',
    languageSaved: 'Language has been saved.',
    timezoneSettings: 'Time zone',
    timezoneHint: 'The time zone is used for time values in the web interface and for the Kindle PNG. Daylight saving time / winter time is handled automatically by the IANA time zone.',
    timezoneLabel: 'Time zone',
    timezoneEuropeBerlin: 'Europe/Berlin',
    timezoneEuropeLondon: 'Europe/London',
    timezoneUtc: 'UTC',
    timezoneAmericaNewYork: 'America/New York',
    timezoneSaved: 'Time zone has been saved.',
    saveTimezone: 'Save time zone',
    userAccess: 'User access',
    userAccessHint: 'The admin is created during initial setup. A viewer can optionally be created or changed here; the viewer may see Dashboard and History, but cannot open Setup. Usernames are freely configurable and stored in plain text; passwords are hashed with Argon2id. 2FA is intended only for the admin.',
    newPassword: 'New password',
    unchangedPlaceholder: 'leave empty = unchanged',
    saveAdmin: 'Save admin',
    saveViewer: 'Create/save viewer',
    adminSaved: 'Admin has been saved.',
    viewerSaved: 'Viewer has been saved.',
    twoFaManagedInTab: 'Manage 2FA in the “Admin 2FA” tab.',
    viewerNoSetup: 'The viewer has no access to Setup or 2FA.',
    role: 'Role',
    twoFa: '2FA',
    active: 'Active',
    yes: 'yes',
    no: 'no',
    enabled: 'enabled',
    disabled: 'off',
    financeValues: 'Financial values',
    financeHint: 'These values are used for consumption costs, savings and amortization in the dashboard. Grid export is not compensated.',
    feedInNotPaidHint: 'Grid export is valued at 0. The battery analysis uses exported surplus as potential battery benefit.',
    enableBatteryAnalysis: 'Enable battery amortization calculation',
    batteryAnalysisDisabled: 'Battery amortization calculation is disabled.',
    batteryDetails: 'Calculation details',
    copyBatteryDetails: 'Copy details',
    batteryDetailsCopied: 'Copied',
    batteryCost: 'Battery cost',
    batteryCapacity: 'Battery capacity',
    batteryAnalysis: 'Battery analysis',
    batterySavingsToday: 'Potential battery savings today',
    batteryUsableSurplusToday: 'Usable surplus today',
    batteryPayback: 'Battery payback without open BPS remainder',
    batteryCombinedPayback: 'Battery incl. open BPS amortization',
    batteryCombinedInvestment: 'Open BPS remainder + battery',
    batteryOpenBps: 'Open BPS remainder',
    batteryWorthwhile: 'Battery appears worthwhile',
    batteryNotWorthwhile: 'Battery does not appear worthwhile yet',
    batteryMissing: 'Enter battery price and capacity in setup.',
    batteryAssumption: 'Assumption: grid export is unpaid, battery round-trip efficiency 90%, maximum one charge/discharge cycle per day. If the balcony PV system has not paid for itself yet, the open remainder is included.',
    financeSaved: 'Financial values have been saved.',
    currency: 'Currency',
    currencyHint: 'The currency is used for kWh price, investment costs, savings and amortization. No automatic conversion is performed.',
    currencyEur: 'Euro (€)',
    currencyUsd: 'US dollar ($)',
    currencyGbp: 'Pound (£)',
    kwhPrice: 'kWh price',
    investmentCost: 'Investment costs',
    saveFinance: 'Save financial values',
    retentionSettings: 'Data retention',
    retentionHint: 'Raw measurements are kept only for the configured period. Daily aggregates are kept permanently and are used for total balance and amortization.',
    rawRetentionDays: 'Raw data retention',
    daysUnit: 'days',
    dailyAggregates: 'Daily aggregates',
    dailyAggregatesHint: 'kept permanently',
    saveRetention: 'Save retention',
    retentionSaved: 'Data retention has been saved.',
    retentionCurrent: 'Current raw data retention: {days} days',
    backupSettings: 'Backup',
    backupHint: 'Creates an encrypted backup with database dump, configuration and backend data. The password is used only for this backup and is not stored.',
    backupPassword: 'Backup password',
    backupConfirmPassword: 'Repeat password',
    createEncryptedBackup: 'Create encrypted backup',
    backupPasswordWarning: 'Without this password the backup cannot be restored.',
    backupCreated: 'Backup has been created.',
    existingBackups: 'Existing backups',
    download: 'Download',
    deleteBackup: 'Delete',
    backupDeleteConfirm: 'Really delete this backup?',
    backupPasswordMismatch: 'The passwords do not match.',
    backupPasswordTooShort: 'The backup password must be at least 12 characters long.',
    noBackups: 'No backups available.',
    backupSize: 'Size',
    created: 'Created',
    simulationSettings: 'Simulation',
    simulationHint: 'Generates realistic demo values without real devices: 800 W balcony PV and a typical 2-person household with fluctuations.',
    enableSimulation: 'Enable simulation',
    simulationSaved: 'Simulation has been saved.',
    saveSimulation: 'Save simulation',
    simulationWarning: 'When simulation is enabled, dashboard, history, Kindle display, air data and JSON API show simulated values. Production data is not changed.',
    matrixBanner: 'You are in the Matrix 😎 Simulation is running!',
    resetValuesSettings: 'Reset values',
    resetValuesHint: 'Deletes all measurements, daily aggregates and volatile value caches. Devices, users and setup settings are kept.',
    resetValuesWarning: 'Warning: This action cannot be undone. Type reset to confirm.',
    resetConfirmationLabel: 'Confirmation',
    resetValuesButton: 'Delete all values',
    resetValuesDone: 'All values have been deleted.',
    resetValuesConfirmPlaceholder: 'reset',
    publicDashboardSettings: 'Public dashboard',
    publicDashboardHint: 'Enables a separate dashboard page without login. Visitors only see the dashboard cards and, if configured, current air sensor values.',
    enablePublicDashboard: 'Enable public dashboard',
    publicDashboardSaved: 'Public dashboard has been saved.',
    publicDashboardLink: 'Public dashboard link',
    openPublicDashboard: 'Open public dashboard',
    publicDashboardDisabledHint: 'Only enable this if visitors may see these values without signing in.',
    publicDashboardTitle: 'Public dashboard',
    publicDashboardLoadFailed: 'Public dashboard could not be loaded',
    currentValuesApiSettings: 'JSON API',
    currentValuesApiHint: 'Provides current BPSTracker values as JSON at /api/current-values. Disable this option if you do not use the endpoint.',
    enableCurrentValuesApi: 'Enable JSON API',
    currentValuesApiSaved: 'JSON API has been saved.',
    saveCurrentValuesApi: 'Save JSON API',
    currentValuesApiDisabledHint: 'When disabled, /api/current-values does not return values.',
    showJsonPreview: 'Show JSON preview',
    refreshJsonPreview: 'Refresh JSON preview',
    hideJsonPreview: 'Hide JSON preview',
    jsonPreviewHint: 'The preview calls the JSON API directly and shows the current response.',
    kindleDisplaySettings: 'Kindle display',
    kindleDisplayHint: 'Generates the Kindle PNG at /api/kindle/display.png. The image remains an optional public cache endpoint for Kindle fetches; refresh and meta are admin-only.',
    enableKindleDisplay: 'Enable Kindle display',
    kindleDisplaySaved: 'Kindle display has been saved.',
    saveKindleDisplay: 'Save Kindle display',
    kindleDisplayDisabledHint: 'When disabled, no new Kindle PNG is generated and the API reports that the display is disabled.',
    showKindlePreview: 'Show Kindle preview',
    hideKindlePreview: 'Hide Kindle preview',
    refreshKindlePreview: 'Refresh Kindle preview',
    kindlePreviewHint: 'The preview shows the current PNG exactly as the Kindle would fetch it.',
    airSensorSettings: 'Air data sensor',
    airSensorHint: 'Optional sensor at /data.json. Temperature, humidity, PM10 (SDS_P1) and PM2.5 (SDS_P2) are shown only in the header; no history is stored.',
    enableAirSensor: 'Enable air data sensor',
    airSensorHost: 'Air sensor IP/hostname',
    airSensorSaved: 'Air data sensor has been saved.',
    saveAirSensor: 'Save air data sensor',
    temperature: 'Temperature',
    humidity: 'Humidity',
    fineDust: 'Particulate matter',
    newShellyDevice: 'New Shelly device',
    devicePurpose: 'Purpose',
    devicePurposeAuto: 'Auto detect',
    devicePurposeGrid: 'Home/grid import',
    devicePurposeSolar: 'Solar/feed-in',
    devicePurposeConsumer: 'Consumer/other',
    devicePurposeIgnored: 'Ignore',
    devicePurposeHint: 'The purpose controls whether a Shelly is counted as grid/home import, solar feed-in, or only as a raw measuring device. Multiple solar/feed-in devices are summed.',
    type: 'Type',
    autoDetection: 'Auto detection',
    ipHostname: 'IP/hostname',
    shellyUserOptional: 'Shelly username optional',
    shellyPasswordOptional: 'Shelly password optional',
    pollingSeconds: 'Polling seconds',
    addDevice: 'Add device',
    configuredDevices: 'Configured devices',
    polling: 'Polling',
    actions: 'Actions',
    all: 'all',
    deviceSaved: 'Device has been saved.',
    pollStarted: 'Poll started and saved.',
    deleteConfirm: 'Really delete this device?',
    edit: 'Edit',
    saveChanges: 'Save changes',
    cancel: 'Cancel',
    test: 'Test',
    pollNow: 'Poll now',
    deviceUpdated: 'Device has been updated.',
    clearShellyPassword: 'Clear Shelly password',
    passwordEditHint: 'Leave empty = Shelly password remains unchanged.',
    editDevice: 'Edit device',
    ok: 'OK',
    accountRole: 'Role',
    twoFaStatus: '2FA',
    notActive: 'not active',
    twoFaHint: 'The TOTP secret is stored encrypted. Recovery codes are stored only as hashes and can be used once instead of the 2FA code.',
    setup2fa: 'Set up 2FA',
    regenerateRecoveryCodes: 'Regenerate recovery codes',
    disable2fa: 'Disable 2FA',
    authenticatorCode: 'Code from authenticator app',
    enable2fa: 'Enable 2FA',
    twoFaEnabledMessage: '2FA has been enabled. Save the recovery codes now; they will not be shown again later.',
    twoFaDisabledMessage: '2FA has been disabled. All recovery codes have been deleted.',
    recoveryRegenerated: 'New recovery codes have been generated. Old codes are invalid.',
    recoveryCodes: 'Recovery codes',
    recoveryHint: 'Store these codes safely. Each code can be used only once and is not stored in plain text.',
    reached: 'reached',
    lessThanOneDay: '< 1 day',
    days: 'days',
    months: 'months',
    years: 'years',
    none: '—'
  }
} as const;

const I18nContext = createContext<I18nContextValue | null>(null);

function translate(language: Language, key: TranslationKey, vars?: Record<string, string | number>): string {
  let value: string = translations[language]?.[key] || translations.de[key] || String(key);
  if (vars) {
    for (const [name, replacement] of Object.entries(vars)) {
      value = value.split(`{${name}}`).join(String(replacement));
    }
  }
  return value;
}

function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error('I18nContext is missing');
  return value;
}

function readStoredLanguage(): Language {
  const value = readCookie('bpstracker-language') || localStorage.getItem('bpstracker-language');
  return value === 'en' ? 'en' : 'de';
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const found = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : null;
}

function writeCookie(name: string, value: string, maxAgeDays = 365): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; Max-Age=${maxAgeDays * 24 * 60 * 60}; Path=/; SameSite=Lax`;
}

function readStoredTheme(): Theme {
  const value = readCookie('bpstracker-theme') || localStorage.getItem('bpstracker-theme');
  if (value === 'dark' || value === 'light') return value;
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

function localeFor(language: Language): string {
  return language === 'en' ? 'en-US' : 'de-DE';
}

type DeviceForm = {
  name: string;
  device_type: DeviceType;
  purpose: DevicePurpose;
  host: string;
  username: string;
  password: string;
  is_active: boolean;
  poll_interval_seconds: number;
  channel: number | '';
};

const emptyDevice: DeviceForm = {
  name: '',
  device_type: 'auto',
  purpose: 'auto',
  host: '',
  username: '',
  password: '',
  is_active: true,
  poll_interval_seconds: 30,
  channel: ''
};

function deviceToForm(device: Device): DeviceForm {
  return {
    name: device.name,
    device_type: device.device_type,
    purpose: device.purpose || 'auto',
    host: device.host,
    username: device.username || '',
    password: '',
    is_active: device.is_active,
    poll_interval_seconds: device.poll_interval_seconds,
    channel: device.channel ?? ''
  };
}

function devicePayloadFromForm(form: DeviceForm) {
  return {
    name: form.name.trim(),
    device_type: form.device_type,
    purpose: form.purpose,
    host: form.host.trim(),
    username: form.username.trim() || null,
    password: form.password.trim() || null,
    is_active: form.is_active,
    poll_interval_seconds: Number(form.poll_interval_seconds) || 30,
    channel: form.channel === '' ? null : Number(form.channel)
  };
}

function fmtW(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  const absValue = Math.abs(value);
  if (absValue >= 1000) {
    return `${(value / 1000).toLocaleString(localeFor(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kW`;
  }
  return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 0 })} W`;
}

function fmtKwh(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 2 })} kWh`;
}

function sumKwhValues(...values: Array<number | null | undefined>): number | null {
  const configuredValues = values.filter((value): value is number => value !== null && value !== undefined);
  if (!configuredValues.length) return null;
  return configuredValues.reduce((sum, value) => sum + value, 0);
}

function fmtBytes(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toLocaleString(localeFor(language), { maximumFractionDigits: index === 0 ? 0 : 1 })} ${units[index]}`;
}

function fmtDate(value?: string | null, language: Language = 'de'): string {
  if (!value) return translations[language].none;
  return new Date(value).toLocaleString(localeFor(language));
}

function normalizeCurrency(currency?: string | null): CurrencyCode {
  return currency === 'USD' || currency === 'GBP' || currency === 'EUR' ? currency : 'EUR';
}

function currencySymbol(currency?: string | null): string {
  const code = normalizeCurrency(currency);
  return code === 'USD' ? '$' : code === 'GBP' ? '£' : '€';
}

function fmtCurrency(value?: number | null, language: Language = 'de', currency?: string | null): string {
  if (value === null || value === undefined) return translations[language].none;
  return `${value.toLocaleString(localeFor(language), { style: 'currency', currency: normalizeCurrency(currency), maximumFractionDigits: 2 })}`;
}

function fmtPercent(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 1 })} %`;
}

function fmtTemperature(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 1 })} °C`;
}

function fmtMicrograms(value?: number | null, language: Language = 'de'): string {
  if (value === null || value === undefined) return translations[language].none;
  return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 2 })} µg/m³`;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}


type AchievementMetric = 'system_online' | 'solar_total_kwh' | 'savings_total_eur' | 'breakeven_progress_percent';

type AchievementDefinition = {
  id: string;
  metric: AchievementMetric;
  threshold: number;
  translationKey: TranslationKey;
  image: string;
};

const ACHIEVEMENTS: AchievementDefinition[] = [
  { id: 'go-live', image: '/achievement-badges/go-live.svg', metric: 'system_online', threshold: 1, translationKey: 'achievementGoLive' },
  { id: 'first-solar', image: '/achievement-badges/first-solar.svg', metric: 'solar_total_kwh', threshold: 0, translationKey: 'achievementFirstSolar' },
  { id: 'coffee', image: '/achievement-badges/coffee.svg', metric: 'savings_total_eur', threshold: 3, translationKey: 'achievementCoffee' },
  { id: 'cake', image: '/achievement-badges/cake.svg', metric: 'savings_total_eur', threshold: 8, translationKey: 'achievementCake' },
  { id: 'pizza', image: '/achievement-badges/pizza.svg', metric: 'savings_total_eur', threshold: 15, translationKey: 'achievementPizza' },
  { id: 'movie', image: '/achievement-badges/movie.svg', metric: 'savings_total_eur', threshold: 25, translationKey: 'achievementMovie' },
  { id: 'plant', image: '/achievement-badges/plant.svg', metric: 'savings_total_eur', threshold: 40, translationKey: 'achievementPlant' },
  { id: 'gadget', image: '/achievement-badges/gadget.svg', metric: 'savings_total_eur', threshold: 75, translationKey: 'achievementGadget' },
  { id: 'dinner', image: '/achievement-badges/dinner.svg', metric: 'savings_total_eur', threshold: 120, translationKey: 'achievementDinner' },
  { id: 'amortization-25', image: '/achievement-badges/amortization-25.svg', metric: 'breakeven_progress_percent', threshold: 25, translationKey: 'achievementAmortization25' },
  { id: 'amortization-50', image: '/achievement-badges/amortization-50.svg', metric: 'breakeven_progress_percent', threshold: 50, translationKey: 'achievementAmortization50' },
  { id: 'amortization-75', image: '/achievement-badges/amortization-75.svg', metric: 'breakeven_progress_percent', threshold: 75, translationKey: 'achievementAmortization75' },
  { id: 'amortization-100', image: '/achievement-badges/amortization-100.svg', metric: 'breakeven_progress_percent', threshold: 100, translationKey: 'achievementAmortization100' },
];

const ACHIEVEMENT_VISIBLE_DAYS = 7;
const ACHIEVEMENT_STORAGE_KEY = 'bpstracker-achievements';

type StoredAchievement = {
  id: string;
  unlockedAt: string;
};

type AchievementInput = {
  systemOnline?: boolean;
  totalSavings?: number | null;
  totalSolarKwh?: number | null;
  breakevenProgressPercent?: number | null;
};

function readStoredAchievements(): StoredAchievement[] {
  try {
    const raw = localStorage.getItem(ACHIEVEMENT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(item => typeof item?.id === 'string' && typeof item?.unlockedAt === 'string') : [];
  } catch {
    return [];
  }
}

function writeStoredAchievements(items: StoredAchievement[]): void {
  localStorage.setItem(ACHIEVEMENT_STORAGE_KEY, JSON.stringify(items));
}

function achievementMetricReached(achievement: AchievementDefinition, input: AchievementInput): boolean {
  switch (achievement.metric) {
    case 'system_online':
      return input.systemOnline === true;
    case 'solar_total_kwh':
      // Das erste Solar-Badge darf erst erscheinen, wenn das konfigurierte Balkonkraftwerk
      // tatsächlich Solarenergie geliefert hat. Ein frisches System mit 0 kWh bekommt nur GoLive.
      return typeof input.totalSolarKwh === 'number' && Number.isFinite(input.totalSolarKwh) && input.totalSolarKwh > achievement.threshold;
    case 'savings_total_eur':
      return typeof input.totalSavings === 'number' && Number.isFinite(input.totalSavings) && input.totalSavings >= achievement.threshold;
    case 'breakeven_progress_percent':
      return typeof input.breakevenProgressPercent === 'number' && Number.isFinite(input.breakevenProgressPercent) && input.breakevenProgressPercent >= achievement.threshold;
  }
}

function updateAchievements(input: AchievementInput): StoredAchievement[] {
  const now = new Date();
  const existing = readStoredAchievements();
  const byId = new Map(existing.map(item => [item.id, item]));
  for (const achievement of ACHIEVEMENTS) {
    if (!byId.has(achievement.id) && achievementMetricReached(achievement, input)) {
      byId.set(achievement.id, { id: achievement.id, unlockedAt: now.toISOString() });
    }
  }
  const next = Array.from(byId.values()).filter(item => {
    const unlocked = new Date(item.unlockedAt).getTime();
    return Number.isFinite(unlocked) && now.getTime() - unlocked <= ACHIEVEMENT_VISIBLE_DAYS * 24 * 60 * 60 * 1000;
  });
  writeStoredAchievements(next);
  return next;
}

function achievementDefinition(id: string): AchievementDefinition | undefined {
  return ACHIEVEMENTS.find(achievement => achievement.id === id);
}


function fmtDays(value: number | null | undefined, language: Language, t: Translator): string {
  if (value === null || value === undefined) return translations[language].none;
  if (value <= 0) return t('reached');
  if (value < 1) return t('lessThanOneDay');
  if (value < 60) return `${value.toLocaleString(localeFor(language), { maximumFractionDigits: 0 })} ${t('days')}`;
  const months = value / 30.4375;
  if (months < 24) return `${months.toLocaleString(localeFor(language), { maximumFractionDigits: 1 })} ${t('months')}`;
  const years = value / 365.25;
  return `${years.toLocaleString(localeFor(language), { maximumFractionDigits: 1 })} ${t('years')}`;
}

function isAdmin(user: User | null): boolean {
  return user?.role === 'admin';
}

function SimulationBanner() {
  const { t } = useI18n();
  const [enabled, setEnabled] = useState(false);

  async function load() {
    try {
      const settings = await api.simulationSettings();
      setEnabled(settings.enabled);
    } catch {
      setEnabled(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(timer);
  }, []);

  if (!enabled) return null;
  return <div className="simulation-banner">{t('matrixBanner')}</div>;
}

export default function App() {
  const isPublicDashboardRoute = typeof window !== 'undefined' && window.location.pathname.replace(/\/$/, '') === '/public/dashboard';
  const [language, setLanguageState] = useState<Language>(readStoredLanguage);
  const [theme, setTheme] = useState<Theme>(readStoredTheme);
  const [user, setUser] = useState<User | null>(null);
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [installRequired, setInstallRequired] = useState<boolean | null>(null);
  const [installUsername, setInstallUsername] = useState('');
  const [installPassword, setInstallPassword] = useState('');
  const [installPasswordConfirm, setInstallPasswordConfirm] = useState('');
  const [challenge, setChallenge] = useState<string | null>(null);
  const [twoFaCode, setTwoFaCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<Tab>('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);

  const setLanguage = useCallback((nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    localStorage.setItem('bpstracker-language', nextLanguage);
    writeCookie('bpstracker-language', nextLanguage);
    document.documentElement.lang = nextLanguage;
  }, []);

  const t = useCallback<Translator>((key, vars) => translate(language, key, vars), [language]);
  const i18n = useMemo<I18nContextValue>(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  if (isPublicDashboardRoute) {
    return (
      <I18nContext.Provider value={i18n}>
        <div className="public-dashboard-page">
          <header className="public-dashboard-header">
            <div>
              <h1>{t('publicDashboardTitle')}</h1>
              <p>BPSTracker {APP_VERSION}</p>
            </div>
            <button
              className="language-switch"
              onClick={() => setLanguage(language === 'de' ? 'en' : 'de')}
              aria-label={t('switchLanguage')}
              title={t('switchLanguage')}
            >
              {language === 'de' ? 'EN' : 'DE'}
            </button>
          </header>
          <PublicDashboard />
        </div>
      </I18nContext.Provider>
    );
  }

  const toggleTheme = useCallback(() => {
    setTheme(current => current === 'dark' ? 'light' : 'dark');
  }, []);

  const loadCurrentUserAndLanguage = useCallback(async () => {
    const [currentUser, ui] = await Promise.all([api.me(), api.uiSettings().catch(() => null)]);
    setUser(currentUser);
    const cookieLanguage = readCookie('bpstracker-language');
    if ((cookieLanguage === 'de' || cookieLanguage === 'en')) {
      setLanguage(cookieLanguage);
    } else if (ui?.language) {
      setLanguage(ui.language);
    }
  }, [setLanguage]);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('bpstracker-theme', theme);
    writeCookie('bpstracker-theme', theme);
  }, [theme]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 980px)');
    const handleResponsiveMenu = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) setMenuOpen(false);
    };

    handleResponsiveMenu(mediaQuery);
    mediaQuery.addEventListener('change', handleResponsiveMenu);
    return () => mediaQuery.removeEventListener('change', handleResponsiveMenu);
  }, []);

  useEffect(() => {
    localStorage.setItem('bpstracker-menu-open', String(menuOpen));
  }, [menuOpen]);

  useEffect(() => {
    api.installStatus()
      .then(status => {
        setInstallRequired(status.install_required);
        if (status.install_required) {
          setToken(null);
          setUser(null);
        }
      })
      .catch(() => setInstallRequired(false));
  }, []);

  useEffect(() => {
    if (installRequired !== false) return;
    loadCurrentUserAndLanguage().catch(() => setToken(null));
  }, [installRequired, loadCurrentUserAndLanguage]);

  useEffect(() => {
    if (!isAdmin(user) && (tab === 'setup' || tab === 'account')) setTab('dashboard');
  }, [tab, user]);

  async function handleInstall() {
    setError(null);
    setInfo(null);
    if (installPassword !== installPasswordConfirm) {
      setError(t('installPasswordMismatch'));
      return;
    }
    setLoading(true);
    try {
      await api.installAdmin(installUsername, installPassword, installPasswordConfirm);
      setInstallRequired(false);
      setLoginUsername(installUsername);
      setLoginPassword('');
      setInstallPassword('');
      setInstallPasswordConfirm('');
      setInfo(t('installCompleteLoginNow'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('installFailed'));
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin() {
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const response = await api.login(loginUsername, loginPassword);
      if (response.requires_2fa && response.challenge_token) {
        setChallenge(response.challenge_token);
      } else {
        setToken(null);
        await loadCurrentUserAndLanguage();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loginFailed'));
    } finally {
      setLoading(false);
    }
  }

  async function handle2faVerify() {
    if (!challenge) return;
    setError(null);
    setLoading(true);
    try {
      await api.verify2fa(challenge, twoFaCode);
      setToken(null);
      await loadCurrentUserAndLanguage();
      setChallenge(null);
      setTwoFaCode('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('twoFaFailed'));
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    void api.logout().catch(() => undefined);
    setToken(null);
    setUser(null);
    setChallenge(null);
    setLoginPassword('');
    setInfo(null);
    setMenuOpen(false);
  }

  function goTo(nextTab: Tab) {
    setTab(nextTab);
    setMenuOpen(false);
  }

  return (
    <I18nContext.Provider value={i18n}>
      {!user ? (
        <main className="login-page">
          <section className="login-card">
            <div className="login-top">
              <div>
                <div className="brand"><Zap /> BPSTracker</div>
                <div className="brand-subtitle">{t('appSubtitle')} · <span className="app-version">{APP_VERSION}</span></div>
              </div>
              <button className="icon-button theme-toggle" onClick={toggleTheme} aria-label={t('toggleTheme')} title={theme === 'dark' ? t('themeLight') : t('themeDark')}>
                {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
              </button>
            </div>
            {installRequired === null ? (
              <>
                <h1>{t('wait')}</h1>
              </>
            ) : installRequired ? (
              <>
                <h1>{t('installTitle')}</h1>
                {error && <div className="error">{error}</div>}
                <p className="hint">{t('installHint')}</p>
                <label>{t('username')}<input autoFocus value={installUsername} onChange={e => setInstallUsername(e.target.value)} /></label>
                <label>{t('password')}<input type="password" value={installPassword} onChange={e => setInstallPassword(e.target.value)} /></label>
                <label>{t('confirmPassword')}<input type="password" value={installPasswordConfirm} onChange={e => setInstallPasswordConfirm(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void handleInstall(); }} /></label>
                <button onClick={handleInstall} disabled={loading}>{loading ? t('wait') : t('installButton')}</button>
              </>
            ) : (
              <>
                <h1>{t('loginTitle')}</h1>
                {error && <div className="error">{error}</div>}
                {info && <div className="info">{info}</div>}
                {!challenge ? (
                  <>
                    <label>{t('username')}<input autoFocus value={loginUsername} onChange={e => setLoginUsername(e.target.value)} /></label>
                    <label>{t('password')}<input type="password" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void handleLogin(); }} /></label>
                    <button onClick={handleLogin} disabled={loading}>{loading ? t('wait') : t('loginButton')}</button>
                    <p className="hint">{t('loginHint')}</p>
                  </>
                ) : (
                  <>
                    <label>{t('twoFaCodeOrRecovery')}<input autoFocus value={twoFaCode} onChange={e => setTwoFaCode(e.target.value)} placeholder={t('twoFaPlaceholder')} onKeyDown={e => { if (e.key === 'Enter') void handle2faVerify(); }} /></label>
                    <button onClick={handle2faVerify} disabled={loading}>{t('confirm2fa')}</button>
                  </>
                )}
              </>
            )}
          </section>
        </main>
      ) : (
        <main className={`app-shell ${menuOpen ? 'menu-open' : 'menu-closed'}`}>
          {menuOpen && <button className="menu-backdrop" aria-label={t('hideMenu')} onClick={() => setMenuOpen(false)} />}
          <aside className="side-nav" aria-hidden={!menuOpen}>
            <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => goTo('dashboard')}><Activity /> {t('dashboard')}</button>
            <button className={tab === 'history' ? 'active' : ''} onClick={() => goTo('history')}><History /> {t('history')}</button>
            {isAdmin(user) && <button className={tab === 'setup' ? 'active' : ''} onClick={() => goTo('setup')}><Settings /> {t('setup')}</button>}
            {isAdmin(user) && <button className={tab === 'account' ? 'active' : ''} onClick={() => goTo('account')}><ShieldCheck /> {t('account2fa')}</button>}
            <button className={tab === 'help' ? 'active' : ''} onClick={() => goTo('help')}><HelpCircle /> {t('help')}</button>
            <button onClick={logout}><LogOut /> {t('logout')}</button>
            <div className="side-nav-version">BPSTracker {APP_VERSION}</div>
          </aside>
          <section className="content">
            <header>
              <div className="header-title">
                <button className="icon-button menu-toggle" onClick={() => setMenuOpen(open => !open)} aria-label={menuOpen ? t('hideMenu') : t('showMenu')} title={menuOpen ? t('hideMenu') : t('showMenu')}>
                  <Menu size={22} />
                </button>
                <div className="header-meta">
                  <h1>{tabTitle(tab, t)}</h1>
                  <p>{user.username} · {user.role === 'admin' ? t('roleAdmin') : t('roleViewer')}</p>
                </div>
              </div>
              <div className="header-actions">
                <AchievementHeader />
                <AirSensorHeader />
                <button
                  className="language-switch"
                  onClick={() => setLanguage(language === 'de' ? 'en' : 'de')}
                  aria-label={t('switchLanguage')}
                  title={t('switchLanguage')}
                >
                  {language === 'de' ? 'EN' : 'DE'}
                </button>
                <button className="icon-button theme-toggle" onClick={toggleTheme} aria-label={t('toggleTheme')} title={theme === 'dark' ? t('themeLight') : t('themeDark')}>
                  {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
                </button>
                <div className="header-brand">
                  <div className="brand"><Zap /> BPSTracker</div>
                  <div className="brand-subtitle">{t('appSubtitle')} · <span className="app-version">{APP_VERSION}</span></div>
                </div>
              </div>
            </header>
            <SimulationBanner />
            {tab === 'dashboard' && <Dashboard />}
            {tab === 'history' && <HistoryView />}
            {tab === 'setup' && isAdmin(user) && <SetupView onCurrentUserChange={setUser} />}
            {tab === 'account' && isAdmin(user) && <AccountView user={user} onUser={setUser} />}
            {tab === 'help' && <HelpView />}
          </section>
        </main>
      )}
    </I18nContext.Provider>
  );
}


function AchievementHeader() {
  const { t } = useI18n();
  const [achievement, setAchievement] = useState<StoredAchievement | null>(null);

  async function load() {
    try {
      const summary = await api.summary();
      const visible = updateAchievements({
        systemOnline: true,
        totalSavings: summary.savings_total_eur,
        totalSolarKwh: summary.solar_total_kwh,
        breakevenProgressPercent: summary.breakeven_progress_percent,
      });
      setAchievement(visible.length ? visible[visible.length - 1] : null);
    } catch {
      const visible = updateAchievements({ systemOnline: false });
      setAchievement(visible.length ? visible[visible.length - 1] : null);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (!achievement) return null;
  const definition = achievementDefinition(achievement.id);
  if (!definition) return null;

  const achievementText = t(definition.translationKey);

  return (
    <div className="achievement-header-widget" title={achievementText} aria-label={achievementText}>
      <img src={definition.image} alt="" aria-hidden="true" />
    </div>
  );
}

function AirSensorHeader() {
  const { language, t } = useI18n();
  const [sensor, setSensor] = useState<AirSensorCurrent | null>(null);

  async function load() {
    try {
      const data = await api.airSensorCurrent();
      setSensor(data);
    } catch {
      setSensor(null);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(timer);
  }, []);

  if (!sensor?.enabled || !sensor.configured) return null;

  return (
    <div className={sensor.ok ? 'air-header-widget' : 'air-header-widget offline'} title={sensor.ok ? t('airSensorSettings') : (sensor.last_error || t('offline'))}>
      <span className="air-header-item"><Thermometer size={17} /> {fmtTemperature(sensor.temperature_c, language)}</span>
      <span className="air-header-item"><Droplets size={17} /> {fmtPercent(sensor.humidity_percent, language)}</span>
      <span className="air-header-item"><Wind size={17} /> PM10 {fmtMicrograms(sensor.sds_p1, language)}</span>
      <span className="air-header-item"><Wind size={17} /> PM2.5 {fmtMicrograms(sensor.sds_p2, language)}</span>
    </div>
  );
}

function tabTitle(tab: Tab, t: Translator): string {
  return {
    dashboard: t('dashboard'),
    history: t('history'),
    setup: t('setup'),
    account: t('account2fa'),
    help: t('help')
  }[tab];
}


function HelpView() {
  const { language, t } = useI18n();
  const [html, setHtml] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fileName = language === 'de' ? 'deREADME.md' : 'README.md';
    setError(null);
    setHtml('');

    fetch(`/help/${fileName}?version=${encodeURIComponent(APP_VERSION)}`, { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error(t('helpLoadFailed'));
        return response.text();
      })
      .then(markdown => {
        if (!cancelled) setHtml(markdownToHtml(markdown));
      })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : t('helpLoadFailed'));
      });

    return () => { cancelled = true; };
  }, [language, t]);

  return (
    <section className="panel help-panel">
      <div className="panel-head">
        <h2><HelpCircle size={20} /> {t('helpTitle')}</h2>
      </div>
      <p className="hint">{t('helpHint')}</p>
      {error && <div className="error">{error}</div>}
      {!error && !html && <p className="hint">{t('wait')}</p>}
      {html && <article className="help-document" dangerouslySetInnerHTML={{ __html: html }} />}
    </section>
  );
}

function markdownToHtml(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const html: string[] = [];
  let inCode = false;
  let codeLines: string[] = [];
  let listType: 'ul' | 'ol' | null = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      closeList();
      continue;
    }

    if (/^[-*_]{3,}$/.test(trimmed)) {
      closeList();
      html.push('<hr />');
      continue;
    }

    if (trimmed.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i + 1])) {
      closeList();
      const headers = splitMarkdownTableRow(trimmed);
      i += 2;
      const bodyRows: string[][] = [];
      while (i < lines.length && lines[i].trim().includes('|')) {
        bodyRows.push(splitMarkdownTableRow(lines[i].trim()));
        i += 1;
      }
      i -= 1;
      html.push('<div class="table-wrap"><table><thead><tr>');
      html.push(headers.map(cell => `<th>${renderInlineMarkdown(cell)}</th>`).join(''));
      html.push('</tr></thead><tbody>');
      for (const row of bodyRows) {
        html.push('<tr>');
        html.push(row.map(cell => `<td>${renderInlineMarkdown(cell)}</td>`).join(''));
        html.push('</tr>');
      }
      html.push('</tbody></table></div>');
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      closeList();
      const level = heading[1].length + 1;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(trimmed);
    if (image) {
      closeList();
      html.push(`<figure><img src="${normalizeHelpHref(image[2])}" alt="${escapeHtml(image[1])}" loading="lazy" /></figure>`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      if (listType !== 'ul') {
        closeList();
        html.push('<ul>');
        listType = 'ul';
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ordered) {
      if (listType !== 'ol') {
        closeList();
        html.push('<ol>');
        listType = 'ol';
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    if (trimmed.startsWith('>')) {
      closeList();
      html.push(`<blockquote>${renderInlineMarkdown(trimmed.replace(/^>\s?/, ''))}</blockquote>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(trimmed)}</p>`);
  }

  closeList();
  if (inCode) html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
  return html.join('\n');
}

function splitMarkdownTableRow(row: string): string[] {
  return row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
}

function renderInlineMarkdown(text: string): string {
  const parts = text.split(/(`[^`]*`)/g);
  return parts.map(part => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
    }
    let rendered = escapeHtml(part);
    rendered = rendered.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    rendered = rendered.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
      const normalized = normalizeHelpHref(href);
      const external = /^https?:\/\//i.test(href);
      const target = external ? ' target="_blank" rel="noreferrer"' : '';
      return `<a href="${normalized}"${target}>${label}</a>`;
    });
    return rendered;
  }).join('');
}

function normalizeHelpHref(href: string): string {
  const cleaned = href.trim();
  if (/^(https?:|mailto:|#|\/)/i.test(cleaned)) return escapeHtmlAttribute(cleaned);
  return escapeHtmlAttribute(`/help/${cleaned}`);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeHtmlAttribute(value: string): string {
  return escapeHtml(value).replace(/`/g, '&#096;');
}


function PublicAirSensorWidget({ sensor }: { sensor: AirSensorCurrent | null }) {
  const { language, t } = useI18n();
  if (!sensor?.enabled || !sensor.configured) return null;

  return (
    <section className={sensor.ok ? 'panel public-air-sensor' : 'panel public-air-sensor offline'} title={sensor.ok ? t('airSensorSettings') : (sensor.last_error || t('offline'))}>
      <div className="panel-head"><h2><Wind size={20} /> {t('airSensorSettings')}</h2></div>
      <div className="public-air-grid">
        <span><Thermometer size={18} /> {fmtTemperature(sensor.temperature_c, language)}</span>
        <span><Droplets size={18} /> {fmtPercent(sensor.humidity_percent, language)}</span>
        <span><Wind size={18} /> PM10 {fmtMicrograms(sensor.sds_p1, language)}</span>
        <span><Wind size={18} /> PM2.5 {fmtMicrograms(sensor.sds_p2, language)}</span>
      </div>
    </section>
  );
}

function PublicDashboard() {
  const { t } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sensor, setSensor] = useState<AirSensorCurrent | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [summaryData, sensorData] = await Promise.all([
        api.publicSummary(),
        api.publicAirSensorCurrent().catch(() => null),
      ]);
      setSummary(summaryData);
      setSensor(sensorData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('publicDashboardLoadFailed'));
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="grid gap public-dashboard-content">
      {error && <div className="error">{error}</div>}
      <PublicAirSensorWidget sensor={sensor} />
      <div className="cards dashboard-cards">
        <GridPowerMetric summary={summary} />
        <DailyBalanceMetric summary={summary} />
        <TotalBalanceMetric summary={summary} />
        <CostBalanceMetric summary={summary} mode="daily" />
        <CostBalanceMetric summary={summary} mode="total" />
      </div>
    </div>
  );
}

function Dashboard() {
  const { language, t } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [latest, setLatest] = useState<Measurement[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [summaryData, latestData, deviceData] = await Promise.all([api.summary(), api.latest(), api.devices()]);
      setSummary(summaryData);
      setLatest(latestData);
      setDevices(deviceData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dashboardLoadFailed'));
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="grid gap">
      {error && <div className="error">{error}</div>}
      <div className="cards dashboard-cards">
        <GridPowerMetric summary={summary} />
        <DailyBalanceMetric summary={summary} />
        <TotalBalanceMetric summary={summary} />
        <AmortizationMetric summary={summary} />
        <CostBalanceMetric summary={summary} mode="daily" />
        <CostBalanceMetric summary={summary} mode="total" />
      </div>
      <DashboardDeviceMeasurements devices={devices} latest={latest} onRefresh={load} />
    </div>
  );
}

type DashboardMeasurementRow = {
  device: Device;
  measurement: Measurement | null;
};

function measurementSortKey(measurement: Measurement): string {
  const phaseOrder: Record<string, string> = { L1: '1', L2: '2', L3: '3', total: '9' };
  const phase = measurement.phase || '';
  const phaseKey = phaseOrder[phase] || phase;
  const channelKey = measurement.channel === null || measurement.channel === undefined ? 'z' : String(measurement.channel).padStart(2, '0');
  return `${measurement.source_type}|${channelKey}|${phaseKey}|${measurement.timestamp}`;
}

function formatMeasurementPhase(phase: string | null | undefined, t: (key: TranslationKey, vars?: Record<string, string | number>) => string): string {
  if (!phase) {
    return t('none');
  }
  return phase === 'total' ? t('total') : phase;
}

function measurementMatchesDeviceConfig(device: Device, measurement: Measurement): boolean {
  if (device.channel === null || device.channel === undefined) {
    return true;
  }
  if (device.device_type === 'shelly_3em_gen1' && measurement.source_type === 'shelly_3em_gen1_total') {
    return false;
  }
  return measurement.channel === device.channel;
}

function shouldShowChannelColumn(rows: DashboardMeasurementRow[]): boolean {
  return rows.some(({ device, measurement }) => (
    device.channel !== null
    && device.channel !== undefined
  ) || (
    measurement?.channel !== null
    && measurement?.channel !== undefined
  ));
}

function DashboardDeviceMeasurements({ devices, latest, onRefresh }: { devices: Device[]; latest: Measurement[]; onRefresh: () => Promise<void> }) {
  const { language, t } = useI18n();
  const latestByDevice = new Map<number, Measurement[]>();

  latest.forEach(row => {
    const list = latestByDevice.get(row.device_id) ?? [];
    list.push(row);
    latestByDevice.set(row.device_id, list);
  });

  latestByDevice.forEach(list => list.sort((a, b) => measurementSortKey(a).localeCompare(measurementSortKey(b))));

  const rows: DashboardMeasurementRow[] = devices.flatMap<DashboardMeasurementRow>(device => {
    const measurements = (latestByDevice.get(device.id) ?? []).filter(measurement => measurementMatchesDeviceConfig(device, measurement));
    if (!measurements.length) {
      return [{ device, measurement: null }];
    }
    return measurements.map(measurement => ({ device, measurement }));
  });

  const measurementRows = rows.map(row => row.measurement).filter((row): row is Measurement => row !== null);
  const hasChannel = shouldShowChannelColumn(rows);
  const hasPhase = measurementRows.some(row => Boolean(row.phase));
  const hasVoltage = measurementRows.some(row => row.voltage_v !== null && row.voltage_v !== undefined);
  const hasCurrent = measurementRows.some(row => row.current_a !== null && row.current_a !== undefined);

  return (
    <section className="panel dashboard-device-measurements">
      <div className="panel-head">
        <h2>{t('dashboardDeviceMeasurements')}</h2>
        <button onClick={() => void onRefresh()}><RefreshCcw size={16} /> {t('refresh')}</button>
      </div>
      <div className="table-wrap compact-table-wrap">
        <table className="compact-dashboard-table">
          <thead>
            <tr>
              <th>{t('name')}</th>
              <th>{t('status')}</th>
              <th>{t('lastPoll')}</th>
              <th>{t('time')}</th>
              {hasChannel && <th>{t('channel')}</th>}
              {hasPhase && <th>{t('phase')}</th>}
              <th>{t('power')}</th>
              {hasVoltage && <th>{t('voltage')}</th>}
              {hasCurrent && <th>{t('current')}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ device, measurement }, index) => (
              <tr key={`${device.id}-${measurement?.id ?? `device-${index}`}`}>
                <td>{device.name}</td>
                <td><span className={device.status?.online ? 'badge ok' : 'badge'}>{device.status?.online ? t('online') : t('offline')}</span></td>
                <td>{fmtDate(device.status?.last_success_at, language)}</td>
                <td>{measurement ? fmtDate(measurement.timestamp, language) : t('noLatestMeasurement')}</td>
                {hasChannel && <td>{measurement?.channel ?? device.channel ?? t('none')}</td>}
                {hasPhase && <td>{formatMeasurementPhase(measurement?.phase, t)}</td>}
                <td>{measurement ? fmtW(measurement.power_w ?? measurement.total_power_w ?? measurement.grid_power_w ?? measurement.solar_power_w, language) : t('none')}</td>
                {hasVoltage && <td>{measurement?.voltage_v ?? t('none')}</td>}
                {hasCurrent && <td>{measurement?.current_a ?? t('none')}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}


function GridPowerMetric({ summary }: { summary: Summary | null }) {
  const { language, t } = useI18n();
  const gridPower = summary?.current_grid_power_w ?? 0;
  const solarRaw = summary?.current_solar_power_w;
  const solarPower = Math.max(solarRaw ?? 0, 0);
  const gridImportPower = Math.max(gridPower, 0);
  const totalPower = gridImportPower + solarPower;
  const hasPower = totalPower > 0.01;
  const gridPercent = hasPower ? clampPercent((gridImportPower / totalPower) * 100) : 0;
  const solarPercent = hasPower ? clampPercent(100 - gridPercent) : 0;
  const exporting = gridPower < -0.01;
  const gridValueClass = gridPower < -0.01 ? 'negative' : Math.abs(gridPower) <= 0.01 ? 'zero' : 'positive';

  return (
    <div className="metric metric-grid-power">
      <div className="grid-power-top">
        <div className="grid-power-values">
          <p>{t('gridPower')}</p>
          <strong className={`home-import-value ${gridValueClass}`}>{fmtW(summary?.current_grid_power_w, language)}</strong>
          <div className="embedded-solar-value">
            <span>{t('solarShare')}</span>
            <b>{fmtW(solarRaw ?? 0, language)}</b>
          </div>
          {exporting && <small>{`${t('gridExporting')}: ${fmtW(Math.abs(gridPower), language)}`}</small>}
        </div>
        <div
          className="share-gauge share-gauge-mini"
          style={{ '--grid-share': `${gridPercent}%` } as React.CSSProperties}
          role="img"
          aria-label={`${t('gridImportShare')}: ${fmtPercent(gridPercent, language)}, ${t('solarShare')}: ${fmtPercent(solarPercent, language)}`}
          title={t('gridShareGauge')}
        >
          <div className="share-gauge-inner">
            <strong>{hasPower ? fmtPercent(solarPercent, language) : '—'}</strong>
            <span>{t('solarShare')}</span>
          </div>
        </div>
      </div>
      <div className="mini-share-row">
        <span className="mini-share-item grid-import"><i />{t('gridImportShare')}: {fmtW(gridImportPower, language)} · {hasPower ? fmtPercent(gridPercent, language) : t('noPowerData')}</span>
        <span className="mini-share-item solar"><i />{t('solarShare')}: {fmtW(solarRaw ?? 0, language)} · {hasPower ? fmtPercent(solarPercent, language) : t('noPowerData')}</span>
      </div>
    </div>
  );
}

function GridShareGauge({ summary }: { summary: Summary | null }) {
  const { language, t } = useI18n();
  const gridPower = summary?.current_grid_power_w ?? 0;
  const solarPower = Math.max(summary?.current_solar_power_w ?? 0, 0);
  const gridImportPower = Math.max(gridPower, 0);
  const totalPower = gridImportPower + solarPower;
  const hasPower = totalPower > 0.01;
  const gridPercent = hasPower ? clampPercent((gridImportPower / totalPower) * 100) : 0;
  const solarPercent = hasPower ? clampPercent(100 - gridPercent) : 0;
  const exporting = gridPower < -0.01;

  return (
    <section className="panel grid-share-panel">
      <div className="panel-head">
        <h2><Activity size={20} /> {t('gridShareGauge')}</h2>
      </div>
      <div className="grid-share-content">
        <div
          className="share-gauge"
          style={{ '--grid-share': `${gridPercent}%` } as React.CSSProperties}
          role="img"
          aria-label={`${t('gridImportShare')}: ${fmtPercent(gridPercent, language)}, ${t('solarShare')}: ${fmtPercent(solarPercent, language)}`}
        >
          <div className="share-gauge-inner">
            <strong>{hasPower ? fmtPercent(solarPercent, language) : '—'}</strong>
            <span>{t('solarShare')}</span>
          </div>
        </div>
        <div className="share-gauge-details">
          <p className="hint">{t('gridShareGaugeSubtitle')}</p>
          {exporting && <div className="info compact-info">{t('gridExporting')}: {fmtW(Math.abs(gridPower), language)}</div>}
          <div className="share-legend">
            <div className="share-legend-item grid-import">
              <span />
              <div><strong>{t('gridImportShare')}</strong><small>{fmtW(gridImportPower, language)} · {hasPower ? fmtPercent(gridPercent, language) : t('noPowerData')}</small></div>
            </div>
            <div className="share-legend-item solar">
              <span />
              <div><strong>{t('solarShare')}</strong><small>{fmtW(solarPower, language)} · {hasPower ? fmtPercent(solarPercent, language) : t('noPowerData')}</small></div>
            </div>
          </div>
          <div className="share-total"><strong>{t('totalCurrently')}:</strong> {hasPower ? fmtW(totalPower, language) : t('noPowerData')}</div>
        </div>
      </div>
    </section>
  );
}


function DailyBalanceMetric({ summary }: { summary: Summary | null }) {
  const { language, t } = useI18n();
  const totalConsumptionTodayKwh = sumKwhValues(summary?.imported_today_kwh, summary?.solar_today_kwh);
  return (
    <div className="metric daily-balance-metric">
      <p>{t('dailyBalance')}</p>
      <div className="daily-balance-list">
        <div className="daily-balance-total-row"><span>{t('totalConsumption')}</span><strong>{fmtKwh(totalConsumptionTodayKwh, language)}</strong></div>
        <div><span>{t('solarToday')}</span><strong>{fmtKwh(summary?.solar_today_kwh ?? 0, language)}</strong></div>
        <div><span>{t('importedToday')}</span><strong>{fmtKwh(summary?.imported_today_kwh ?? 0, language)}</strong></div>
        <div><span>{t('exportedToday')}</span><strong>{fmtKwh(summary?.exported_today_kwh ?? 0, language)}</strong></div>
      </div>
    </div>
  );
}

function TotalBalanceMetric({ summary }: { summary: Summary | null }) {
  const { language, t } = useI18n();
  const totalConsumptionKwh = sumKwhValues(summary?.imported_total_kwh, summary?.solar_total_kwh);
  return (
    <div className="metric daily-balance-metric">
      <p>{t('totalBalance')}</p>
      <div className="daily-balance-list">
        <div className="daily-balance-total-row"><span>{t('totalConsumption')}</span><strong>{fmtKwh(totalConsumptionKwh, language)}</strong></div>
        <div><span>{t('solarToday')}</span><strong>{fmtKwh(summary?.solar_total_kwh, language)}</strong></div>
        <div><span>{t('importedToday')}</span><strong>{fmtKwh(summary?.imported_total_kwh, language)}</strong></div>
        <div><span>{t('exportedToday')}</span><strong>{fmtKwh(summary?.exported_total_kwh, language)}</strong></div>
      </div>
    </div>
  );
}

function CostBalanceMetric({ summary, mode }: { summary: Summary | null; mode: 'daily' | 'total' }) {
  const { language, t } = useI18n();
  const price = summary?.kwh_price_eur ?? 0;
  const currency = summary?.currency_code;
  const consumptionCost = mode === 'daily'
    ? summary?.consumption_cost_today_eur
    : summary?.imported_total_kwh !== null && summary?.imported_total_kwh !== undefined
      ? summary.imported_total_kwh * price
      : null;
  const savings = mode === 'daily' ? (summary?.savings_today_eur ?? 0) : summary?.savings_total_eur;

  return (
    <div className="metric daily-balance-metric">
      <p>{mode === 'daily' ? t('dailyCostBalance') : t('totalCostBalance')}</p>
      <div className="daily-balance-list">
        <div><span>{t('consumptionCost')}</span><strong>{fmtCurrency(consumptionCost, language, currency)}</strong></div>
        <div><span>{t('savings')}</span><strong>{fmtCurrency(savings, language, currency)}</strong></div>
      </div>
      <small>{fmtCurrency(price, language, currency)} / kWh</small>
    </div>
  );
}

function AmortizationMetric({ summary }: { summary: Summary | null }) {
  const { language, t } = useI18n();
  const [batteryDetailsCopied, setBatteryDetailsCopied] = useState(false);
  const [batteryDetailsOpen, setBatteryDetailsOpen] = useState(false);
  const currency = summary?.currency_code;
  const investment = summary?.investment_cost_eur ?? 0;
  const progress = summary?.breakeven_progress_percent;
  const remaining = summary?.remaining_to_breakeven_eur;
  const remainingDays = summary?.estimated_breakeven_days;
  const estimatedDate = summary?.estimated_breakeven_date;
  const progressValue = clampPercent(progress ?? 0);

  const batteryEnabled = Boolean(summary?.battery_analysis_enabled);
  const batteryCost = summary?.battery_cost_eur ?? 0;
  const batteryCapacity = summary?.battery_capacity_kwh ?? 0;
  const batteryConfigured = batteryEnabled && batteryCost > 0 && batteryCapacity > 0;
  const batteryPaybackDays = summary?.battery_payback_days;
  const batteryWorthwhile = summary?.battery_worthwhile;
  const batteryDetailRows = batteryConfigured ? [
    [t('batteryUsableSurplusToday'), fmtKwh(summary?.battery_usable_surplus_today_kwh, language)],
    [t('batterySavingsToday'), fmtCurrency(summary?.battery_savings_today_eur, language, currency)],
    [t('batteryPayback'), batteryPaybackDays === null || batteryPaybackDays === undefined ? '∞' : fmtDays(batteryPaybackDays, language, t)],
    [t('batteryOpenBps'), fmtCurrency(summary?.battery_remaining_bps_investment_eur, language, currency)],
    [t('batteryCombinedInvestment'), fmtCurrency(summary?.battery_combined_investment_eur, language, currency)],
    [t('batteryCombinedPayback'), summary?.battery_combined_payback_days === null || summary?.battery_combined_payback_days === undefined ? '∞' : fmtDays(summary.battery_combined_payback_days, language, t)],
  ] : [];
  const batteryDetailCopyText = batteryConfigured
    ? `${batteryDetailRows.map(([label, value]) => `${label}: ${value}`).join('\n')}\n${t('batteryAssumption')}`
    : '';

  async function copyBatteryDetails() {
    if (!batteryDetailCopyText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(batteryDetailCopyText);
      setBatteryDetailsCopied(true);
      window.setTimeout(() => setBatteryDetailsCopied(false), 1800);
    } catch {
      setBatteryDetailsCopied(false);
    }
  }

  return (
    <div className="metric amortization-metric">
      <p>{t('amortization')}</p>
      {investment > 0 ? (
        <>
          <div className="progress-line" aria-label={`${t('breakevenProgress')}: ${fmtPercent(progressValue, language)}`}>
            <span style={{ width: `${progressValue}%` }} />
          </div>
          <div className="daily-balance-list">
            <div><span>{t('breakevenProgress')}</span><strong>{fmtPercent(progressValue, language)}</strong></div>
            <div><span>{t('remaining')}</span><strong>{fmtCurrency(remaining, language, currency)}</strong></div>
            <div><span>{t('estimatedRemaining')}</span><strong>{remainingDays === null || remainingDays === undefined ? '∞' : fmtDays(remainingDays, language, t)}</strong></div>
          </div>
          {estimatedDate && <small>{t('untilApprox', { date: new Date(estimatedDate).toLocaleDateString(localeFor(language)) })}</small>}
        </>
      ) : (
        <small>{t('enterInvestment')}</small>
      )}

      <div className="battery-analysis">
        <p>{t('batteryAnalysis')}</p>
        {!batteryEnabled ? (
          <small className="battery-analysis-status">{t('batteryAnalysisDisabled')}</small>
        ) : batteryConfigured ? (
          <>
            <button
              type="button"
              className="battery-analysis-status battery-analysis-toggle"
              aria-expanded={batteryDetailsOpen}
              onClick={() => setBatteryDetailsOpen(open => !open)}
            >
              {batteryWorthwhile ? t('batteryWorthwhile') : t('batteryNotWorthwhile')}
            </button>
            {batteryDetailsOpen && (
              <div className="embedded-copy-box battery-detail-box">
                <div className="embedded-copy-head">
                  <span>{t('batteryDetails')}</span>
                  <button type="button" onClick={() => void copyBatteryDetails()}>{batteryDetailsCopied ? t('batteryDetailsCopied') : t('copyBatteryDetails')}</button>
                </div>
                <div className="daily-balance-list">
                  {batteryDetailRows.map(([label, value]) => (
                    <div key={label}><span>{label}</span><strong>{value}</strong></div>
                  ))}
                </div>
                <small>{t('batteryAssumption')}</small>
              </div>
            )}
          </>
        ) : (
          <small className="battery-analysis-status">{t('batteryMissing')}</small>
        )}
      </div>
    </div>
  );
}


function Metric({ title, value, subtitle }: { title: string; value: string; subtitle?: string }) {
  return <div className="metric"><p>{title}</p><strong>{value}</strong>{subtitle && <small>{subtitle}</small>}</div>;
}

function HistoryView() {
  const { language, t } = useI18n();
  const [hours, setHours] = useState(24);
  const [history, setHistory] = useState<Measurement[]>([]);
  const [historyTotals, setHistoryTotals] = useState<HistoryTotals | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const [nextHistory, nextTotals] = await Promise.all([api.history(hours), api.historyTotals(hours)]);
    setHistory(nextHistory);
    setHistoryTotals(nextTotals);
  }

  async function exportCsv() {
    const blob = await api.exportCsv();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'bpstracker-measurements.csv';
    a.click();
    window.URL.revokeObjectURL(url);
    setMessage(t('csvDownloaded'));
  }

  useEffect(() => { void load(); }, [hours]);

  const historySeriesNames = useMemo(() => ({
    solar: `${t('solarShare')} (${fmtKwh(historyTotals?.solar_kwh, language)})`,
    gridImport: `${t('gridImportShare')} (${fmtKwh(historyTotals?.imported_kwh, language)})`,
    gridExport: `${t('exportedToday')} (${fmtKwh(historyTotals?.exported_kwh, language)})`,
  }), [historyTotals, language, t]);

  const chartData = useMemo(() => history.map(row => {
    const gridPower = row.grid_power_w ?? row.total_power_w ?? null;
    const solarPower = row.solar_power_w ?? (row.source_type?.includes('solar') ? row.power_w : null);
    const fallbackPower = row.power_w ?? row.total_power_w ?? null;
    return {
      time: new Date(row.timestamp).toLocaleString(localeFor(language), { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
      solar: solarPower === null || solarPower === undefined ? null : Math.abs(solarPower),
      gridImport: gridPower === null || gridPower === undefined ? null : Math.max(0, gridPower),
      gridExport: gridPower === null || gridPower === undefined ? null : Math.abs(Math.min(0, gridPower)),
      power: fallbackPower,
      source: row.source_type,
      device: row.device_id
    };
  }), [history, language]);

  return (
    <section className="panel tall">
      {message && <div className="info">{message}</div>}
      <div className="panel-head">
        <div className="row gap-small">
          <button className={hours === 24 ? 'active small' : 'small'} onClick={() => setHours(24)}>24h</button>
          <button className={hours === 168 ? 'active small' : 'small'} onClick={() => setHours(168)}>{language === 'de' ? '7 Tage' : '7 days'}</button>
          <button className={hours === 720 ? 'active small' : 'small'} onClick={() => setHours(720)}>{language === 'de' ? '30 Tage' : '30 days'}</button>
        </div>
        <button onClick={() => void exportCsv()}>{t('csvExport')}</button>
      </div>
      <ResponsiveContainer width="100%" height={420}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="time" minTickGap={32} />
          <YAxis />
          <Tooltip />
          <Legend />
          <Area
            type="monotone"
            dataKey="solar"
            name={historySeriesNames.solar}
            stroke="#16a34a"
            fill="#16a34a"
            fillOpacity={0.22}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Area
            type="monotone"
            dataKey="gridImport"
            name={historySeriesNames.gridImport}
            stroke="#2563eb"
            fill="#2563eb"
            fillOpacity={0.20}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Area
            type="monotone"
            dataKey="gridExport"
            name={historySeriesNames.gridExport}
            stroke="#dc2626"
            fill="#dc2626"
            fillOpacity={0.18}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  );
}


function GithubRepositoryPanel() {
  const { t } = useI18n();

  return (
    <section className="panel github-repository-panel">
      <div className="panel-head"><h2><Globe2 size={20} /> {t('githubRepository')}</h2></div>
      <p className="hint">{t('githubRepositoryHint')}</p>
      <a className="button" href="https://github.com/syschelle/bpstracker" target="_blank" rel="noreferrer">{t('openGithubRepository')}</a>
    </section>
  );
}

function SetupView({ onCurrentUserChange }: { onCurrentUserChange: (user: User) => void }) {
  return (
    <div className="grid gap">
      <LanguageSettingsPanel />
      <TimezoneSettingsPanel />
      <GithubRepositoryPanel />
      <KindleDisplaySettingsPanel />
      <SimulationSettingsPanel />
      <PublicDashboardSettingsPanel />
      <CurrentValuesApiSettingsPanel />
      <UserCredentialsPanel onCurrentUserChange={onCurrentUserChange} />
      <FinanceSettingsPanel />
      <BackupSettingsPanel />
      <ResetValuesPanel />
      <RetentionSettingsPanel />
      <AirSensorSettingsPanel />
      <DeviceSetupPanel />
    </div>
  );
}

const TIMEZONE_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: 'Europe/Berlin', labelKey: 'timezoneEuropeBerlin' },
  { value: 'Europe/London', labelKey: 'timezoneEuropeLondon' },
  { value: 'UTC', labelKey: 'timezoneUtc' },
  { value: 'America/New_York', labelKey: 'timezoneAmericaNewYork' },
];



function LanguageSettingsPanel() {
  const { language, setLanguage, t } = useI18n();
  const [settings, setSettings] = useState<UiSettings>({ language, timezone: 'Europe/Berlin' });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const loaded = await api.uiSettings();
    setSettings(loaded);
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateUiSettings({
      language: settings.language,
      timezone: settings.timezone || 'Europe/Berlin',
    });
    setSettings(saved);
    setLanguage(saved.language);
    setMessage(t('languageSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Globe2 size={20} /> {t('languageSettings')}</h2></div>
      <p className="hint">{t('languageHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label>{t('languageLabel')}
          <select value={settings.language} onChange={e => setSettings({ ...settings, language: e.target.value as Language })}>
            <option value="de">{t('german')}</option>
            <option value="en">{t('english')}</option>
          </select>
        </label>
      </div>
      <p className="hint">Kindle-Display und serverseitige Ausgaben verwenden diese gespeicherte Sprache. Der Header-Umschalter bleibt eine Browser-/Cookie-Auswahl.</p>
      <button onClick={() => void save()}>{t('saveLanguage')}</button>
    </section>
  );
}

function TimezoneSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<UiSettings>({ language: 'de', timezone: 'Europe/Berlin' });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setSettings(await api.uiSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateUiSettings({
      language: settings.language,
      timezone: settings.timezone || 'Europe/Berlin',
    });
    setSettings(saved);
    setMessage(t('timezoneSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Globe2 size={20} /> {t('timezoneSettings')}</h2></div>
      <p className="hint">{t('timezoneHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label>{t('timezoneLabel')}
          <select value={settings.timezone} onChange={e => setSettings({ ...settings, timezone: e.target.value })}>
            {TIMEZONE_OPTIONS.map(option => <option key={option.value} value={option.value}>{t(option.labelKey)}</option>)}
          </select>
        </label>
      </div>
      <button onClick={() => void save()}>{t('saveTimezone')}</button>
    </section>
  );
}

function UserCredentialsPanel({ onCurrentUserChange }: { onCurrentUserChange: (user: User) => void }) {
  const { t } = useI18n();
  const [users, setUsers] = useState<User[]>([]);
  const [adminUsername, setAdminUsername] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [viewerUsername, setViewerUsername] = useState('');
  const [viewerPassword, setViewerPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const data = await api.users();
    setUsers(data);
    setAdminUsername(data.find(u => u.role === 'admin')?.username ?? '');
    setViewerUsername(data.find(u => u.role === 'viewer')?.username ?? '');
  }

  useEffect(() => { void load(); }, []);

  async function saveRole(role: 'admin' | 'viewer') {
    setMessage(null);
    const username = role === 'admin' ? adminUsername : viewerUsername;
    const password = role === 'admin' ? adminPassword : viewerPassword;
    const updated = await api.updateUserCredentials(role, { username, password: password.trim() ? password : null });
    if (role === 'admin') {
      setAdminPassword('');
      onCurrentUserChange(updated);
    } else {
      setViewerPassword('');
    }
    setMessage(role === 'admin' ? t('adminSaved') : t('viewerSaved'));
    await load();
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><UserCog size={20} /> {t('userAccess')}</h2></div>
      <p className="hint">{t('userAccessHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="credentials-grid">
        <div className="credential-card">
          <h3>{t('roleAdmin')}</h3>
          <label>{t('username')}<input value={adminUsername} onChange={e => setAdminUsername(e.target.value)} /></label>
          <label>{t('newPassword')}<input type="password" value={adminPassword} onChange={e => setAdminPassword(e.target.value)} placeholder={t('unchangedPlaceholder')} /></label>
          <button onClick={() => void saveRole('admin')}>{t('saveAdmin')}</button>
          <small>{t('twoFaManagedInTab')}</small>
        </div>
        <div className="credential-card">
          <h3>{t('roleViewer')}</h3>
          <label>{t('username')}<input value={viewerUsername} onChange={e => setViewerUsername(e.target.value)} /></label>
          <label>{t('newPassword')}<input type="password" value={viewerPassword} onChange={e => setViewerPassword(e.target.value)} placeholder={t('unchangedPlaceholder')} /></label>
          <button onClick={() => void saveRole('viewer')}>{t('saveViewer')}</button>
          <small>{t('viewerNoSetup')}</small>
        </div>
      </div>
      <table className="compact-table">
        <thead><tr><th>{t('role')}</th><th>{t('username')}</th><th>{t('twoFa')}</th><th>{t('active')}</th></tr></thead>
        <tbody>{users.map(u => <tr key={u.id}><td>{u.role === 'admin' ? t('roleAdmin') : t('roleViewer')}</td><td>{u.username}</td><td>{u.totp_enabled ? t('enabled') : t('disabled')}</td><td>{u.is_active ? t('yes') : t('no')}</td></tr>)}</tbody>
      </table>
    </section>
  );
}

function FinanceSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<FinanceSettings>({ kwh_price_eur: 0.3, investment_cost_eur: 0, battery_analysis_enabled: false, battery_cost_eur: 0, battery_capacity_kwh: 0, currency_code: 'EUR' });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setSettings(await api.financeSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateFinanceSettings({
      kwh_price_eur: Number(settings.kwh_price_eur) || 0,
      investment_cost_eur: Number(settings.investment_cost_eur) || 0,
      battery_analysis_enabled: Boolean(settings.battery_analysis_enabled),
      battery_cost_eur: Number(settings.battery_cost_eur) || 0,
      battery_capacity_kwh: Number(settings.battery_capacity_kwh) || 0,
      currency_code: normalizeCurrency(settings.currency_code),
    });
    setSettings(saved);
    setMessage(t('financeSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Euro size={20} /> {t('financeValues')}</h2></div>
      <p className="hint">{t('financeHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label>{t('currency')}
          <select value={settings.currency_code} onChange={e => setSettings({ ...settings, currency_code: normalizeCurrency(e.target.value) })}>
            <option value="EUR">{t('currencyEur')}</option>
            <option value="USD">{t('currencyUsd')}</option>
            <option value="GBP">{t('currencyGbp')}</option>
          </select>
        </label>
        <label>{t('kwhPrice')} ({currencySymbol(settings.currency_code)}/kWh)<input type="number" min={0} step="0.0001" value={settings.kwh_price_eur} onChange={e => setSettings({ ...settings, kwh_price_eur: Number(e.target.value) })} placeholder="0,30" /></label>
        <label>{t('investmentCost')} ({currencySymbol(settings.currency_code)})<input type="number" min={0} step="0.01" value={settings.investment_cost_eur} onChange={e => setSettings({ ...settings, investment_cost_eur: Number(e.target.value) })} placeholder="600" /></label>
        <label className="check"><input type="checkbox" checked={Boolean(settings.battery_analysis_enabled)} onChange={e => setSettings({ ...settings, battery_analysis_enabled: e.target.checked })} /> {t('enableBatteryAnalysis')}</label>
        <label>{t('batteryCost')} ({currencySymbol(settings.currency_code)})<input type="number" min={0} step="0.01" value={settings.battery_cost_eur ?? 0} onChange={e => setSettings({ ...settings, battery_cost_eur: Number(e.target.value) })} placeholder="1200" /></label>
        <label>{t('batteryCapacity')} (kWh)<input type="number" min={0} step="0.1" value={settings.battery_capacity_kwh ?? 0} onChange={e => setSettings({ ...settings, battery_capacity_kwh: Number(e.target.value) })} placeholder="2.0" /></label>
      </div>
      <p className="hint">{t('feedInNotPaidHint')}</p>
      <p className="hint">{t('currencyHint')}</p>
      <button onClick={() => void save()}>{t('saveFinance')}</button>
    </section>
  );
}


function BackupSettingsPanel() {
  const { language, t } = useI18n();
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBackups(await api.backups());
  }

  useEffect(() => { void load(); }, []);

  async function createBackup() {
    setMessage(null);
    setError(null);
    if (password.length < 12) {
      setError(t('backupPasswordTooShort'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('backupPasswordMismatch'));
      return;
    }
    setBusy(true);
    try {
      const created = await api.createBackup(password, confirmPassword);
      setPassword('');
      setConfirmPassword('');
      setMessage(t('backupCreated'));
      await load();
      await downloadBackup(created.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function downloadBackup(filename: string) {
    const blob = await api.downloadBackup(filename);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function deleteBackup(filename: string) {
    if (!window.confirm(t('backupDeleteConfirm'))) return;
    setError(null);
    setMessage(null);
    await api.deleteBackup(filename);
    await load();
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><ShieldCheck size={20} /> {t('backupSettings')}</h2></div>
      <p className="hint">{t('backupHint')}</p>
      <p className="hint strong-hint">{t('backupPasswordWarning')}</p>
      {message && <div className="info">{message}</div>}
      {error && <div className="error">{error}</div>}
      <div className="form-grid finance-form">
        <label>{t('backupPassword')}<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" /></label>
        <label>{t('backupConfirmPassword')}<input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} autoComplete="new-password" /></label>
      </div>
      <button disabled={busy} onClick={() => void createBackup()}>{busy ? t('wait') : t('createEncryptedBackup')}</button>

      <h3>{t('existingBackups')}</h3>
      {backups.length === 0 ? <p className="hint">{t('noBackups')}</p> : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t('created')}</th><th>{t('backupSize')}</th><th>{t('actions')}</th></tr>
            </thead>
            <tbody>
              {backups.map(backup => (
                <tr key={backup.filename}>
                  <td><code>{backup.filename}</code><br /><span className="muted">{fmtDate(backup.created_at, language)}</span></td>
                  <td>{fmtBytes(backup.size_bytes, language)}</td>
                  <td className="actions-cell">
                    <button type="button" className="secondary" onClick={() => void downloadBackup(backup.filename)}>{t('download')}</button>
                    <button type="button" className="danger" onClick={() => void deleteBackup(backup.filename)}>{t('deleteBackup')}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RetentionSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<RetentionSettings>({ raw_retention_days: 30, daily_aggregates_forever: true });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setSettings(await api.retentionSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateRetentionSettings({
      raw_retention_days: Math.max(7, Math.min(3650, Number(settings.raw_retention_days) || 30)),
      daily_aggregates_forever: true,
    });
    setSettings(saved);
    setMessage(t('retentionSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><History size={20} /> {t('retentionSettings')}</h2></div>
      <p className="hint">{t('retentionHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label>{t('rawRetentionDays')} ({t('daysUnit')})
          <input type="number" min={7} max={3650} step={1} value={settings.raw_retention_days} onChange={e => setSettings({ ...settings, raw_retention_days: Number(e.target.value) })} />
        </label>
        <label>{t('dailyAggregates')}
          <input value={t('dailyAggregatesHint')} disabled />
        </label>
      </div>
      <p className="hint">{t('retentionCurrent', { days: settings.raw_retention_days })}</p>
      <button onClick={() => void save()}>{t('saveRetention')}</button>
    </section>
  );
}





function ResetValuesPanel() {
  const { t } = useI18n();
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function reset() {
    setMessage(null);
    setError(null);
    if (confirmation.trim().toLowerCase() !== 'reset') {
      setError(t('resetValuesWarning'));
      return;
    }
    setBusy(true);
    try {
      const result = await api.resetValues(confirmation);
      setConfirmation('');
      setMessage(`${t('resetValuesDone')} (${result.deleted_measurements} / ${result.deleted_daily_summaries})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel danger-panel">
      <div className="panel-head"><h2><Trash2 size={20} /> {t('resetValuesSettings')}</h2></div>
      <p className="hint">{t('resetValuesHint')}</p>
      <p className="hint strong-hint">{t('resetValuesWarning')}</p>
      {message && <div className="info">{message}</div>}
      {error && <div className="error">{error}</div>}
      <div className="form-grid finance-form">
        <label>{t('resetConfirmationLabel')}<input value={confirmation} placeholder={t('resetValuesConfirmPlaceholder')} onChange={e => setConfirmation(e.target.value)} /></label>
      </div>
      <button className="danger" disabled={busy || confirmation.trim().toLowerCase() !== 'reset'} onClick={() => void reset()}>{busy ? t('wait') : t('resetValuesButton')}</button>
    </section>
  );
}

function SimulationSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<SimulationSettings>({ enabled: false, pv_peak_w: 800, household_profile: 'two_person_household' });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setSettings(await api.simulationSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateSimulationSettings({
      enabled: settings.enabled,
      pv_peak_w: 800,
      household_profile: 'two_person_household',
    });
    setSettings(saved);
    setMessage(t('simulationSaved'));
  }

  return (
    <section className="panel simulation-settings-panel">
      <div className="panel-head"><h2><Activity size={20} /> {t('simulationSettings')}</h2></div>
      <p className="hint">{t('simulationHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e => setSettings({ ...settings, enabled: e.target.checked })} /> {t('enableSimulation')}</label>
      </div>
      <p className="hint">{t('simulationWarning')}</p>
      <button onClick={() => void save()}>{t('saveSimulation')}</button>
    </section>
  );
}


function PublicDashboardSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<PublicDashboardSettings>({ enabled: false });
  const [message, setMessage] = useState<string | null>(null);
  const publicUrl = typeof window === 'undefined' ? '/public/dashboard' : `${window.location.origin}/public/dashboard`;

  async function load() {
    setSettings(await api.publicDashboardSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updatePublicDashboardSettings({ enabled: settings.enabled });
    setSettings(saved);
    setMessage(t('publicDashboardSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Activity size={20} /> {t('publicDashboardSettings')}</h2></div>
      <p className="hint">{t('publicDashboardHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e => setSettings({ enabled: e.target.checked })} /> {t('enablePublicDashboard')}</label>
      </div>
      <p className="hint">{t('publicDashboardDisabledHint')}</p>
      {settings.enabled && (
        <div className="api-preview">
          <p className="hint">{t('publicDashboardLink')}</p>
          <pre>{publicUrl}</pre>
          <a className="button" href="/public/dashboard" target="_blank" rel="noreferrer">{t('openPublicDashboard')}</a>
        </div>
      )}
      <button onClick={() => void save()}>{t('saveChanges')}</button>
    </section>
  );
}

function CurrentValuesApiSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<CurrentValuesApiSettings>({ enabled: false });
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  async function load() {
    setSettings(await api.currentValuesApiSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateCurrentValuesApiSettings({ enabled: settings.enabled });
    setSettings(saved);
    setMessage(t('currentValuesApiSaved'));
    if (!saved.enabled) {
      setPreview(null);
      setPreviewError(null);
    }
  }

  async function loadPreview() {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      setPreview(await api.currentValues());
    } catch (error) {
      setPreview(null);
      setPreviewError(error instanceof Error ? error.message : String(error));
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Activity size={20} /> {t('currentValuesApiSettings')}</h2></div>
      <p className="hint">{t('currentValuesApiHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e => setSettings({ enabled: e.target.checked })} /> {t('enableCurrentValuesApi')}</label>
      </div>
      <p className="hint">{t('currentValuesApiDisabledHint')}</p>
      <div className="button-row">
        <button onClick={() => void save()}>{t('saveCurrentValuesApi')}</button>
        {settings.enabled && (
          <button type="button" className="secondary" disabled={previewLoading} onClick={() => preview ? setPreview(null) : void loadPreview()}>
            {preview ? t('hideJsonPreview') : t('showJsonPreview')}
          </button>
        )}
        {settings.enabled && preview && (
          <button type="button" className="secondary" disabled={previewLoading} onClick={() => void loadPreview()}>{t('refreshJsonPreview')}</button>
        )}
      </div>
      {settings.enabled && (preview || previewError) && (
        <div className="api-preview">
          <p className="hint">{t('jsonPreviewHint')}</p>
          {previewError ? <div className="error">{previewError}</div> : <pre>{JSON.stringify(preview, null, 2)}</pre>}
        </div>
      )}
    </section>
  );
}

function KindleDisplaySettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<KindleDisplaySettings>({ enabled: true });
  const [message, setMessage] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewNonce, setPreviewNonce] = useState(0);

  async function load() {
    setSettings(await api.kindleDisplaySettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateKindleDisplaySettings({ enabled: settings.enabled });
    setSettings(saved);
    setMessage(t('kindleDisplaySaved'));
    if (!saved.enabled) setShowPreview(false);
  }

  const previewUrl = `${api.kindlePreviewUrl()}?preview=${previewNonce}`;

  return (
    <section className="panel kindle-settings-panel">
      <div className="panel-head"><h2><Zap size={20} /> {t('kindleDisplaySettings')}</h2></div>
      <p className="hint">{t('kindleDisplayHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e => setSettings({ enabled: e.target.checked })} /> {t('enableKindleDisplay')}</label>
      </div>
      <p className="hint">{t('kindleDisplayDisabledHint')}</p>
      <div className="button-row">
        <button onClick={() => void save()}>{t('saveKindleDisplay')}</button>
        {settings.enabled && (
          <button type="button" className="secondary" onClick={() => setShowPreview(value => !value)}>
            {showPreview ? t('hideKindlePreview') : t('showKindlePreview')}
          </button>
        )}
        {settings.enabled && showPreview && (
          <button type="button" className="secondary" onClick={() => setPreviewNonce(Date.now())}>{t('refreshKindlePreview')}</button>
        )}
      </div>
      {settings.enabled && showPreview && (
        <div className="kindle-preview">
          <p className="hint">{t('kindlePreviewHint')}</p>
          <img src={previewUrl} alt="Kindle display preview" />
        </div>
      )}
    </section>
  );
}

function AirSensorSettingsPanel() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<AirSensorSettings>({ enabled: false, host: '' });
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setSettings(await api.airSensorSettings());
  }

  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    const saved = await api.updateAirSensorSettings({
      enabled: settings.enabled,
      host: (settings.host || '').trim() || null,
    });
    setSettings(saved);
    setMessage(t('airSensorSaved'));
  }

  return (
    <section className="panel">
      <div className="panel-head"><h2><Wind size={20} /> {t('airSensorSettings')}</h2></div>
      <p className="hint">{t('airSensorHint')}</p>
      {message && <div className="info">{message}</div>}
      <div className="form-grid finance-form">
        <label className="check"><input type="checkbox" checked={settings.enabled} onChange={e => setSettings({ ...settings, enabled: e.target.checked })} /> {t('enableAirSensor')}</label>
        <label>{t('airSensorHost')}<input value={settings.host || ''} onChange={e => setSettings({ ...settings, host: e.target.value })} placeholder="192.168.178.60" /></label>
      </div>
      <button onClick={() => void save()}>{t('saveAirSensor')}</button>
    </section>
  );
}



function deviceTypeLabel(deviceType: DeviceType, t: Translator): string {
  const labels: Record<DeviceType, string> = {
    auto: t('autoDetection'),
    shelly_3em_gen1: 'Shelly 3EM Gen1',
    shelly_pro_3em_gen2: 'Shelly Pro/NG 3EM',
    shelly_2pm_gen4: 'Shelly 2PM Gen4',
    shelly_ng_generic: 'Shelly NG generisch',
  };
  return labels[deviceType] || deviceType;
}

function devicePurposeLabel(purpose: DevicePurpose, t: Translator): string {
  const labels: Record<DevicePurpose, string> = {
    auto: t('devicePurposeAuto'),
    grid: t('devicePurposeGrid'),
    solar: t('devicePurposeSolar'),
    consumer: t('devicePurposeConsumer'),
    ignored: t('devicePurposeIgnored'),
  };
  return labels[purpose] || purpose;
}

function DeviceSetupPanel() {
  const { t } = useI18n();
  const [devices, setDevices] = useState<Device[]>([]);
  const [form, setForm] = useState<DeviceForm>(emptyDevice);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<DeviceForm>(emptyDevice);
  const [clearEditPassword, setClearEditPassword] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function load() { setDevices(await api.devices()); }
  useEffect(() => { void load(); }, []);

  async function save() {
    setMessage(null);
    await api.createDevice(devicePayloadFromForm(form));
    setForm(emptyDevice);
    setMessage(t('deviceSaved'));
    await load();
  }

  function startEdit(device: Device) {
    setMessage(null);
    setEditingId(device.id);
    setEditForm(deviceToForm(device));
    setClearEditPassword(false);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(emptyDevice);
    setClearEditPassword(false);
  }

  async function saveEdit(id: number) {
    setMessage(null);
    const payload = {
      ...devicePayloadFromForm(editForm),
      clear_password: clearEditPassword
    };
    if (!editForm.password.trim()) payload.password = null;
    await api.updateDevice(id, payload);
    cancelEdit();
    setMessage(t('deviceUpdated'));
    await load();
  }

  async function test(id: number) {
    const result = await api.testDevice(id);
    setMessage(`${result.ok ? t('ok') : t('error')}: ${result.message}`);
  }

  async function poll(id: number) {
    await api.pollNow(id);
    setMessage(t('pollStarted'));
    await load();
  }

  async function remove(id: number) {
    if (!confirm(t('deleteConfirm'))) return;
    await api.deleteDevice(id);
    await load();
  }

  const deviceTypeSelect = (value: DeviceType, onChange: (value: DeviceType) => void) => (
    <select value={value} onChange={e => onChange(e.target.value as DeviceType)}>
      <option value="auto">{t('autoDetection')}</option>
      <option value="shelly_3em_gen1">Shelly 3EM Gen1</option>
      <option value="shelly_pro_3em_gen2">Shelly Pro/NG 3EM</option>
      <option value="shelly_2pm_gen4">Shelly 2PM Gen4</option>
      <option value="shelly_ng_generic">Shelly NG generisch</option>
    </select>
  );

  const devicePurposeSelect = (value: DevicePurpose, onChange: (value: DevicePurpose) => void) => (
    <select value={value} onChange={e => onChange(e.target.value as DevicePurpose)}>
      <option value="auto">{t('devicePurposeAuto')}</option>
      <option value="grid">{t('devicePurposeGrid')}</option>
      <option value="solar">{t('devicePurposeSolar')}</option>
      <option value="consumer">{t('devicePurposeConsumer')}</option>
      <option value="ignored">{t('devicePurposeIgnored')}</option>
    </select>
  );

  return (
    <div className="grid gap">
      {message && <div className="info">{message}</div>}
      <section className="panel">
        <h2>{t('newShellyDevice')}</h2>
        <div className="form-grid">
          <label>{t('name')}<input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Hausanschluss" /></label>
          <label>{t('type')}{deviceTypeSelect(form.device_type, device_type => setForm({ ...form, device_type }))}</label>
          <label>{t('devicePurpose')}{devicePurposeSelect(form.purpose, purpose => setForm({ ...form, purpose }))}</label>
          <label>{t('ipHostname')}<input value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} placeholder="192.168.178.50" /></label>
          <label>{t('channel')}<input value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value === '' ? '' : Number(e.target.value) })} placeholder="leer, 0 oder 1" /></label>
          <label>{t('shellyUserOptional')}<input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
          <label>{t('shellyPasswordOptional')}<input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
          <label>{t('pollingSeconds')}<input type="number" min={5} value={form.poll_interval_seconds} onChange={e => setForm({ ...form, poll_interval_seconds: Number(e.target.value) })} /></label>
          <label className="check"><input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} /> {t('active')}</label>
        </div>
        <p className="hint">{t('devicePurposeHint')}</p>
        <button onClick={() => void save()}><Plus size={16} /> {t('addDevice')}</button>
      </section>
      <section className="panel">
        <h2>{t('configuredDevices')}</h2>
        <table>
          <thead><tr><th>{t('name')}</th><th>{t('type')}</th><th>{t('devicePurpose')}</th><th>{t('host')}</th><th>{t('channel')}</th><th>{t('polling')}</th><th>{t('status')}</th><th>{t('actions')}</th></tr></thead>
          <tbody>
            {devices.map(device => editingId === device.id ? <tr key={device.id} className="edit-row">
              <td><input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} /></td>
              <td>{deviceTypeSelect(editForm.device_type, device_type => setEditForm({ ...editForm, device_type }))}</td>
              <td>{devicePurposeSelect(editForm.purpose, purpose => setEditForm({ ...editForm, purpose }))}</td>
              <td><input value={editForm.host} onChange={e => setEditForm({ ...editForm, host: e.target.value })} /></td>
              <td><input value={editForm.channel} onChange={e => setEditForm({ ...editForm, channel: e.target.value === '' ? '' : Number(e.target.value) })} placeholder="leer, 0 oder 1" /></td>
              <td><input type="number" min={5} value={editForm.poll_interval_seconds} onChange={e => setEditForm({ ...editForm, poll_interval_seconds: Number(e.target.value) })} /></td>
              <td>
                <label className="check compact"><input type="checkbox" checked={editForm.is_active} onChange={e => setEditForm({ ...editForm, is_active: e.target.checked })} /> {t('active')}</label>
              </td>
              <td className="actions edit-actions">
                <label>{t('shellyUserOptional')}<input value={editForm.username} onChange={e => setEditForm({ ...editForm, username: e.target.value })} /></label>
                <label>{t('shellyPasswordOptional')}<input type="password" value={editForm.password} onChange={e => setEditForm({ ...editForm, password: e.target.value })} placeholder={t('unchangedPlaceholder')} /></label>
                <small>{t('passwordEditHint')}</small>
                <label className="check compact"><input type="checkbox" checked={clearEditPassword} onChange={e => setClearEditPassword(e.target.checked)} /> {t('clearShellyPassword')}</label>
                <div className="button-row">
                  <button onClick={() => void saveEdit(device.id)}>{t('saveChanges')}</button>
                  <button className="secondary" onClick={cancelEdit}>{t('cancel')}</button>
                </div>
              </td>
            </tr> : <tr key={device.id}>
              <td>{device.name}</td><td>{deviceTypeLabel(device.device_type, t)}</td><td>{devicePurposeLabel((device.purpose || 'auto') as DevicePurpose, t)}</td><td>{device.host}</td><td>{device.channel ?? t('all')}</td><td>{device.poll_interval_seconds}s</td>
              <td><span className={device.status?.online ? 'badge ok' : 'badge'}>{device.status?.online ? t('online') : t('offline')}</span></td>
              <td className="actions"><button onClick={() => startEdit(device)}>{t('edit')}</button><button onClick={() => void test(device.id)}>{t('test')}</button><button onClick={() => void poll(device.id)}>{t('pollNow')}</button><button className="danger" onClick={() => void remove(device.id)}><Trash2 size={14} /></button></td>
            </tr>)}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function AccountView({ user, onUser }: { user: User; onUser: (user: User) => void }) {
  const { t } = useI18n();
  const [setup, setSetup] = useState<{ secret: string; provisioning_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  async function startSetup() {
    setMessage(null);
    setRecoveryCodes([]);
    setSetup(await api.setup2fa());
  }

  async function enable() {
    const updated = await api.enable2fa(code);
    onUser(updated);
    setSetup(null);
    setCode('');
    setRecoveryCodes(updated.recovery_codes || []);
    setMessage(t('twoFaEnabledMessage'));
  }

  async function disable() {
    const updated = await api.disable2fa();
    onUser(updated);
    setSetup(null);
    setRecoveryCodes([]);
    setMessage(t('twoFaDisabledMessage'));
  }

  async function regenerateRecoveryCodes() {
    const response = await api.regenerateRecoveryCodes();
    setRecoveryCodes(response.recovery_codes);
    setMessage(t('recoveryRegenerated'));
  }

  return (
    <section className="panel account">
      {message && <div className="info">{message}</div>}
      <h2>{user.username}</h2>
      <p>{t('accountRole')}: <strong>{user.role === 'admin' ? t('roleAdmin') : t('roleViewer')}</strong></p>
      <p>{t('twoFaStatus')}: <strong>{user.totp_enabled ? t('enabled') : t('notActive')}</strong></p>
      <p className="hint">{t('twoFaHint')}</p>
      {!user.totp_enabled && !setup && <button onClick={() => void startSetup()}>{t('setup2fa')}</button>}
      {user.totp_enabled && <div className="actions"><button onClick={() => void regenerateRecoveryCodes()}>{t('regenerateRecoveryCodes')}</button><button className="danger" onClick={() => void disable()}>{t('disable2fa')}</button></div>}
      {setup && <div className="twofa-box">
        <QRCodeSVG value={setup.provisioning_uri} size={180} />
        <p>Secret: <code>{setup.secret}</code></p>
        <label>{t('authenticatorCode')}<input value={code} onChange={e => setCode(e.target.value)} /></label>
        <button onClick={() => void enable()}>{t('enable2fa')}</button>
      </div>}
      {recoveryCodes.length > 0 && <div className="recovery-box">
        <h3>{t('recoveryCodes')}</h3>
        <p className="hint">{t('recoveryHint')}</p>
        <ul>{recoveryCodes.map(code => <li key={code}><code>{code}</code></li>)}</ul>
      </div>}
    </section>
  );
}
