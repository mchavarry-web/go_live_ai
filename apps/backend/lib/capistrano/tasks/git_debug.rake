namespace :git do
  desc "Check git mirror contents on server"
  task :check_mirror do
    on roles(:all) do
      repo_path = fetch(:repo_path)
      if test("[ -d #{repo_path} ]")
        info "Git mirror exists at #{repo_path}"
        within repo_path do
          execute :git, "log", "--oneline", "-5"
          execute :ls, "-la"
          # Try to list files in apps/backend
          if test(:git, "ls-tree", "-r", "HEAD", "--name-only", "apps/backend")
            info "apps/backend directory exists in mirror"
          else
            warn "apps/backend directory NOT found in mirror!"
          end
        end
      else
        info "Git mirror does not exist yet at #{repo_path}"
      end
    end
  end

  desc "Clean git mirror on server to force fresh clone"
  task :clean_mirror do
    on roles(:all) do
      repo_path = fetch(:repo_path)
      if test("[ -d #{repo_path} ]")
        info "Removing existing git mirror at #{repo_path}"
        execute :rm, "-rf", repo_path
        info "Git mirror removed. Next deploy will create a fresh clone."
      else
        info "No git mirror to clean"
      end
    end
  end
end
