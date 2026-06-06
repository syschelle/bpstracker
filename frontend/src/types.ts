export type Language = string;
export type CurrencyCode = 'EUR' | 'USD' | 'GBP';

export type DeviceType = 'auto' | 'shelly_3em_gen1' | 'shelly_pro_3em_gen2' | 'shelly_2pm_gen4' | 'shelly_ng_generic';
export type DevicePurpose = 'auto' | 'grid' | 'solar' | 'consumer' | 'ignored';

export interface User {
  id: number;
  username: string;
  role: 'admin' | 'viewer';
  is_active: boolean;
  totp_enabled: boolean;
  created_at: string;
}

export interface DeviceStatus {
  online: boolean;
  detected_model?: string | null;
  generation?: string | null;
  firmware?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: string | null;
}

export interface Device {
  id: number;
  name: string;
  device_type: DeviceType;
  purpose: DevicePurpose;
  host: string;
  username?: string | null;
  is_active: boolean;
  poll_interval_seconds: number;
  channel?: number | null;
  created_at: string;
  updated_at: string;
  status?: DeviceStatus | null;
}

export interface Measurement {
  id: number;
  timestamp: string;
  device_id: number;
  source_type: string;
  channel?: number | null;
  phase?: string | null;
  power_w?: number | null;
  voltage_v?: number | null;
  current_a?: number | null;
  power_factor?: number | null;
  energy_import_wh?: number | null;
  energy_export_wh?: number | null;
  total_power_w?: number | null;
  solar_power_w?: number | null;
  grid_power_w?: number | null;
}

export interface HistoryTotals {
  imported_kwh?: number | null;
  exported_kwh?: number | null;
  solar_kwh?: number | null;
}

export interface HistorySeries {
  points: Measurement[];
  totals: HistoryTotals;
}

export interface UiSettings {
  language: Language;
  timezone: string;
}

export interface FinanceSettings {
  kwh_price_eur: number;
  investment_cost_eur: number;
  battery_analysis_enabled: boolean;
  battery_cost_eur: number;
  battery_capacity_kwh: number;
  battery_roundtrip_efficiency: number;
  currency_code: CurrencyCode;
}

export interface RetentionSettings {
  raw_retention_days: number;
  daily_aggregates_forever: boolean;
  effective_raw_retention_hours?: number | null;
  live_data_max_hours?: number | null;
  pi_zero_2w_mode?: boolean;
}

export interface KindleDisplaySettings {
  enabled: boolean;
}

export interface CurrentValuesApiSettings {
  enabled: boolean;
}

export interface SimulationSettings {
  enabled: boolean;
  pv_peak_w: number;
  baseload_day_w: number;
  baseload_night_w: number;
  household_profile: string;
}

export interface Summary {
  current_grid_power_w?: number | null;
  current_solar_power_w?: number | null;
  current_total_power_w?: number | null;
  imported_today_kwh?: number | null;
  exported_today_kwh?: number | null;
  solar_today_kwh?: number | null;
  imported_total_kwh?: number | null;
  exported_total_kwh?: number | null;
  solar_total_kwh?: number | null;
  kwh_price_eur: number;
  investment_cost_eur: number;
  battery_analysis_enabled?: boolean | null;
  battery_cost_eur?: number | null;
  battery_capacity_kwh?: number | null;
  battery_roundtrip_efficiency?: number | null;
  battery_remaining_bps_investment_eur?: number | null;
  battery_combined_investment_eur?: number | null;
  battery_combined_payback_days?: number | null;
  battery_combined_payback_years?: number | null;
  battery_usable_surplus_today_kwh?: number | null;
  battery_savings_today_eur?: number | null;
  battery_savings_total_potential_eur?: number | null;
  battery_payback_days?: number | null;
  battery_payback_years?: number | null;
  battery_worthwhile?: boolean | null;
  currency_code: CurrencyCode;
  consumption_cost_today_eur?: number | null;
  savings_today_eur?: number | null;
  savings_total_eur?: number | null;
  remaining_to_breakeven_eur?: number | null;
  breakeven_progress_percent?: number | null;
  estimated_breakeven_days?: number | null;
  estimated_breakeven_date?: string | null;
  last_measurement_at?: string | null;
  device_count: number;
  online_device_count: number;
  raw_retention_days: number;
  public_meter_number?: string | null;
}


export interface AirSensorSettings {
  enabled: boolean;
  host?: string | null;
}

export interface AirSensorCurrent {
  enabled: boolean;
  configured: boolean;
  ok: boolean;
  cached?: boolean;
  temperature_c?: number | null;
  humidity_percent?: number | null;
  sds_p1?: number | null;
  sds_p2?: number | null;
  age_seconds?: number | null;
  software_version?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
}


export interface BackupInfo {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface BackupCreateResponse {
  filename: string;
  size_bytes: number;
  download_url: string;
}


export interface ResetValuesResponse {
  ok: boolean;
  deleted_measurements: number;
  deleted_daily_summaries: number;
  message: string;
}


export interface PublicDashboardSettings {
  enabled: boolean;
  meter_number?: string | null;
}
