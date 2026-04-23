Rails.application.routes.draw do
  # Devise authentication
  devise_for :users, controllers: {
    sessions: 'users/sessions'
  }

  # Mobile API routes
  namespace :api do
    namespace :v1 do
      namespace :mobile do
        post 'login', to: 'sessions#create'
        delete 'logout', to: 'sessions#destroy'
        get 'user', to: 'sessions#show'
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

  # Reveal health status on /up that returns 200 if the app boots with no exceptions, otherwise 500.
  # Can be used by load balancers and uptime monitors to verify that the app is live.
  get "up" => "rails/health#show", as: :rails_health_check

  # Defines the root path route ("/")
  root "home#index"
end
