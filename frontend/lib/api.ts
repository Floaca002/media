export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const TOKEN_KEY = "vault_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body.detail ?? body.error?.message ?? message;
    } catch {
      /* no JSON body */
    }
    // A 401 on the login endpoint itself just means "wrong password" — the
    // login form handles that inline. A 401 anywhere else means the stored
    // session token is missing/expired, so clear it and send the user back
    // to sign in rather than leaving the page stuck on a cryptic error.
    if (response.status === 401 && path !== "/auth/login" && typeof window !== "undefined") {
      clearToken();
      if (window.location.pathname !== "/login") window.location.href = "/login";
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; username: string; jellyfin_user_id: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  requestPasswordReset: (username: string) =>
    request<{ pin_file: string | null }>("/auth/request-password-reset", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),

  resetPassword: (username: string, pin: string, pinFile: string, newPassword: string) =>
    request("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ username, pin, pin_file: pinFile, new_password: newPassword }),
    }),

  trending: (mediaType: "all" | "movie" | "tv" = "all") =>
    request<{ results: TmdbItem[] }>(`/discover/trending?media_type=${mediaType}`),

  popular: (mediaType: "movie" | "tv", page = 1) =>
    request<{ results: TmdbItem[] }>(`/discover/popular?media_type=${mediaType}&page=${page}`),

  search: (query: string, page = 1) =>
    request<{ results: TmdbItem[] }>(`/discover/search?q=${encodeURIComponent(query)}&page=${page}`),

  details: (mediaType: "movie" | "tv", id: number) =>
    request<TmdbDetails>(`/discover/${mediaType}/${id}`),

  availability: (mediaType: "movie" | "tv", id: number) =>
    request<Availability>(`/discover/${mediaType}/${id}/availability`),

  createRequest: (body: {
    tmdb_id: number;
    media_type: string;
    title: string;
    magnet?: string;
    season?: number;
    episode?: number;
  }) => request<RequestOut>("/requests", { method: "POST", body: JSON.stringify(body) }),

  downloads: () => request<DownloadOut[]>("/downloads"),
  pauseDownload: (hash: string) => request(`/downloads/${hash}/pause`, { method: "POST" }),
  resumeDownload: (hash: string) => request(`/downloads/${hash}/resume`, { method: "POST" }),
  deleteDownload: (hash: string, deleteFiles: boolean) =>
    request(`/downloads/${hash}?delete_files=${deleteFiles}`, { method: "DELETE" }),

  libraryItems: (params: { type?: string; search?: string } = {}) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<{ Items: JellyfinItem[]; TotalRecordCount: number }>(`/library/items?${qs}`);
  },
  continueWatching: () => request<JellyfinItem[]>("/library/continue-watching"),
  playbackInfo: async (itemId: string) => {
    const info = await request<PlaybackInfo>(`/library/items/${itemId}/playback`);
    // hls_url comes back as a path relative to the backend (e.g.
    // "/api/stream/..."), not the frontend's own origin — resolve it
    // against wherever the API base actually points.
    const origin = new URL(API_BASE_URL).origin;
    return { ...info, hls_url: `${origin}${info.hls_url}` };
  },
  reportProgress: (body: {
    item_id: string;
    play_session_id: string;
    media_source_id: string;
    position_ticks: number;
    is_paused?: boolean;
    event?: "start" | "progress" | "stop";
  }) => request("/watch/progress", { method: "POST", body: JSON.stringify(body) }),
};

export function downloadsSocketUrl(): string {
  const token = getToken() ?? "";
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/downloads/stream?token=${token}`;
}

// ---- Types ----
export interface TmdbItem {
  id: number;
  media_type: "movie" | "tv";
  title?: string;
  name?: string;
  overview: string;
  poster_url: string | null;
  backdrop_url: string | null;
  vote_average: number;
  release_date?: string;
  first_air_date?: string;
}

export interface TmdbDetails extends TmdbItem {
  genres: { id: number; name: string }[];
  runtime?: number;
  trailer_key: string | null;
  cast: { id: number; name: string; character: string; profile_path: string | null }[];
  similar: TmdbItem[];
}

export interface Availability {
  status: "NOT_REQUESTED" | "SEARCHING" | "DOWNLOADING" | "ORGANIZING" | "AVAILABLE" | "FAILED";
  jellyfin_item_id: string | null;
  request_id?: number;
}

export interface RequestOut {
  id: number;
  tmdb_id: number;
  media_type: string;
  title: string;
  status: string;
  torrent_hash: string | null;
  jellyfin_item_id: string | null;
}

export interface DownloadOut {
  hash: string;
  name: string;
  category: string | null;
  progress: number;
  download_speed_bps: number;
  upload_speed_bps: number;
  eta_seconds: number | null;
  state: string;
  size_bytes: number;
  request_id: number | null;
}

export interface JellyfinItem {
  Id: string;
  Name: string;
  Type: string;
  Overview?: string;
  ProductionYear?: number;
  UserData?: { PlayedPercentage?: number; Played?: boolean };
  ImageTags?: { Primary?: string };
}

export interface PlaybackInfo {
  hls_url: string;
  play_session_id: string;
  media_source_id: string;
  start_position_ticks: number;
}
