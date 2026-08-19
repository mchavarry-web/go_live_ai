Rails.application.routes.draw do
  # ── Web (Devise cookie session — admin area + marketing pages) ──────
  devise_for :users, controllers: {
    sessions:            "users/sessions",
    omniauth_callbacks:  "users/omniauth_callbacks"
  }

  # ── Mobile + Web API (hand-rolled JWT, see Api::V1::BaseController) ──
  namespace :api do
    namespace :v1 do
      # Auth — every flow terminates in { access_token, refresh_token, user }
      post   "auth/sign_in",  to: "auth#sign_in"
      post   "auth/sign_up",  to: "auth#sign_up"
      post   "auth/google",   to: "auth#google"
      post   "auth/apple",    to: "auth#apple"
      post   "auth/facebook", to: "auth#facebook"
      post   "auth/refresh",  to: "auth#refresh"
      get    "auth/me",       to: "auth#me"
      delete "auth/sign_out", to: "auth#sign_out"

      # Onboarding
      get  "onboarding/status",   to: "onboarding#status"
      post "onboarding/complete", to: "onboarding#complete"
      post "onboarding/reset",    to: "onboarding#reset"

      # Avatar (1:1 with user — appearance + behavior jsonb)
      get    "avatar",                      to: "avatars#show"
      patch  "avatar",                      to: "avatars#update"
      get    "avatar/insights",             to: "avatars#insights"
      delete "avatar/insights",             to: "avatars#delete_all_insights"
      delete "avatar/insights/:id",         to: "avatars#delete_insight"
      post   "avatar/teach",                to: "avatars#teach"

      # Per-user feature settings (proactive skill opt-out, future flags)
      get  "settings/features", to: "feature_settings#index"
      post "settings/features", to: "feature_settings#update"

      # Psychological profiling (DEV-98 — strictly opt-in via
      # avatar.behavior["psych_profiling_opt_in"]; env-gated in FastAPI)
      post "profile/psych", to: "psych_profiles#create"
      get  "profile/psych", to: "psych_profiles#show"

      # Chat
      scope "chat" do
        resources :conversations, only: %i[index show create destroy] do
          resources :messages, only: %i[index create] do
            collection do
              # Multipart audio upload → transcribe → user message →
              # voice-mode ChatGenerationJob (assistant reply rendered as TTS).
              post :voice
            end
          end
        end
        # Auth-gated audio bytes for an assistant TTS reply (or a stored
        # user voice clip). Flat — keyed by message id so the cable
        # broadcast can carry just the id.
        get "messages/:id/audio", to: "message_audios#show", as: :message_audio
        post "proactive-greeting", to: "proactive_greetings#create"
      end

      # Audio training (continuous recording → transcription → insights)
      scope "audio" do
        resources :sessions, only: %i[index show create destroy], controller: "audio_sessions" do
          post :finish, on: :member
          post :cancel, on: :member
          resources :chunks, only: %i[create], controller: "audio_chunks"
        end
        post   "wipe",              to: "audio_sessions#wipe_all"
        get    "voice_enrollment",  to: "voice_enrollments#show"
        post   "voice_enrollment",  to: "voice_enrollments#create"
        delete "voice_enrollment",  to: "voice_enrollments#destroy"
      end

      # Wave C.4 (2026-05-06) — agent draft-mode proposal surface.
      # No execution; proposals are persisted as audit rows for the user
      # to approve/reject/edit. See docs/autonomous_agent_design.md.
      scope "agent" do
        resources :proposals,
                  only: %i[index show create],
                  controller: "agent_proposals" do
          patch :approve, on: :member
          patch :reject,  on: :member
          patch :edit,    on: :member
        end
      end

      # Device tokens + push notifications
      scope "notifications" do
        post   "device_tokens",         to: "device_tokens#create"
        delete "device_tokens/:token",  to: "device_tokens#destroy", constraints: { token: %r{[^/]+} }
        post   "test",                  to: "device_tokens#test"
      end

      # Social connections + ingestion (flat per-platform, no Ingestion:: namespace)
      %w[instagram facebook twitter spotify].each do |p|
        get    "#{p}/status",  to: "#{p}#status"
        post   "#{p}/ingest",  to: "#{p}#ingest"
        post   "#{p}/extract", to: "#{p}#extract_insights"
        delete "#{p}",         to: "#{p}#disconnect"
      end

      # Spotify-only OAuth endpoints
      get "spotify/auth_url", to: "spotify#auth_url"
      get "spotify/callback", to: "spotify#callback"

      # Legacy mobile sessions (kept until Expo is fully switched to /auth/*)
      namespace :mobile do
        post   "login",  to: "sessions#create"
        delete "logout", to: "sessions#destroy"
        get    "user",   to: "sessions#show"
      end
    end
  end

  # Admin routes
  namespace :admin do
    get "dashboard/index"
    root "dashboard#index"

    resources :users do
      member do
        post :promote
        post :demote
        post :reset_onboarding
        post :extract
        post :disconnect_social
      end

      # Memory / training drill-down (lives in FastAPI; Rails proxies via AiAgentsClient).
      resources :memories,
                only:       %i[index show edit update destroy],
                controller: "user_memories"
    end

    # Instagram ingestion panel (replaces the old gln-web-front Next.js).
    # `admin_instagram_path`         → GET  /admin/instagram
    # `admin_instagram_extract_path(id)` → POST /admin/instagram/:id/extract
    get  "instagram",              to: "instagram#index",   as: :instagram
    post "instagram/:id/extract",  to: "instagram#extract", as: :instagram_extract

    # Global feature flags (proactive-skill toggles, future feature gates)
    get   "feature_settings", to: "feature_settings#index", as: :feature_settings
    patch "feature_settings", to: "feature_settings#update"
  end

  # ── ActionCable (JWT-authenticated via ApplicationCable::Connection) ──
  mount ActionCable.server => "/cable"

  # Reveal health status on /up that returns 200 if the app boots with no exceptions, otherwise 500.
  # Can be used by load balancers and uptime monitors to verify that the app is live.
  get "up" => "rails/health#show", as: :rails_health_check

  # Defines the root path route ("/")
  root "home#index"
end
