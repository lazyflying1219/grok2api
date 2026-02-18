export interface ModelInfo {
  grok_model: [string, string];
  rate_limit_model: string;
  display_name: string;
  description: string;
  raw_model_path: string;
  default_temperature: number;
  default_max_output_tokens: number;
  supported_max_output_tokens: number;
  default_top_p: number;
  is_image_model?: boolean;
  is_video_model?: boolean;
}

export const MODEL_ALIASES: Record<string, string> = {
  "grok-420": "grok-4.2",
};

export const MODEL_CONFIG: Record<string, ModelInfo> = {
  "grok-3": {
    grok_model: ["grok-3", "MODEL_MODE_AUTO"],
    rate_limit_model: "grok-3",
    display_name: "Grok 3",
    description: "Grok 3 chat model",
    raw_model_path: "xai/grok-3",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-3-fast": {
    grok_model: ["grok-3", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-3",
    display_name: "Grok 3 Fast",
    description: "Fast Grok 3 chat model",
    raw_model_path: "xai/grok-3",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4": {
    grok_model: ["grok-4", "MODEL_MODE_AUTO"],
    rate_limit_model: "grok-4",
    display_name: "Grok 4",
    description: "Grok 4 chat model",
    raw_model_path: "xai/grok-4",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4-mini": {
    grok_model: ["grok-4-mini-thinking-tahoe", "MODEL_MODE_GROK_4_MINI_THINKING"],
    rate_limit_model: "grok-4-mini-thinking-tahoe",
    display_name: "Grok 4 Mini",
    description: "Grok 4 mini thinking model",
    raw_model_path: "xai/grok-4-mini-thinking-tahoe",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4-fast": {
    grok_model: ["grok-4", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-4",
    display_name: "Grok 4 Fast",
    description: "Fast Grok 4 chat model",
    raw_model_path: "xai/grok-4",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.1": {
    grok_model: ["grok-4-1-thinking-1129", "MODEL_MODE_AUTO"],
    rate_limit_model: "grok-4-1-thinking-1129",
    display_name: "Grok 4.1",
    description: "Grok 4.1 chat model",
    raw_model_path: "xai/grok-4-1-thinking-1129",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.1-fast": {
    grok_model: ["grok-4-1-thinking-1129", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-4-1-thinking-1129",
    display_name: "Grok 4.1 Fast",
    description: "Fast Grok 4.1 chat model",
    raw_model_path: "xai/grok-4-1-thinking-1129",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.1-expert": {
    grok_model: ["grok-4-1-thinking-1129", "MODEL_MODE_EXPERT"],
    rate_limit_model: "grok-4-1-thinking-1129",
    display_name: "Grok 4.1 Expert",
    description: "Expert Grok 4.1 chat model",
    raw_model_path: "xai/grok-4-1-thinking-1129",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.1-thinking": {
    grok_model: ["grok-4-1-thinking-1129", "MODEL_MODE_GROK_4_1_THINKING"],
    rate_limit_model: "grok-4-1-thinking-1129",
    display_name: "Grok 4.1 Thinking",
    description: "Grok 4.1 with thinking mode",
    raw_model_path: "xai/grok-4-1-thinking-1129",
    default_temperature: 1.0,
    default_max_output_tokens: 32768,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.2": {
    grok_model: ["grok-4.2", "MODEL_MODE_AUTO"],
    rate_limit_model: "grok-4.2",
    display_name: "Grok 4.2",
    description: "Grok 4.2 chat model",
    raw_model_path: "xai/grok-4.2",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-4.2-fast": {
    grok_model: ["grok-4.2", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-4.2",
    display_name: "Grok 4.2 Fast",
    description: "Fast Grok 4.2 chat model",
    raw_model_path: "xai/grok-4.2",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
  },
  "grok-imagine-1.0": {
    grok_model: ["grok-3", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-3",
    display_name: "Grok Imagine 1.0",
    description: "Image generation model",
    raw_model_path: "xai/grok-imagine-1.0",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
    is_image_model: true,
  },
  "grok-imagine-1.0-edit": {
    grok_model: ["imagine-image-edit", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-3",
    display_name: "Grok Imagine 1.0 Edit",
    description: "Image edit model",
    raw_model_path: "xai/grok-imagine-1.0-edit",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
    is_image_model: true,
  },
  "grok-imagine-1.0-video": {
    grok_model: ["grok-3", "MODEL_MODE_FAST"],
    rate_limit_model: "grok-3",
    display_name: "Grok Imagine 1.0 Video",
    description: "Video generation model",
    raw_model_path: "xai/grok-imagine-1.0-video",
    default_temperature: 1.0,
    default_max_output_tokens: 8192,
    supported_max_output_tokens: 131072,
    default_top_p: 0.95,
    is_video_model: true,
  },
};

export function normalizeModelId(model: string): string {
  const id = String(model ?? "").trim();
  return MODEL_ALIASES[id] ?? id;
}

export function isValidModel(model: string): boolean {
  return Boolean(MODEL_CONFIG[normalizeModelId(model)]);
}

export function getModelInfo(model: string): ModelInfo | null {
  return MODEL_CONFIG[normalizeModelId(model)] ?? null;
}

export function toGrokModel(model: string): { grokModel: string; mode: string; isVideoModel: boolean } {
  const cfg = getModelInfo(model);
  if (!cfg) return { grokModel: model, mode: "MODEL_MODE_FAST", isVideoModel: false };
  return { grokModel: cfg.grok_model[0], mode: cfg.grok_model[1], isVideoModel: Boolean(cfg.is_video_model) };
}

export function toRateLimitModel(model: string): string {
  return getModelInfo(model)?.rate_limit_model ?? model;
}
