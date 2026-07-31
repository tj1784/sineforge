-- PostgreSQL schema for local Automated AI Video Editor.
-- Stores reproducibility, model registry, ComfyUI jobs, generated assets, benchmarks, and FFmpeg assembly.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE hardware_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  gpu_name TEXT NOT NULL,
  vram_mib INTEGER NOT NULL,
  ram_mib INTEGER NOT NULL,
  driver_version TEXT,
  cuda_version TEXT,
  os TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  workflow_lane TEXT NOT NULL DEFAULT 'cineforge_studio'
    CHECK (workflow_lane IN ('cineforge_studio', 'agentless')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  target_duration_sec NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tracks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('video','voiceover','music','sfx','subtitle')),
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE timeline_slots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  slot_index INTEGER NOT NULL,
  start_sec NUMERIC NOT NULL,
  duration_sec NUMERIC NOT NULL,
  continuity_source_slot_id UUID REFERENCES timeline_slots(id),
  notes TEXT,
  UNIQUE(track_id, slot_index)
);

CREATE TABLE prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE negative_prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  family TEXT NOT NULL,
  name TEXT NOT NULL,
  source_url TEXT,
  license TEXT,
  evidence_level TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE model_variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  variant_name TEXT NOT NULL,
  params_b NUMERIC,
  file_path TEXT,
  file_size_bytes BIGINT,
  sha256 TEXT,
  precision TEXT,
  quantization TEXT,
  compatible_24gb_status TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE quantizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  applies_to TEXT NOT NULL,
  loader_node TEXT,
  evidence_level TEXT NOT NULL,
  recommended_24gb BOOLEAN NOT NULL DEFAULT false,
  notes TEXT
);

CREATE TABLE text_encoders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  file_path TEXT,
  sha256 TEXT,
  precision TEXT,
  source_url TEXT,
  notes TEXT
);

CREATE TABLE vaes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  file_path TEXT,
  sha256 TEXT,
  precision TEXT,
  source_url TEXT,
  notes TEXT
);

CREATE TABLE loras (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  base_model_id UUID REFERENCES models(id),
  base_variant_id UUID REFERENCES model_variants(id),
  purpose TEXT NOT NULL,
  file_path TEXT,
  sha256 TEXT,
  source_url TEXT,
  license TEXT,
  quantized_base_status TEXT NOT NULL DEFAULT 'unknown',
  evidence_level TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE lora_combinations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT
);

CREATE TABLE lora_combination_items (
  combination_id UUID NOT NULL REFERENCES lora_combinations(id) ON DELETE CASCADE,
  lora_id UUID NOT NULL REFERENCES loras(id),
  order_index INTEGER NOT NULL,
  strength_model NUMERIC,
  strength_clip NUMERIC,
  extra_params JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (combination_id, lora_id, order_index)
);

CREATE TABLE workflow_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  workflow_api_json JSONB NOT NULL,
  manifest_json JSONB NOT NULL,
  sha256 TEXT NOT NULL,
  comfyui_commit TEXT,
  custom_node_snapshot JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(name, version)
);

CREATE TABLE clips (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timeline_slot_id UUID NOT NULL REFERENCES timeline_slots(id) ON DELETE CASCADE,
  title TEXT,
  selected_iteration_id UUID,
  status TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE clip_iterations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
  iteration_index INTEGER NOT NULL,
  prompt_id UUID REFERENCES prompts(id),
  negative_prompt_id UUID REFERENCES negative_prompts(id),
  model_variant_id UUID REFERENCES model_variants(id),
  quantization_id UUID REFERENCES quantizations(id),
  text_encoder_id UUID REFERENCES text_encoders(id),
  vae_id UUID REFERENCES vaes(id),
  lora_combination_id UUID REFERENCES lora_combinations(id),
  seed BIGINT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  frame_count INTEGER NOT NULL,
  fps NUMERIC NOT NULL,
  steps INTEGER,
  sampler TEXT,
  scheduler TEXT,
  guidance NUMERIC,
  extra_params JSONB NOT NULL DEFAULT '{}',
  quality_rating INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(clip_id, iteration_index)
);

ALTER TABLE clips
  ADD CONSTRAINT clips_selected_iteration_fk
  FOREIGN KEY (selected_iteration_id) REFERENCES clip_iterations(id);

CREATE TABLE workflow_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_iteration_id UUID REFERENCES clip_iterations(id) ON DELETE SET NULL,
  workflow_template_id UUID NOT NULL REFERENCES workflow_templates(id),
  patched_workflow_json JSONB NOT NULL,
  patch_payload_json JSONB NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ
);

CREATE TABLE comfy_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
  prompt_id TEXT,
  client_id TEXT,
  queue_number INTEGER,
  status TEXT NOT NULL,
  worker_id TEXT,
  reserved_at TIMESTAMPTZ,
  heartbeat_at TIMESTAMPTZ,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_state_change_at TIMESTAMPTZ,
  recovery_metadata JSONB NOT NULL DEFAULT '{}',
  node_errors JSONB,
  websocket_events JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  submitted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE TABLE generated_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clip_iteration_id UUID REFERENCES clip_iterations(id) ON DELETE SET NULL,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT,
  width INTEGER,
  height INTEGER,
  frame_count INTEGER,
  fps NUMERIC,
  duration_sec NUMERIC,
  probe_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE file_outputs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
  generated_asset_id UUID REFERENCES generated_assets(id) ON DELETE SET NULL,
  filename_prefix TEXT,
  filename TEXT NOT NULL,
  subfolder TEXT,
  type TEXT,
  path TEXT NOT NULL,
  sha256 TEXT
);

CREATE TABLE benchmark_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hardware_profile_id UUID NOT NULL REFERENCES hardware_profiles(id),
  workflow_template_id UUID REFERENCES workflow_templates(id),
  model_variant_id UUID REFERENCES model_variants(id),
  quantization_id UUID REFERENCES quantizations(id),
  lora_combination_id UUID REFERENCES lora_combinations(id),
  settings JSONB NOT NULL,
  metrics JSONB NOT NULL,
  decision TEXT NOT NULL,
  notes TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ
);

CREATE TABLE ffmpeg_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  command TEXT NOT NULL,
  input_manifest JSONB NOT NULL,
  output_path TEXT,
  status TEXT NOT NULL,
  probe_json JSONB,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  error_message TEXT
);

CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL,
  entity_id UUID,
  action TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE error_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_timeline_slots_track ON timeline_slots(track_id, slot_index);
CREATE INDEX idx_clip_iterations_clip ON clip_iterations(clip_id, iteration_index);
CREATE INDEX idx_clip_iterations_model ON clip_iterations(model_variant_id, quantization_id, lora_combination_id);
CREATE INDEX idx_workflow_runs_iteration ON workflow_runs(clip_iteration_id);
CREATE INDEX idx_comfy_jobs_prompt ON comfy_jobs(prompt_id);
CREATE INDEX idx_generated_assets_iteration ON generated_assets(clip_iteration_id);
CREATE INDEX idx_benchmark_model_quant ON benchmark_runs(model_variant_id, quantization_id);
CREATE INDEX idx_ffmpeg_campaign ON ffmpeg_jobs(campaign_id);
