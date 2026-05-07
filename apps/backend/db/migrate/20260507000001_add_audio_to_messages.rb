class AddAudioToMessages < ActiveRecord::Migration[8.1]
  def change
    # Shrine attachment column. Stays nil for plain-text messages so the
    # mobile client can detect "this message has audio" with a single
    # presence check on the metadata payload.
    add_column :messages, :audio_data, :text
  end
end
