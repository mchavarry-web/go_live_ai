require "image_processing/vips"

class UserImageUploader < Shrine
  storages[:store] = Shrine.storages[:store_public]

  Attacher.validate do
    validate_max_size 5.megabytes, message: "es demasiado grande (máximo 5MB)"
    validate_mime_type_inclusion [ "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp" ]
  end

  Attacher.derivatives do |original|
    vips = ImageProcessing::Vips.source(original)

    {
      large:  vips.resize_to_fill!(300, 300),   # For profile pages
      medium: vips.resize_to_fill!(150, 150),  # For cards and lists
      thumb:  vips.resize_to_fill!(50, 50),    # For header navigation
      avatar: vips.resize_to_fill!(40, 40)     # For small avatars
    }
  end
end
