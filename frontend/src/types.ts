export type User = {
  email: string;
  display_name: string;
  role: "admin" | "reference_editor" | "user";
  organization_id: string;
  organization_name: string;
};

export type Rock = {
  name: string;
  density_t_m3: number;
  ucs_mpa: number;
  fissuring_ff: number;
};

export type Explosive = {
  key: string;
  name: string;
  density_t_m3: number;
  power_mj_kg: number;
  chart_label: string;
};

export type BlastVariant = {
  crown_mm: number;
  specific_q_kg_m3: number;
  line_of_least_resistance_m: number;
  grid_a_m: number;
  grid_b_m: number;
  grid_label: string;
  x50_mm: number;
  oversize_pct: number;
  target_q_kg_m3: number | null;
};
