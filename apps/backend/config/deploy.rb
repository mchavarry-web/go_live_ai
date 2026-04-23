# config valid for current version and patch releases of Capistrano
lock "~> 3.19.2"

set :application, "go_live-backend"
set :repo_url, "git@github.com:augustosamame/go_live.git"
set :repo_tree, "apps/backend"


set :branch, ENV["BRANCH"] || "main"

set :user, "deploy"
set :deploy_to, "/home/deploy/rails_app"

set :rails_env, "production"
set :linked_files, fetch(:linked_files, []).push(".env", "config/master.key", "config/database.yml")

# Default value for :pty is false
# set :pty, true

# Default value for :linked_files is []
append :linked_files, "config/master.key", ".env", "config/puma/production.rb"

# Default value for linked_dirs is []
append :linked_dirs, "log", "tmp/pids", "tmp/cache", "tmp/sockets", "public/system", "public/uploads", "vendor", "storage", "app/assets/builds"

# Default value for default_env is {}
# set :default_env, { path: "/opt/ruby/bin:$PATH" }
set :env_file, ".env"

set :bundle_flags, ""
set :bundle_jobs, 1

# Default value for keep_releases is 5
set :keep_releases, 3

set :puma_user, fetch(:user)
set :puma_enable_socket_service, true
set :puma_service_unit_name, "puma.service"
set :puma_systemctl_user, :system # when the puma.service is of type system

set :sidekiq_service_unit_name, "sidekiq.service"
set :sidekiq_service_unit_user, :system

# set :assets_dependencies, %w[app/assets lib/assets vendor/assets Gemfile.lock config/routes.rb package.json yarn.lock]

set :whenever_environment, -> { fetch(:rails_env) }
set :whenever_identifier, -> { "#{fetch(:application)}_#{fetch(:stage)}" }

# Uncomment the following to require manually verifying the host key before first deploy.
# checks if master.key is present in shared/config folder. If it's not, it copies it over
namespace :deploy do
  namespace :check do
    before :linked_files, :set_master_key do
      on roles(:app) do
        unless test("[ -f #{shared_path}/config/master.key ]")
          upload! "config/master.key", "#{shared_path}/config/master.key"
        end
      end
    end
  end
end

namespace :deploy do
  desc "Create database if it does not exist"
  task :db_create do
    on roles(:db) do
      within release_path do
        with rails_env: fetch(:rails_env) do
          execute :bundle, "exec rake db:create"
        end
      end
    end
  end

  before "deploy:migrate", "deploy:db_create"
end


# this is added so that the yarn build and esbuild command is executed in the production environment


# Override the deploy:assets:precompile task
# Rake::Task["deploy:assets:precompile"].clear

# desc "Precompile assets"
# task :precompile_assets do
# on roles(:web) do
# within release_path do
# with rails_env: fetch(:rails_env) do
# execute :rake, "assets:precompile"
# Run Yarn build for production assets
# execute :yarn, "install"
# invoke "deploy:yarn_install"
# execute :yarn, "build:js:prod"
# invoke "deploy:yarn_build"
# TODO fix the double build issue
# end
# end
# end
# end
# end

# Hook the custom precompile task into the deploy process
# before "deploy:assets:precompile", "deploy:precompile_assets"
