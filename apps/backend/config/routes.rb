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

      # Chat
      scope "chat" do
        resources :conversations, only: %i[index show create destroy] do
          resources :messages, only: %i[index create]
        end
        post "proactive-greeting", to: "proactive_greetings#create"
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
      end
    end

    # Instagram ingestion panel (replaces the old gln-web-front Next.js).
    # `admin_instagram_path`         → GET  /admin/instagram
    # `admin_instagram_extract_path(id)` → POST /admin/instagram/:id/extract
    get  "instagram",              to: "instagram#index",   as: :instagram
    post "instagram/:id/extract",  to: "instagram#extract", as: :instagram_extract
  end

  # ── ActionCable (JWT-authenticated via ApplicationCable::Connection) ──
  mount ActionCable.server => "/cable"

  # Reveal health status on /up that returns 200 if the app boots with no exceptions, otherwise 500.
  # Can be used by load balancers and uptime monitors to verify that the app is live.
  get "up" => "rails/health#show", as: :rails_health_check

  # Defines the root path route ("/")
  root "home#index"
end
