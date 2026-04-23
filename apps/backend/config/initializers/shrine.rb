require "shrine"
require "shrine/storage/s3"

Shrine.logger = Rails.logger

# S3 storage configuration using environment variables
s3_options = {
  bucket:            ENV["S3_AWS_STORAGE_BUCKET_NAME"],
  region:            ENV.fetch("AWS_REGION", "us-east-1"),
  access_key_id:     ENV["AWS_ACCESS_KEY_ID"],
  secret_access_key: ENV["AWS_SECRET_ACCESS_KEY"]
}

Shrine.storages = {
  cache: Shrine::Storage::S3.new(prefix: "cache", **s3_options), # temporary storage
  # Public storage (public read access)
  store_public: Shrine::Storage::S3.new(prefix: "public", upload_options: { acl: nil }, **s3_options.merge(public: true)),
  # Private storage (requires signed URLs)
  store_private: Shrine::Storage::S3.new(prefix: "private", **s3_options.merge(public: false))
}

Shrine.plugin :activerecord           # loads Active Record integration
Shrine.plugin :cached_attachment_data # enables retaining cached file across form redisplays
Shrine.plugin :restore_cached_data
Shrine.plugin :derivatives, create_on_promote: true
Shrine.plugin :determine_mime_type, analyzer: :marcel
Shrine.plugin :validation_helpers
Shrine.plugin :default_url
Shrine.plugin :pretty_location
