namespace :git do
  desc "Debug: List branches and check for apps/backend in mirror"
  task :debug_mirror do
    on roles(:all) do
      repo_path = deploy_path.join("repo")
      within repo_path do
        info "=== Listing all refs ==="
        execute :git, "show-ref"

        info "=== Checking if apps/backend exists in HEAD ==="
        execute :git, "ls-tree", "-r", "--name-only", "HEAD", "|", "grep", "apps/backend", "|", "head"

        info "=== Checking if apps/backend exists in origin/main ==="
        execute :git, "ls-tree", "-r", "--name-only", "origin/main", "|", "grep", "apps/backend", "|", "head"

        info "=== Testing git archive with HEAD ==="
        execute :git, "archive", "--list"
      end
    end
  end
end
