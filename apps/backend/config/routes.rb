Rails.application.routes.draw do
  # ── Web (Devise cookie session — admin area + marketing pages) ──────
  devise_for :users, controllers: {
    sessions: "users/sessions"
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
    root 'dashboard#index'

    resources :users do
      member do
        post :assign_role
        delete :remove_role
      end
    end
  end

  # ── ActionCable (JWT-authenticated via ApplicationCable::Connection) ──
  mount ActionCable.server => "/cable"

  # Reveal health status on /up that returns 200 if the app boots with no exceptions, otherwise 500.
  # Can be used by load balancers and uptime monitors to verify that the app is live.
  get "up" => "rails/health#show", as: :rails_health_check

  # Defines the root path route ("/")
  root "home#index"
end
