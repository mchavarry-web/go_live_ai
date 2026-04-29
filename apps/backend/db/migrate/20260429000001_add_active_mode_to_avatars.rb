# Adds the user-selectable behavior modes to the avatar model.
#
#   active_mode           -- "professional" | "friends" | "dating"; drives
#                            tone, register, and persona-evolution scope.
#                            Read live at chat-generation time; never stamped
#                            onto conversations or audio sessions (the user
#                            wants switching to be seamless, no side effects).
#   mode_message_counts   -- per-mode lifetime user-message count, used by
#                            the Citas ramp (nascent / warming / established)
#                            and future analytics. Shape: {"professional"=>4,
#                            "friends"=>120, "dating"=>17}.
class AddActiveModeToAvatars < ActiveRecord::Migration[8.1]
  def change
    add_column :avatars, :active_mode, :string, null: false, default: "friends"
    add_index  :avatars, :active_mode

    add_column :avatars, :mode_message_counts, :jsonb, null: false, default: {}
  end
end
