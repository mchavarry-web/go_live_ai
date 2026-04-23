require "capistrano/setup"
require "capistrano/deploy"
require 'capistrano/rails/console'
require "capistrano/scm/git"
install_plugin Capistrano::SCM::Git
require 'capistrano/dotenv'
require 'capistrano/rails'
# require 'capistrano/faster_assets'
# require 'capistrano/yarn'
require 'capistrano/puma'
install_plugin Capistrano::Puma  # Default puma tasks
install_plugin Capistrano::Puma::Systemd
require 'capistrano/sidekiq'
install_plugin Capistrano::Sidekiq  # Default sidekiq tasks
install_plugin Capistrano::Sidekiq::Systemd
require 'whenever/capistrano'

# Load custom tasks from `lib/capistrano/tasks` if you have any defined
Dir.glob("lib/capistrano/tasks/*.rake").each { |r| import r }
