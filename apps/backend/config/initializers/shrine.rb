require "shrine"

Shrine.logger = Rails.logger

# Storage selection:
#   - If S3 env vars are set, use S3 for cache/public/private (staging, prod).
#   - Otherwise fall back to local filesystem storage under storage/ (dev).
if ENV["S3_AWS_STORAGE_BUCKET_NAME"].present?
  require "shrine/storage/s3"

  s3_options = {
    bucket:            ENV["S3_AWS_STORAGE_BUCKET_NAME"],
    region:            ENV.fetch("AWS_REGION", "us-east-1"),
    access_key_id:     ENV["AWS_ACCESS_KEY_ID"],
    secret_access_key: ENV["AWS_SECRET_ACCESS_KEY"]
  }

  Shrine.storages = {
    cache:         Shrine::Storage::S3.new(prefix: "cache", **s3_options),
    store_public:  Shrine::Storage::S3.new(prefix: "public", upload_options: { acl: nil }, **s3_options.merge(public: true)),
    store_private: Shrine::Storage::S3.new(prefix: "private", **s3_options.merge(public: false))
  }
else
  require "shrine/storage/file_system"

  Shrine.storages = {
    cache:         Shrine::Storage::FileSystem.new("storage", prefix: "cache"),
    store_public:  Shrine::Storage::FileSystem.new("storage", prefix: "public"),
    store_private: Shrine::Storage::FileSystem.new("storage", prefix: "private")
  }
end

Shrine.plugin :activerecord
Shrine.plugin :cached_attachment_data
Shrine.plugin :restore_cached_data
Shrine.plugin :derivatives, create_on_promote: true
Shrine.plugin :determine_mime_type, analyzer: :marcel
Shrine.plugin :validation_helpers
Shrine.plugin :default_url
Shrine.plugin :pretty_location
